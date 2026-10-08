//! Client side of the parent/child IPC channel.
//!
//! [`ParentBridge`] is what an AuroraView **child** process uses to talk to its
//! parent. It is deliberately dependency-free (std TCP + serde), so it can be
//! used from the CLI, from future native hosts, or from tests without pulling
//! in a WebView.
//!
//! # Lifecycle
//!
//! ```text
//! ParentBridge::connect(info)
//!   - TCP connect to 127.0.0.1:<AURORAVIEW_PARENT_PORT>
//!   - spawn reader thread
//!   - send {"type":"hello","protocol":1,...}
//!   - send {"type":"event","event":"child:ready",...}   (legacy-compatible)
//! ```
//!
//! The handshake is **non-blocking and backward compatible**: `hello` is
//! followed immediately by `child:ready`, so a pre-protocol parent that simply
//! ignores `hello` keeps working unchanged. A parent that *does* implement the
//! protocol answers with `hello_ack`. Callers that care use
//! [`ParentBridge::wait_for_handshake`]; if no ack arrives before the deadline
//! the state is downgraded to [`HandshakeState::Legacy`] rather than failing.

use std::collections::HashMap;
use std::io::{self, Read, Write};
use std::net::{Shutdown, TcpStream};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex, Weak};
use std::thread;
use std::time::Duration;

use serde_json::json;

use super::context::ChildInfo;
use super::protocol::{
    ErrorCode, FrameError, FrameReader, Message, MessageKind, CLOSING_EVENT, COMMAND_EVENT,
    DEFAULT_HOST, MAX_FRAME_BYTES, PROTOCOL_VERSION, READY_EVENT,
};

/// How far the opening exchange has progressed.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HandshakeState {
    /// `hello` sent, no `hello_ack` seen yet.
    Pending,
    /// Parent answered `hello_ack` with `accepted: true`.
    Acked,
    /// Handshake deadline passed without an ack; treated as a pre-protocol
    /// parent. The channel is fully usable, just without negotiation.
    Legacy,
    /// Parent refused the child (`accepted: false` or a fatal `error`).
    Rejected,
    /// Channel is down.
    Disconnected,
}

impl HandshakeState {
    /// Stable, lowercase name used in logs and diagnostics.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Acked => "acked",
            Self::Legacy => "legacy",
            Self::Rejected => "rejected",
            Self::Disconnected => "disconnected",
        }
    }
}

/// A registered event callback.
type SharedHandler = Arc<dyn Fn(serde_json::Value) + Send + Sync>;
/// A registered disconnect callback.
type SharedDisconnectHandler = Arc<dyn Fn() + Send + Sync>;

/// Reconnect behaviour after the channel drops.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum ReconnectPolicy {
    /// Never reconnect (default). Matches the Python `ParentBridge`.
    #[default]
    Disabled,
    /// Retry a bounded number of times with a fixed interval.
    Fixed {
        /// Maximum attempts before giving up.
        attempts: u32,
        /// Delay between attempts.
        interval: Duration,
    },
}

/// Errors surfaced by the bridge.
#[derive(Debug)]
pub enum BridgeError {
    /// TCP connect failed.
    Io(io::Error),
    /// Outbound frame could not be serialized.
    Encode(serde_json::Error),
    /// The channel is not connected.
    NotConnected,
}

impl std::fmt::Display for BridgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "ipc io error: {}", e),
            Self::Encode(e) => write!(f, "ipc encode error: {}", e),
            Self::NotConnected => f.write_str("ipc channel is not connected"),
        }
    }
}

impl std::error::Error for BridgeError {}

impl From<io::Error> for BridgeError {
    fn from(e: io::Error) -> Self {
        Self::Io(e)
    }
}

impl From<serde_json::Error> for BridgeError {
    fn from(e: serde_json::Error) -> Self {
        Self::Encode(e)
    }
}

/// Runtime configuration for [`ParentBridge`].
#[derive(Debug, Clone)]
pub struct BridgeConfig {
    /// Host to connect to. Always loopback in practice.
    pub host: String,
    /// Port to connect to (`AURORAVIEW_PARENT_PORT`).
    pub port: u16,
    /// Value sent as `child_id`.
    pub child_id: Option<String>,
    /// Value sent as `parent_id`.
    pub parent_id: Option<String>,
    /// Value sent as `example_name`.
    pub example_name: Option<String>,
    /// TCP connect timeout.
    pub connect_timeout: Duration,
    /// How long [`ParentBridge::wait_for_handshake`] waits before downgrading
    /// to [`HandshakeState::Legacy`].
    pub handshake_timeout: Duration,
    /// Reconnect behaviour.
    pub reconnect: ReconnectPolicy,
    /// Emit `child:ready` right after `hello`.
    ///
    /// On by default: pre-protocol parents rely on `child:ready` to mark a
    /// child as live.
    pub announce_ready: bool,
    /// Emit `child:closing` when the bridge shuts down cleanly.
    pub announce_closing: bool,
    /// Read timeout used by the reader thread so it can observe shutdown
    /// promptly even if the peer never closes the socket.
    pub read_timeout: Duration,
}

impl Default for BridgeConfig {
    fn default() -> Self {
        Self {
            host: DEFAULT_HOST.to_string(),
            port: 0,
            child_id: None,
            parent_id: None,
            example_name: None,
            connect_timeout: Duration::from_secs(3),
            handshake_timeout: Duration::from_secs(2),
            reconnect: ReconnectPolicy::Disabled,
            announce_ready: true,
            announce_closing: true,
            read_timeout: Duration::from_millis(500),
        }
    }
}

impl BridgeConfig {
    /// Config derived from a [`ChildInfo`] snapshot.
    pub fn from_child_info(info: &ChildInfo) -> Self {
        Self {
            host: DEFAULT_HOST.to_string(),
            port: info.parent_port.unwrap_or(0),
            child_id: info.child_id.clone(),
            parent_id: info.parent_id.clone(),
            example_name: info.example_name.clone(),
            ..Default::default()
        }
    }
}

struct Shared {
    config: BridgeConfig,
    /// Write half of the socket. `None` while disconnected.
    writer: Mutex<Option<TcpStream>>,
    handlers: Mutex<HashMap<String, Vec<(u64, SharedHandler)>>>,
    next_handler_id: AtomicU64,
    disconnect_handlers: Mutex<Vec<(u64, SharedDisconnectHandler)>>,
    /// Poked whenever the handshake state changes.
    handshake_cv: Condvar,
    handshake: Mutex<HandshakeState>,
    running: Mutex<bool>,
    /// Serialises reconnect attempts.
    reconnect_lock: Mutex<()>,
}

/// Client side of the parent/child IPC channel.
///
/// Cloning is cheap: all clones talk to the same connection. Dropping the last
/// clone tears the channel down.
#[derive(Clone)]
pub struct ParentBridge {
    shared: Arc<Shared>,
}

impl ParentBridge {
    /// Connect using the environment-derived [`ChildInfo`].
    pub fn connect(info: &ChildInfo) -> Result<Self, BridgeError> {
        Self::connect_with_config(BridgeConfig::from_child_info(info))
    }

    /// Connect with an explicit configuration.
    pub fn connect_with_config(config: BridgeConfig) -> Result<Self, BridgeError> {
        let stream = Self::tcp_connect(&config)?;
        let bridge = Self::from_stream(config, stream)
            .ok_or_else(|| BridgeError::Io(io::Error::other("failed to split the IPC socket")))?;
        bridge.start_handshake();
        Ok(bridge)
    }

    /// Wrap an already-connected stream (test seam).
    ///
    /// Returns `None` when the socket cannot be split into a read half and a
    /// write half, which would leave the bridge half-duplex.
    pub(crate) fn from_stream(config: BridgeConfig, stream: TcpStream) -> Option<Self> {
        stream
            .set_nodelay(true)
            .unwrap_or_else(|e| tracing::debug!("[parent-ipc] set_nodelay failed: {}", e));

        let read_timeout = config.read_timeout;
        let reader_stream = match stream.try_clone() {
            Ok(clone) => clone,
            Err(e) => {
                tracing::error!("[parent-ipc] failed to clone IPC stream: {}", e);
                return None;
            }
        };
        let _ = reader_stream.set_read_timeout(Some(read_timeout));

        let shared = Arc::new(Shared {
            config,
            writer: Mutex::new(Some(stream)),
            handlers: Mutex::new(HashMap::new()),
            next_handler_id: AtomicU64::new(1),
            disconnect_handlers: Mutex::new(Vec::new()),
            handshake_cv: Condvar::new(),
            handshake: Mutex::new(HandshakeState::Pending),
            running: Mutex::new(true),
            reconnect_lock: Mutex::new(()),
        });

        let bridge = Self { shared };
        bridge.spawn_reader(reader_stream);
        Some(bridge)
    }

    fn tcp_connect(config: &BridgeConfig) -> Result<TcpStream, BridgeError> {
        let addr = format!("{}:{}", config.host, config.port);
        let socket = addr
            .parse()
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, format!("{}: {}", addr, e)))?;
        TcpStream::connect_timeout(&socket, config.connect_timeout).map_err(BridgeError::Io)
    }

    fn spawn_reader(&self, stream: TcpStream) {
        let weak = Arc::downgrade(&self.shared);
        if let Err(e) = thread::Builder::new()
            .name("auroraview-parent-ipc".into())
            .spawn(move || reader_loop(weak, stream))
        {
            tracing::error!("[parent-ipc] failed to spawn reader thread: {}", e);
        }
    }

    fn start_handshake(&self) {
        let hello = Message {
            kind: MessageKind::Hello,
            event: None,
            data: json!({ "capabilities": ["event", "command", "ping"] }),
            child_id: self.shared.config.child_id.clone(),
            protocol: Some(PROTOCOL_VERSION),
            accepted: None,
            parent_id: self.shared.config.parent_id.clone(),
            example_name: self.shared.config.example_name.clone(),
            code: None,
            message: None,
            fatal: None,
        };

        if let Err(e) = self.send(&hello) {
            tracing::warn!("[parent-ipc] failed to send hello: {}", e);
        }

        // Sent unconditionally: a pre-protocol parent never answers `hello`
        // but still needs `child:ready` to mark the child as live.
        if self.shared.config.announce_ready {
            let _ = self.send_event(
                READY_EVENT,
                json!({
                    "child_id": self.shared.config.child_id,
                    "example_name": self.shared.config.example_name,
                }),
            );
        }
    }

    /// Send a pre-built frame.
    pub fn send(&self, message: &Message) -> Result<(), BridgeError> {
        let mut line = message.encode()?;
        line.push('\n');

        let mut guard = self.shared.writer.lock().unwrap_or_else(|e| e.into_inner());
        let stream = guard.as_mut().ok_or(BridgeError::NotConnected)?;
        stream.write_all(line.as_bytes())?;
        stream.flush()?;
        Ok(())
    }

    /// Send an event to the parent, stamped with this child's id.
    pub fn send_event(&self, event: &str, data: serde_json::Value) -> Result<(), BridgeError> {
        let message =
            Message::event(event, data).with_child_id(self.shared.config.child_id.clone());
        self.send(&message)
    }

    /// Register a handler for a named inbound event.
    ///
    /// Handlers run on the reader thread; keep them short and non-blocking.
    /// Returns an unsubscribe closure that removes exactly this handler.
    pub fn on_event<F>(&self, event: &str, handler: F) -> impl Fn() + Send + Sync + 'static
    where
        F: Fn(serde_json::Value) + Send + Sync + 'static,
    {
        let key = event.to_string();
        let id = self.shared.next_handler_id.fetch_add(1, Ordering::Relaxed);

        {
            let mut handlers = self
                .shared
                .handlers
                .lock()
                .unwrap_or_else(|e| e.into_inner());
            handlers
                .entry(key.clone())
                .or_default()
                .push((id, Arc::new(handler)));
        }

        let shared = Arc::downgrade(&self.shared);
        move || {
            if let Some(shared) = shared.upgrade() {
                let mut handlers = shared.handlers.lock().unwrap_or_else(|e| e.into_inner());
                let remove_entry = match handlers.get_mut(&key) {
                    Some(list) => {
                        list.retain(|(entry_id, _)| *entry_id != id);
                        list.is_empty()
                    }
                    None => false,
                };
                if remove_entry {
                    handlers.remove(&key);
                }
            }
        }
    }

    /// Convenience wrapper for the `parent:command` event.
    pub fn on_command<F>(&self, handler: F) -> impl Fn() + Send + Sync + 'static
    where
        F: Fn(serde_json::Value) + Send + Sync + 'static,
    {
        self.on_event(COMMAND_EVENT, handler)
    }

    /// Register a callback invoked when the channel drops.
    ///
    /// Hosts use this to decide whether to keep the child alive or exit.
    pub fn on_disconnect<F>(&self, handler: F)
    where
        F: Fn() + Send + Sync + 'static,
    {
        let id = self.shared.next_handler_id.fetch_add(1, Ordering::Relaxed);
        self.shared
            .disconnect_handlers
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .push((id, Arc::new(handler)));
    }

    /// Current handshake state.
    pub fn handshake_state(&self) -> HandshakeState {
        *self
            .shared
            .handshake
            .lock()
            .unwrap_or_else(|e| e.into_inner())
    }

    /// Block until the handshake resolves, or until the deadline elapses.
    ///
    /// On timeout the state is downgraded to [`HandshakeState::Legacy`] and
    /// returned; the channel stays usable either way.
    pub fn wait_for_handshake(&self, timeout: Duration) -> HandshakeState {
        let guard = self
            .shared
            .handshake
            .lock()
            .unwrap_or_else(|e| e.into_inner());

        let (mut guard, _) = self
            .shared
            .handshake_cv
            .wait_timeout_while(guard, timeout, |state| {
                matches!(*state, HandshakeState::Pending)
            })
            .unwrap_or_else(|e| e.into_inner());

        // Still pending means the wait timed out rather than being notified.
        if *guard == HandshakeState::Pending {
            *guard = HandshakeState::Legacy;
            self.shared.handshake_cv.notify_all();
        }

        *guard
    }

    /// `true` while the channel has a live socket.
    pub fn is_connected(&self) -> bool {
        self.shared
            .writer
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .is_some()
    }

    /// `true` while the reader thread should keep running.
    fn is_running(&self) -> bool {
        *self
            .shared
            .running
            .lock()
            .unwrap_or_else(|e| e.into_inner())
    }

    /// Tear the channel down, announcing `child:closing` if configured.
    pub fn disconnect(&self) {
        self.shutdown(self.shared.config.announce_closing);
    }

    fn shutdown(&self, announce_closing: bool) {
        {
            let mut running = self
                .shared
                .running
                .lock()
                .unwrap_or_else(|e| e.into_inner());
            *running = false;
        }

        if announce_closing && self.is_connected() {
            let _ = self.send_event(
                CLOSING_EVENT,
                json!({ "child_id": self.shared.config.child_id }),
            );
        }

        let mut guard = self.shared.writer.lock().unwrap_or_else(|e| e.into_inner());
        if let Some(stream) = guard.take() {
            let _ = stream.shutdown(Shutdown::Both);
        }
        drop(guard);

        self.set_state(HandshakeState::Disconnected);
    }

    fn set_state(&self, state: HandshakeState) {
        {
            let mut guard = self
                .shared
                .handshake
                .lock()
                .unwrap_or_else(|e| e.into_inner());
            *guard = state;
        }
        self.shared.handshake_cv.notify_all();
    }

    /// Handle one inbound frame. Returns `false` when the channel must close.
    fn dispatch(&self, message: Message) -> bool {
        match message.kind {
            MessageKind::HelloAck => {
                let accepted = message.accepted.unwrap_or(true);
                tracing::info!(
                    "[parent-ipc] handshake {}: parent_id={:?} protocol={:?}",
                    if accepted { "accepted" } else { "rejected" },
                    message.parent_id,
                    message.protocol
                );
                self.set_state(if accepted {
                    HandshakeState::Acked
                } else {
                    HandshakeState::Rejected
                });
                accepted
            }
            MessageKind::Error => {
                let code = message.code.unwrap_or(ErrorCode::InternalError);
                let fatal = message.fatal.unwrap_or(false);
                tracing::warn!(
                    "[parent-ipc] error from parent: {} ({}) fatal={}",
                    message.message.as_deref().unwrap_or(""),
                    code,
                    fatal
                );
                if fatal {
                    self.set_state(HandshakeState::Rejected);
                    return false;
                }
                true
            }
            MessageKind::Ping => {
                let pong = Message {
                    kind: MessageKind::Pong,
                    event: None,
                    data: serde_json::Value::Null,
                    child_id: self.shared.config.child_id.clone(),
                    protocol: Some(PROTOCOL_VERSION),
                    accepted: None,
                    parent_id: None,
                    example_name: None,
                    code: None,
                    message: None,
                    fatal: None,
                };
                let _ = self.send(&pong);
                true
            }
            MessageKind::Pong | MessageKind::Hello => true,
            MessageKind::Event => {
                let name = match message.event.clone() {
                    Some(name) => name,
                    None => {
                        tracing::debug!("[parent-ipc] dropping event frame without a name");
                        return true;
                    }
                };

                let handlers: Vec<SharedHandler> = {
                    let guard = self
                        .shared
                        .handlers
                        .lock()
                        .unwrap_or_else(|e| e.into_inner());
                    match guard.get(&name) {
                        Some(list) => list
                            .iter()
                            .map(|(_, handler)| Arc::clone(handler))
                            .collect(),
                        None => Vec::new(),
                    }
                };

                if handlers.is_empty() {
                    tracing::debug!("[parent-ipc] no handler for event '{}'", name);
                    return true;
                }

                for handler in handlers {
                    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                        handler(message.data.clone())
                    }));
                    if result.is_err() {
                        tracing::error!("[parent-ipc] handler for '{}' panicked", name);
                        let _ = self.send(&Message::error(
                            ErrorCode::HandlerError,
                            format!("handler for '{}' panicked", name),
                            false,
                        ));
                    }
                }
                true
            }
            MessageKind::Unknown(kind) => {
                tracing::debug!("[parent-ipc] ignoring unknown frame type '{}'", kind);
                true
            }
        }
    }

    fn notify_disconnected(&self) {
        let handlers: Vec<SharedDisconnectHandler> = {
            let guard = self
                .shared
                .disconnect_handlers
                .lock()
                .unwrap_or_else(|e| e.into_inner());
            guard.iter().map(|(_, h)| Arc::clone(h)).collect()
        };
        for handler in handlers {
            let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| handler()));
        }
    }

    /// Attempt a reconnect while holding [`Shared::reconnect_lock`].
    fn try_reconnect(&self) -> bool {
        let _guard = self
            .shared
            .reconnect_lock
            .lock()
            .unwrap_or_else(|e| e.into_inner());

        if !self.is_running() {
            return false;
        }

        let stream = match Self::tcp_connect(&self.shared.config) {
            Ok(stream) => stream,
            Err(e) => {
                tracing::debug!("[parent-ipc] reconnect attempt failed: {}", e);
                return false;
            }
        };

        let read_timeout = self.shared.config.read_timeout;
        let reader = match stream.try_clone() {
            Ok(clone) => clone,
            Err(e) => {
                tracing::warn!("[parent-ipc] reconnect clone failed: {}", e);
                return false;
            }
        };
        let _ = reader.set_read_timeout(Some(read_timeout));

        {
            let mut writer = self.shared.writer.lock().unwrap_or_else(|e| e.into_inner());
            *writer = Some(stream);
        }
        self.set_state(HandshakeState::Pending);
        self.spawn_reader(reader);
        self.start_handshake();
        tracing::info!("[parent-ipc] reconnected to parent");
        true
    }
}

impl Drop for ParentBridge {
    fn drop(&mut self) {
        // Only the last clone actually tears the channel down.
        if Arc::strong_count(&self.shared) == 1 && self.is_running() {
            self.shutdown(self.shared.config.announce_closing);
        }
    }
}

fn reader_loop(weak: Weak<Shared>, mut stream: TcpStream) {
    let mut frame_reader = FrameReader::new();
    let mut buffer = [0u8; 8192];

    loop {
        let Some(shared) = weak.upgrade() else {
            return;
        };
        let bridge = ParentBridge { shared };

        if !bridge.is_running() {
            return;
        }

        match stream.read(&mut buffer) {
            Ok(0) => {
                tracing::info!("[parent-ipc] parent closed the connection");
                break;
            }
            Ok(n) => {
                frame_reader.push(&buffer[..n]);

                // A peer that never sends a delimiter would otherwise grow the
                // buffer without bound: `next_frame` only reaches its size
                // check once a complete frame has been drained.
                if frame_reader.is_overgrown() {
                    frame_reader.reset();
                    tracing::warn!(
                        "[parent-ipc] discarding overgrown frame (>{} bytes without a delimiter)",
                        MAX_FRAME_BYTES
                    );
                    let _ = bridge.send(&Message::error(
                        ErrorCode::FrameTooLarge,
                        "frame exceeded the 1 MiB limit",
                        false,
                    ));
                }

                let mut keep_going = true;
                while let Some(frame) = frame_reader.next_frame() {
                    match frame {
                        Ok(message) => {
                            if !bridge.dispatch(message) {
                                keep_going = false;
                                break;
                            }
                        }
                        Err(FrameError::BadJson(detail)) => {
                            tracing::warn!("[parent-ipc] discarding bad frame: {}", detail);
                            let _ = bridge.send(&Message::error(ErrorCode::BadJson, detail, false));
                        }
                        Err(FrameError::TooLarge) => {
                            let _ = bridge.send(&Message::error(
                                ErrorCode::FrameTooLarge,
                                "frame exceeded the 1 MiB limit",
                                false,
                            ));
                        }
                    }
                }

                if !keep_going {
                    break;
                }
            }
            Err(e)
                if e.kind() == io::ErrorKind::WouldBlock || e.kind() == io::ErrorKind::TimedOut =>
            {
                continue;
            }
            Err(e) => {
                if bridge.is_running() {
                    tracing::warn!("[parent-ipc] read error: {}", e);
                }
                break;
            }
        }

        // Drop the temporary upgrade so a pending `Drop` can observe the
        // strong count and shut the channel down.
        drop(bridge);
    }

    // Channel is down: release the socket, tell the host, maybe reconnect.
    let Some(shared) = weak.upgrade() else {
        return;
    };
    let bridge = ParentBridge { shared };

    {
        let mut writer = bridge
            .shared
            .writer
            .lock()
            .unwrap_or_else(|e| e.into_inner());
        if let Some(socket) = writer.take() {
            let _ = socket.shutdown(Shutdown::Both);
        }
    }
    {
        let mut state = bridge
            .shared
            .handshake
            .lock()
            .unwrap_or_else(|e| e.into_inner());
        // A refusal closes the transport too. Keep its cause observable after
        // teardown so a waiting caller does not race the reader thread.
        if *state != HandshakeState::Rejected {
            *state = HandshakeState::Disconnected;
        }
    }
    bridge.shared.handshake_cv.notify_all();
    bridge.notify_disconnected();

    if let ReconnectPolicy::Fixed { attempts, interval } = bridge.shared.config.reconnect {
        for _ in 0..attempts {
            if !bridge.is_running() {
                break;
            }
            thread::sleep(interval);
            if bridge.try_reconnect() {
                return;
            }
        }
    }
}
