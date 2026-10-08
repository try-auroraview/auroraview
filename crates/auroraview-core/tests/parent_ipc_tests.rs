//! Integration tests for the parent/child IPC bridge.
//!
//! Each test drives a real [`ParentBridge`] against a small in-process TCP
//! "parent", so handshake, framing, routing and disconnect semantics are all
//! covered without a WebView or an external host.

use std::io::{BufRead, BufReader, Write};
use std::net::{Shutdown, TcpListener, TcpStream};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use auroraview_core::parent_ipc::{
    BridgeConfig, BridgeError, ErrorCode, HandshakeState, MessageKind, ParentBridge,
    ReconnectPolicy, ENV_PARENT_ID, ENV_PARENT_PORT, PROTOCOL_VERSION, UTF8_BOM,
};
use rstest::rstest;
use serde_json::json;

/// A minimal in-process stand-in for a parent host.
///
/// It accepts exactly one connection, records every frame the child sends, and
/// can inject raw lines (including deliberately malformed ones) back.
struct MockParent {
    /// Frames received from the child, in arrival order.
    received: Arc<Mutex<Vec<String>>>,
    /// The accepted socket, used to write frames to the child.
    peer: Arc<Mutex<Option<TcpStream>>>,
    /// Port the listener was bound to.
    port: u16,
}

impl MockParent {
    fn start() -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback listener");
        let port = listener.local_addr().expect("listener addr").port();
        let received: Arc<Mutex<Vec<String>>> = Arc::new(Mutex::new(Vec::new()));
        let peer: Arc<Mutex<Option<TcpStream>>> = Arc::new(Mutex::new(None));

        let sink = Arc::clone(&received);
        let peer_sink = Arc::clone(&peer);
        thread::Builder::new()
            .name("mock-parent".into())
            .spawn(move || {
                let (stream, _) = listener.accept().expect("accept child");
                let read_stream = stream.try_clone().expect("clone stream");
                *peer_sink.lock().unwrap_or_else(|e| e.into_inner()) = Some(stream);

                let mut reader = BufReader::new(read_stream);
                let mut line = String::new();
                loop {
                    line.clear();
                    match reader.read_line(&mut line) {
                        Ok(0) | Err(_) => break,
                        Ok(_) => sink
                            .lock()
                            .unwrap_or_else(|e| e.into_inner())
                            .push(line.trim_end().to_string()),
                    }
                }
            })
            .expect("spawn mock parent");

        Self {
            received,
            peer,
            port,
        }
    }

    /// Wait until the accept thread spawned by [`MockParent::start`] has
    /// published the child's socket.
    ///
    /// `TcpStream::connect` returns as soon as the kernel completes the
    /// handshake, which can happen before that thread has run `accept()` and
    /// stored the peer. Touching the socket too early made [`Self::write_raw`]
    /// panic and [`Self::drop_connection`] silently do nothing, so both wait
    /// here first.
    fn wait_until_connected(&self) {
        let deadline = std::time::Instant::now() + Duration::from_secs(5);
        while std::time::Instant::now() < deadline {
            if self
                .peer
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .is_some()
            {
                return;
            }
            thread::sleep(Duration::from_millis(5));
        }
        panic!("the child never connected within 5s");
    }

    /// Write raw bytes to the child. Used for both well-formed and malformed
    /// frames.
    fn write_raw(&self, bytes: &[u8]) {
        self.wait_until_connected();
        let mut guard = self.peer.lock().unwrap_or_else(|e| e.into_inner());
        let stream = guard.as_mut().expect("child is connected");
        stream.write_all(bytes).expect("write");
        stream.flush().expect("flush");
    }

    /// Write one LF-terminated frame.
    fn send(&self, line: &str) {
        self.write_raw(line.as_bytes());
        self.write_raw(b"\n");
    }

    fn ack(&self, accepted: bool) {
        self.send(&format!(
            r#"{{"type":"hello_ack","protocol":{},"parent_id":"mock","accepted":{}}}"#,
            PROTOCOL_VERSION, accepted
        ));
    }

    fn received(&self) -> Vec<String> {
        self.received
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }

    fn parsed(&self) -> Vec<serde_json::Value> {
        self.received()
            .iter()
            .filter_map(|line| serde_json::from_str(line).ok())
            .collect()
    }

    /// Wait until `predicate` holds, polling every 5 ms.
    fn wait_for<F: Fn(&Self) -> bool>(&self, timeout: Duration, predicate: F) -> bool {
        let deadline = std::time::Instant::now() + timeout;
        while std::time::Instant::now() < deadline {
            if predicate(self) {
                return true;
            }
            thread::sleep(Duration::from_millis(5));
        }
        predicate(self)
    }

    /// Close the connection to simulate the parent going away.
    fn drop_connection(&self) {
        // Without this the `take()` below would silently no-op on a `None`
        // peer, leaving the connection up and the port still bound.
        self.wait_until_connected();
        if let Some(stream) = self.peer.lock().unwrap_or_else(|e| e.into_inner()).take() {
            let _ = stream.shutdown(Shutdown::Both);
        }
    }
}

fn config_for(port: u16) -> BridgeConfig {
    BridgeConfig {
        port,
        child_id: Some("child-1".to_string()),
        parent_id: Some("mock".to_string()),
        example_name: Some("demo".to_string()),
        read_timeout: Duration::from_millis(50),
        ..Default::default()
    }
}

/// Channel-backed probe: `register` wires a handler for `event`, and `rx`
/// receives its payloads so assertions never block the reader thread.
struct Probe {
    rx: Receiver<serde_json::Value>,
}

impl Probe {
    fn register(bridge: &ParentBridge, event: &str) -> (Self, impl Fn() + Send + Sync + 'static) {
        let (tx, rx): (Sender<serde_json::Value>, Receiver<serde_json::Value>) = mpsc::channel();
        let handle = bridge.on_event(event, move |data| {
            let _ = tx.send(data);
        });
        (Self { rx }, handle)
    }

    fn recv(&self) -> serde_json::Value {
        self.rx
            .recv_timeout(Duration::from_secs(5))
            .expect("event did not arrive")
    }
}

#[test]
fn child_sends_hello_then_ready() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    assert!(
        parent.wait_for(Duration::from_secs(5), |p| p.parsed().len() >= 2),
        "expected hello + child:ready, got {:?}",
        parent.received()
    );

    let frames = parent.parsed();
    assert_eq!(frames[0]["type"], json!("hello"));
    assert_eq!(frames[0]["protocol"], json!(PROTOCOL_VERSION));
    assert_eq!(frames[0]["child_id"], json!("child-1"));
    assert_eq!(frames[0]["parent_id"], json!("mock"));
    assert_eq!(frames[1]["event"], json!("child:ready"));

    bridge.disconnect();
}

#[test]
fn handshake_completes_when_parent_acks() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    parent.ack(true);

    assert_eq!(
        bridge.wait_for_handshake(Duration::from_secs(5)),
        HandshakeState::Acked
    );
    bridge.disconnect();
}

#[test]
fn handshake_downgrades_to_legacy_for_a_silent_parent() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    // Gallery today never sends `hello_ack`; the child must stay usable.
    assert_eq!(
        bridge.wait_for_handshake(Duration::from_millis(100)),
        HandshakeState::Legacy
    );
    assert!(bridge.is_connected());

    // Legacy mode still carries traffic in both directions.
    let (probe, _handle) = Probe::register(&bridge, "parent:legacy");
    parent.send(r#"{"event":"parent:legacy","data":{"ok":1}}"#);
    assert_eq!(probe.recv(), json!({"ok": 1}));

    bridge.disconnect();
}

#[rstest]
#[case::rejected_ack(false)]
#[case::fatal_error(true)]
fn handshake_reports_rejection(#[case] fatal: bool) {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    let (tx, rx) = mpsc::channel();
    bridge.on_disconnect(move || {
        let _ = tx.send(());
    });
    if fatal {
        parent.send(r#"{"type":"error","code":"unsupported_protocol","fatal":true}"#);
    } else {
        parent.ack(false);
    }
    rx.recv_timeout(Duration::from_secs(5))
        .expect("rejected channel disconnects");
    assert!(!bridge.is_connected());

    assert_eq!(
        bridge.wait_for_handshake(Duration::from_secs(5)),
        HandshakeState::Rejected
    );
    bridge.disconnect();
}

#[test]
fn events_route_by_name_and_carry_data() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    let (probe, _handle) = Probe::register(&bridge, "parent:ping");

    parent.send(r#"{"type":"event","event":"parent:ping","data":{"nonce":42}}"#);

    assert_eq!(probe.recv(), json!({"nonce": 42}));
    bridge.disconnect();
}

#[test]
fn legacy_frames_without_type_are_events() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    // Gallery sends `{"event": ..., "data": ...}` with no `type` key at all.
    let (probe, _handle) = Probe::register(&bridge, "parent:command");

    parent.send(r#"{"event":"parent:command","data":{"command":"close"}}"#);

    assert_eq!(probe.recv(), json!({"command": "close"}));
    bridge.disconnect();
}

#[test]
fn events_are_stamped_with_the_child_id() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    bridge
        .send_event("child:status", json!({"progress": 50}))
        .expect("send event");

    assert!(parent.wait_for(Duration::from_secs(5), |p| p
        .parsed()
        .iter()
        .any(|f| f["event"] == json!("child:status"))));

    let frame = parent
        .parsed()
        .into_iter()
        .find(|f| f["event"] == json!("child:status"))
        .expect("status frame");
    assert_eq!(frame["child_id"], json!("child-1"));
    assert_eq!(frame["data"], json!({"progress": 50}));

    bridge.disconnect();
}

#[test]
fn ping_is_answered_with_pong() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    parent.send(r#"{"type":"ping"}"#);

    assert!(
        parent.wait_for(Duration::from_secs(5), |p| p
            .parsed()
            .iter()
            .any(|f| f["type"] == json!("pong"))),
        "expected a pong, got {:?}",
        parent.received()
    );
    bridge.disconnect();
}

#[test]
fn malformed_frame_is_reported_and_the_channel_survives() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    parent.send("{not json}");

    assert!(
        parent.wait_for(Duration::from_secs(5), |p| p
            .parsed()
            .iter()
            .any(|f| f["code"] == json!(ErrorCode::BadJson.as_str()))),
        "expected a bad_json error frame, got {:?}",
        parent.received()
    );

    // The channel must still work afterwards.
    let (probe, _handle) = Probe::register(&bridge, "after:bad");
    parent.send(r#"{"type":"event","event":"after:bad","data":1}"#);
    assert_eq!(probe.recv(), json!(1));

    bridge.disconnect();
}

#[test]
fn unknown_frame_types_are_ignored() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    parent.send(r#"{"type":"from_the_future","payload":1}"#);

    let (probe, _handle) = Probe::register(&bridge, "after:unknown");
    parent.send(r#"{"type":"event","event":"after:unknown","data":2}"#);

    assert_eq!(probe.recv(), json!(2));
    bridge.disconnect();
}

#[test]
fn leading_bom_does_not_break_the_handshake() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    // PowerShell and .NET StreamWriter emit a UTF-8 BOM before the first frame.
    parent.write_raw(&UTF8_BOM);
    parent.send(r#"{"type":"hello_ack","protocol":1,"accepted":true}"#);

    assert_eq!(
        bridge.wait_for_handshake(Duration::from_secs(5)),
        HandshakeState::Acked,
        "a BOM before the first frame must not break the handshake"
    );
    bridge.disconnect();
}

#[test]
fn unsubscribe_removes_only_its_own_handler() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    let (keep_tx, keep_rx) = mpsc::channel();
    let (drop_tx, drop_rx) = mpsc::channel();

    let _keep = bridge.on_event("multi", move |data| {
        let _ = keep_tx.send(data);
    });
    let unsubscribe = bridge.on_event("multi", move |data| {
        let _ = drop_tx.send(data);
    });
    unsubscribe();

    parent.send(r#"{"type":"event","event":"multi","data":{"n":1}}"#);

    assert_eq!(
        keep_rx.recv_timeout(Duration::from_secs(5)).expect("kept"),
        json!({"n": 1})
    );
    assert!(
        drop_rx.recv_timeout(Duration::from_millis(200)).is_err(),
        "unsubscribed handler must not fire"
    );

    bridge.disconnect();
}

#[test]
fn disconnect_announces_closing_and_marks_state() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    bridge.disconnect();

    assert!(parent.wait_for(Duration::from_secs(5), |p| p
        .parsed()
        .iter()
        .any(|f| f["event"] == json!("child:closing"))));
    assert!(!bridge.is_connected());
    assert_eq!(bridge.handshake_state(), HandshakeState::Disconnected);
}

#[test]
fn only_the_last_clone_tears_the_channel_down() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    let clone = bridge.clone();
    drop(clone);
    assert!(
        bridge.is_connected(),
        "dropping a non-last clone must keep the channel open"
    );

    drop(bridge);
    assert!(parent.wait_for(Duration::from_secs(5), |p| p
        .parsed()
        .iter()
        .any(|f| f["event"] == json!("child:closing"))));
}

#[test]
fn disconnect_callback_fires_when_the_parent_drops_the_link() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    let (tx, rx) = mpsc::channel::<()>();
    bridge.on_disconnect(move || {
        let _ = tx.send(());
    });

    parent.drop_connection();

    rx.recv_timeout(Duration::from_secs(5))
        .expect("disconnect callback");
    assert_eq!(bridge.handshake_state(), HandshakeState::Disconnected);
}

#[test]
fn sending_after_disconnect_reports_not_connected() {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    bridge.disconnect();

    match bridge.send_event("late", json!(null)) {
        Err(BridgeError::NotConnected) => {}
        Err(other) => panic!("expected NotConnected, got {other}"),
        Ok(()) => panic!("expected send after disconnect to fail"),
    }
}

#[test]
fn connect_fails_fast_on_a_closed_port() {
    // Port 1 on loopback is not listening; the connect attempt must fail
    // within the configured timeout rather than hanging.
    let cfg = BridgeConfig {
        port: 1,
        connect_timeout: Duration::from_millis(300),
        ..config_for(1)
    };

    let started = std::time::Instant::now();
    let result = ParentBridge::connect_with_config(cfg);
    assert!(result.is_err(), "connect to a closed port must fail");
    assert!(
        started.elapsed() < Duration::from_secs(5),
        "connect must respect its timeout"
    );
}

#[test]
fn reconnect_policy_reconnects_after_the_link_drops() {
    let parent = MockParent::start();
    let port = parent.port;

    // The mock parent only accepts one connection. After it is dropped the
    // child's retry hit nothing until this port is bound again, which is
    // exactly what a restarted parent looks like.
    let cfg = BridgeConfig {
        reconnect: ReconnectPolicy::Fixed {
            attempts: 10,
            interval: Duration::from_millis(50),
        },
        announce_closing: false,
        ..config_for(port)
    };

    let bridge = ParentBridge::connect_with_config(cfg).expect("connect");
    parent.drop_connection();

    // Give the reader thread time to notice the drop before rebinding.
    thread::sleep(Duration::from_millis(100));
    let listener = TcpListener::bind(("127.0.0.1", port)).expect("rebind port");

    let (tx, rx) = mpsc::channel::<()>();
    thread::spawn(move || {
        if listener.accept().is_ok() {
            let _ = tx.send(());
        }
    });

    assert!(
        rx.recv_timeout(Duration::from_secs(10)).is_ok(),
        "child should reconnect once the parent is back"
    );
    bridge.disconnect();
}

#[rstest]
#[case("parent:ping")]
#[case("custom:event")]
#[case("child:from_parent")]
fn routing_is_exact_per_event_name(#[case] name: &str) {
    let parent = MockParent::start();
    let bridge = ParentBridge::connect_with_config(config_for(parent.port)).expect("connect");

    let (probe, _handle) = Probe::register(&bridge, name);

    parent.send(&format!(
        r#"{{"type":"event","event":"{name}","data":{{"ok":true}}}}"#
    ));

    assert_eq!(probe.recv(), json!({"ok": true}));

    bridge.disconnect();
}

#[test]
fn env_driven_child_info_gates_connection() {
    // ChildInfo parsing is covered in-crate; here we only assert the invariant
    // the CLI depends on: a missing port never yields a bridge.
    let info = auroraview_core::parent_ipc::ChildInfo {
        is_child: true,
        parent_id: Some("gallery".to_string()),
        child_id: Some("c1".to_string()),
        example_name: None,
        parent_port: None,
        parent_hwnd: None,
    };
    assert!(!info.can_connect());

    // The env contract itself must keep the documented names.
    assert_eq!(ENV_PARENT_ID, "AURORAVIEW_PARENT_ID");
    assert_eq!(ENV_PARENT_PORT, "AURORAVIEW_PARENT_PORT");
}

#[test]
fn message_kind_wire_spellings_match_the_spec() {
    assert_eq!(MessageKind::Hello.as_str(), "hello");
    assert_eq!(MessageKind::HelloAck.as_str(), "hello_ack");
    assert_eq!(MessageKind::Event.as_str(), "event");
    assert_eq!(MessageKind::Error.as_str(), "error");
    assert_eq!(MessageKind::Ping.as_str(), "ping");
    assert_eq!(MessageKind::Pong.as_str(), "pong");
}
