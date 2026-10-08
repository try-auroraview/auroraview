# -*- coding: utf-8 -*-
"""WebSocket Bridge for DCC and Web application integration.

This module provides a generic WebSocket server that can be used to integrate
AuroraView with any DCC tool or web application that supports WebSocket communication.

Example:
    >>> from auroraview import WebView, Bridge
    >>>
    >>> # Create Bridge with decorator API
    >>> bridge = Bridge(port=9001)
    >>>
    >>> @bridge.on('layer_created')
    >>> async def handle_layer(data, client):
    ...     print(f"Layer created: {data}")
    ...     return {"status": "ok"}
    >>>
    >>> # Create WebView with Bridge
    >>> webview = WebView.create("My Tool", bridge=bridge)
    >>> webview.show()
"""

import asyncio
import atexit
import json
import logging
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Set

try:
    import websockets

    # websockets 14.0+ deprecates the legacy server API
    # Use the new asyncio API which doesn't require WebSocketServerProtocol
    WEBSOCKETS_AVAILABLE = True

    # For type hints, use a Protocol-compatible type
    if TYPE_CHECKING:
        # Import for type checking only to avoid deprecation warnings at runtime
        try:
            from websockets.asyncio.server import ServerConnection

            WebSocketConnection = ServerConnection
        except ImportError:
            # Fallback for older websockets versions
            from websockets.server import WebSocketServerProtocol

            WebSocketConnection = WebSocketServerProtocol
except ImportError:
    WEBSOCKETS_AVAILABLE = False

logger = logging.getLogger(__name__)


class Bridge:
    """WebSocket Bridge for DCC and Web application integration.

    This class provides a WebSocket server that can communicate with external
    applications (Photoshop, Maya, Blender, etc.) and automatically integrates
    with AuroraView WebView for bidirectional communication.

    Args:
        host: WebSocket server host (default: "localhost")
        port: WebSocket server port (0 = auto-allocate, default: 9001)
        auto_start: Auto-start server on creation (default: False)
        protocol: Message protocol - 'json' or 'msgpack' (default: 'json')
        service_discovery: Enable service discovery (default: False)
        discovery_port: HTTP discovery port (default: 9000)
        enable_mdns: Enable mDNS service discovery (default: True)

    Example:
        >>> # Auto-allocate port with service discovery
        >>> bridge = Bridge(port=0, service_discovery=True)
        >>> print(f"Bridge port: {bridge.port}")
        >>>
        >>> @bridge.on('handshake')
        >>> async def handle_handshake(data, client):
        ...     return {"server": "auroraview", "version": "1.0.0"}
        >>>
        >>> # Start manually
        >>> await bridge.start()
        >>>
        >>> # Or use with WebView (auto-start)
        >>> webview = WebView.create("Tool", bridge=bridge)
        >>> webview.show()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9001,
        *,
        auto_start: bool = False,
        protocol: str = "json",
        service_discovery: bool = False,
        discovery_port: int = 9000,
        enable_mdns: bool = True,
    ):
        """Initialize the Bridge.

        Args:
            host: WebSocket server host
            port: WebSocket server port (0 = auto-allocate)
            auto_start: Auto-start server on creation
            protocol: Message protocol ('json' or 'msgpack')
            service_discovery: Enable service discovery
            discovery_port: HTTP discovery port
            enable_mdns: Enable mDNS service discovery
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError(
                "websockets library is required for Bridge. Install with: pip install websockets"
            )

        # Service discovery
        self._service_discovery = None
        if service_discovery:
            try:
                from ._core import ServiceDiscovery

                self._service_discovery = ServiceDiscovery(
                    bridge_port=port,
                    discovery_port=discovery_port,
                    enable_mdns=enable_mdns,
                )
                # Use allocated port
                port = self._service_discovery.bridge_port
                logger.info(
                    f"Service discovery enabled: bridge_port={port}, discovery_port={discovery_port}"
                )
            except ImportError as e:
                logger.warning(f"Service discovery not available: {e}")
            except Exception as e:
                logger.error(f"Failed to initialize service discovery: {e}")

        self.host = host
        self.port = port
        self.protocol = protocol
        self._clients: Set[Any] = set()  # WebSocket connections (ServerConnection in 14.0+)
        self._handlers: Dict[str, Callable] = {}
        self._webview_callback: Optional[Callable] = None
        self._server = None
        self._server_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._state_lock = threading.RLock()
        self._starting = False
        self._stop_event: Optional[asyncio.Event] = None
        self._client_tasks: Set[asyncio.Task] = set()
        self._startup_event = threading.Event()
        self._startup_error: Optional[BaseException] = None
        self._background_done: Optional[Future] = None
        self._exit_hook = self.stop_background
        self._atexit_registered = False

        logger.info(f"Bridge initialized: {self.host}:{self.port} (protocol={self.protocol})")

        if auto_start:
            self.start_background()

    def on(self, action: str) -> Callable:
        """Decorator to register a message handler.

        Args:
            action: Action name (e.g., 'layer_created', 'handshake')

        Returns:
            Decorator function

        Example:
            >>> @bridge.on('layer_created')
            >>> async def handle_layer(data, client):
            ...     print(f"Layer: {data}")
            ...     return {"status": "ok"}
        """

        def decorator(func: Callable) -> Callable:
            self.register_handler(action, func)
            return func

        return decorator

    def register_handler(self, action: str, handler: Callable):
        """Register a message handler.

        Args:
            action: Action name
            handler: Async function(data, client) -> response
                    - data: Message data dict
                    - client: WebSocket client connection
                    - return: Response dict (optional)
        """
        self._handlers[action] = handler
        logger.info(f"Registered handler for action: '{action}'")

    def set_webview_callback(self, callback: Callable):
        """Set callback to communicate with WebView UI.

        This is called automatically when Bridge is associated with a WebView.

        Args:
            callback: Function(action, data, result) to call when UI needs update
        """
        self._webview_callback = callback
        logger.debug("WebView callback registered")

    async def start(self):
        """Start the WebSocket server (blocking).

        This method blocks until the server is stopped. Use start_background()
        for non-blocking operation.

        Example:
            >>> await bridge.start()  # Returns after stop() or cancellation
        """
        with self._state_lock:
            if self._server_task is not None:
                raise RuntimeError("Bridge is already starting or running")
            if self._starting and self._thread is not threading.current_thread():
                raise RuntimeError("Bridge is already starting")
            self._starting = True
            self._loop = asyncio.get_running_loop()
            self._server_task = asyncio.current_task()
            self._stop_event = asyncio.Event()
            self._startup_error = None
        logger.info("Starting Bridge on %s:%s", self.host, self.port)
        try:
            self._server = await websockets.serve(
                self._handle_client, self.host, self.port, close_timeout=1
            )
            if self.port == 0:
                self.port = self._server.sockets[0].getsockname()[1]
            if self._service_discovery:
                try:
                    self._service_discovery.start(
                        {
                            "service": "AuroraView Bridge",
                            "version": "1.0.0",
                            "protocol": self.protocol,
                        }
                    )
                except Exception as exc:
                    logger.error("Failed to start service discovery: %s", exc)
            self._is_running = True
            self._starting = False
            self._startup_event.set()
            logger.info("WebSocket server listening on ws://%s:%s", self.host, self.port)
            await self._stop_event.wait()
        except BaseException as exc:
            self._startup_error = exc
            raise
        finally:
            self._is_running = False
            try:
                if self._server is not None:
                    self._server.close()
                tasks = tuple(self._client_tasks)
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                if self._server is not None:
                    await self._server.wait_closed()
            finally:
                if self._service_discovery:
                    try:
                        self._service_discovery.stop()
                    except Exception as exc:
                        logger.error("Failed to stop service discovery: %s", exc)
                self._server = None
                self._server_task = None
                self._stop_event = None
                self._starting = False
                self._startup_event.set()

    def start_background(self):
        """Start the WebSocket server in a background thread (non-blocking).

        This is the recommended way to start the Bridge when using with WebView.
        stop() joins the owned daemon thread. An exit hook also closes it when
        an application exits without an explicit stop().

        Example:
            >>> bridge = Bridge(port=9001)
            >>> bridge.start_background()  # Returns immediately
            >>> # Server is now running in background
        """

        def _run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            try:
                loop.run_until_complete(self.start())
            except BaseException as exc:
                self._startup_error = exc
            finally:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
                asyncio.set_event_loop(None)
                self._unregister_exit_hook()
                self._startup_event.set()
                self._background_done.set_result(None)

        with self._state_lock:
            if self._is_running or self._starting:
                return
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("Bridge background thread is still stopping")
            self._starting = True
            self._startup_event.clear()
            self._startup_error = None
            self._background_done = Future()
            self._thread = threading.Thread(
                target=_run_server, name="AuroraViewBridge", daemon=True
            )
            atexit.register(self._exit_hook)
            self._atexit_registered = True
            try:
                self._thread.start()
            except BaseException:
                self._starting = False
                self._unregister_exit_hook()
                raise
        if not self._startup_event.wait(3):
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._request_stop)
            raise TimeoutError("Bridge did not start within three seconds")
        if self._startup_error is not None:
            self._thread.join(3)
            raise self._startup_error

    def _unregister_exit_hook(self):
        with self._state_lock:
            if self._atexit_registered:
                atexit.unregister(self._exit_hook)
                self._atexit_registered = False

    def stop_background(self, timeout: float = 3.0):
        """Synchronously close an owned background server with a bounded join."""
        if not 0 < timeout <= 5:
            raise ValueError("Bridge stop timeout must be within (0, 5] seconds")
        thread = self._thread
        if thread is None or not thread.is_alive():
            self._unregister_exit_hook()
            return
        if thread is threading.current_thread():
            raise RuntimeError("Use await stop() from the Bridge event loop")
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._request_stop)
        thread.join(timeout)
        if thread.is_alive():
            raise TimeoutError("Bridge background thread did not exit")
        self._unregister_exit_hook()

    def _request_stop(self):
        """Request teardown on the owner loop, including an unfinished bind."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._server is not None:
            self._server.close()
        elif self._server_task is not None:
            self._server_task.cancel()

    async def _stop_on_loop(self):
        task = self._server_task
        self._request_stop()
        # A handler cannot await the server that is waiting for that handler.
        if task is not None and asyncio.current_task() not in self._client_tasks:
            await asyncio.shield(task)

    async def stop(self):
        """Stop the WebSocket server.

        Closes the listener and clients, and joins an owned background thread.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            if self._thread is not None and self._thread is not threading.current_thread():
                self._thread.join(0.25)
                if self._thread.is_alive():
                    raise TimeoutError("Bridge background thread did not exit")
            return
        if loop is asyncio.get_running_loop():
            await self._stop_on_loop()
        elif self._thread is not None and self._thread.is_alive():
            loop.call_soon_threadsafe(self._request_stop)
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(self._background_done)), 5)
            self._thread.join(0.25)
            if self._thread.is_alive():
                raise TimeoutError("Bridge background thread did not exit")
        else:
            future = asyncio.run_coroutine_threadsafe(self._stop_on_loop(), loop)
            await asyncio.wait_for(asyncio.wrap_future(future), 5)
        logger.info("Bridge stopped")

    async def _handle_client(self, websocket: Any):
        """Handle a new client connection.

        Args:
            websocket: WebSocket connection (ServerConnection in websockets 14.0+)
        """
        client_addr = websocket.remote_address
        logger.info(f"New client connected: {client_addr}")

        self._clients.add(websocket)
        task = asyncio.current_task()
        self._client_tasks.add(task)

        try:
            async for message in websocket:
                await self._process_message(message, websocket)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected: {client_addr}")
        except Exception as e:
            logger.error(f"Error handling client {client_addr}: {e}", exc_info=True)
        finally:
            self._clients.discard(websocket)
            self._client_tasks.discard(task)
            logger.info(f"Client removed: {client_addr} (total: {len(self._clients)})")

    async def _process_message(self, message: str, websocket: Any):
        """Process incoming message from client.

        Args:
            message: JSON message string
            websocket: WebSocket connection (ServerConnection in websockets 14.0+)
        """
        try:
            # Decode message
            if self.protocol == "json":
                data = json.loads(message)
            else:
                raise ValueError(f"Unsupported protocol: {self.protocol}")

            action = data.get("action")
            logger.info(f"Received: {action}")
            logger.debug(f"Message data: {data}")

            # Route to handler
            if action in self._handlers:
                handler = self._handlers[action]
                result = await handler(data, websocket)

                # Send response back to client
                if result:
                    await self.send(websocket, result)

                # Notify WebView UI if callback is set
                if self._webview_callback:
                    self._webview_callback(action, data, result)
            else:
                logger.warning(f"⚠️  No handler registered for action: {action}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    async def send(self, websocket: Any, data: Dict[str, Any]):
        """Send message to a specific client.

        Args:
            websocket: Target WebSocket connection (ServerConnection in websockets 14.0+)
            data: Data to send (will be JSON serialized)
        """
        try:
            if self.protocol == "json":
                message = json.dumps(data)
            else:
                raise ValueError(f"Unsupported protocol: {self.protocol}")

            await websocket.send(message)
            logger.info(f"Sent to client: {data.get('action', 'unknown')}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def broadcast(self, data: Dict[str, Any]):
        """Broadcast message to all connected clients.

        Args:
            data: Data to broadcast (will be JSON serialized)
        """
        if not self._clients:
            logger.warning("No clients connected to broadcast to")
            return

        if self.protocol == "json":
            message = json.dumps(data)
        else:
            raise ValueError(f"Unsupported protocol: {self.protocol}")

        # Send to all clients concurrently
        await asyncio.gather(
            *[client.send(message) for client in self._clients], return_exceptions=True
        )

        logger.info(f"Broadcast to {len(self._clients)} clients: {data.get('action', 'unknown')}")

    def execute_command(self, command: str, params: Dict[str, Any] = None):
        """Send command to all clients (non-blocking).

        This is a convenience method that broadcasts a command to all clients
        without blocking. Useful for sending commands from synchronous code.

        Args:
            command: Command name
            params: Command parameters

        Example:
            >>> bridge.execute_command('create_layer', {'name': 'New Layer'})
        """
        data = {
            "type": "request",
            "action": "execute_command",
            "data": {"command": command, "params": params or {}},
        }

        # Schedule broadcast in the event loop
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(data), self._loop)
        else:
            logger.warning("Bridge event loop not running, cannot execute command")

    @property
    def clients(self) -> Set[Any]:
        """Get set of connected clients (ServerConnection in websockets 14.0+)."""
        return self._clients

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._is_running

    @property
    def service_discovery(self):
        """Get the service discovery instance (if enabled).

        Returns:
            ServiceDiscovery instance or None
        """
        return self._service_discovery

    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)

    def __repr__(self) -> str:
        """String representation."""
        status = "running" if self._is_running else "stopped"
        return f"Bridge(ws://{self.host}:{self.port}, {status}, clients={self.client_count})"
