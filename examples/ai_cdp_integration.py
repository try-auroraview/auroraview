# -*- coding: utf-8 -*-
"""AI Agent CDP Integration Demo.

This example demonstrates how to use AuroraView with AI agents
via Chrome DevTools Protocol (CDP) for automated testing and
AI-powered interactions.

Features:
    - CDP-enabled WebView for external tool access
    - Integration with browser-use AI automation
    - Direct CDP client for custom automation
    - MCP server integration examples

Usage:
    # Run with CDP enabled (default port 9222)
    python examples/ai_cdp_integration.py

    # Custom CDP port
    python examples/ai_cdp_integration.py --cdp-port 9223

    # Run browser-use automation test
    python examples/ai_cdp_integration.py --test-browser-use

    # Run CDP client demo
    python examples/ai_cdp_integration.py --test-cdp-client

Requirements:
    pip install auroraview httpx websockets
    pip install browser-use langchain-openai  # For browser-use test

Signed-off-by: Hal Long <hal.long@outlook.com>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import threading
import time
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# HTML content for the demo app
DEMO_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Agent CDP Demo</title>
    <style>
        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --accent: #0f3460;
            --text: #eaeaea;
            --highlight: #e94560;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text);
            min-height: 100vh;
            padding: 40px;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
        }

        h1 {
            font-size: 2.5rem;
            margin-bottom: 1rem;
            background: linear-gradient(90deg, var(--highlight), #ff6b6b);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: var(--bg-secondary);
            border-radius: 20px;
            margin-bottom: 2rem;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #4caf50;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .card {
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }

        .card h2 {
            font-size: 1.25rem;
            margin-bottom: 1rem;
            color: var(--highlight);
        }

        .form-group {
            margin-bottom: 1rem;
        }

        label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 500;
        }

        input, textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid var(--accent);
            border-radius: 8px;
            background: var(--bg-primary);
            color: var(--text);
            font-size: 1rem;
        }

        input:focus, textarea:focus {
            outline: none;
            border-color: var(--highlight);
        }

        button {
            padding: 12px 24px;
            background: var(--highlight);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.2s;
        }

        button:hover {
            background: #ff6b6b;
            transform: translateY(-2px);
        }

        .output {
            background: var(--bg-primary);
            border-radius: 8px;
            padding: 16px;
            font-family: monospace;
            min-height: 100px;
            white-space: pre-wrap;
        }

        .api-list {
            list-style: none;
        }

        .api-list li {
            padding: 8px 12px;
            background: var(--bg-primary);
            border-radius: 6px;
            margin-bottom: 8px;
            font-family: monospace;
        }

        .actions {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AI Agent CDP Demo</h1>

        <div class="status-badge">
            <span class="status-dot"></span>
            <span id="status">CDP Ready - Port <span id="cdp-port">9222</span></span>
        </div>

        <div class="card">
            <h2>API Test</h2>
            <div class="form-group">
                <label for="message">Message:</label>
                <input type="text" id="message" placeholder="Enter a message to echo...">
            </div>
            <div class="actions">
                <button onclick="testEcho()">Test Echo API</button>
                <button onclick="testAdd()">Test Add API</button>
                <button onclick="getSystemInfo()">Get System Info</button>
            </div>
        </div>

        <div class="card">
            <h2>Output</h2>
            <div class="output" id="output">Ready for AI agent interaction...</div>
        </div>

        <div class="card">
            <h2>Available APIs</h2>
            <ul class="api-list" id="api-list">
                <li>api.echo(message: str) -> str</li>
                <li>api.add(a: int, b: int) -> int</li>
                <li>api.get_system_info() -> dict</li>
                <li>api.multiply(x: float, y: float) -> float</li>
            </ul>
        </div>

        <div class="card">
            <h2>CDP Commands</h2>
            <p>Connect to this WebView using CDP:</p>
            <ul class="api-list">
                <li>curl http://127.0.0.1:9222/json/version</li>
                <li>curl http://127.0.0.1:9222/json/list</li>
            </ul>
        </div>
    </div>

    <script>
        // Wait for AuroraView bridge
        function waitForBridge() {
            return new Promise((resolve) => {
                if (window.auroraview) {
                    resolve();
                } else {
                    window.addEventListener('auroraviewready', resolve);
                }
            });
        }

        function log(message) {
            const output = document.getElementById('output');
            const timestamp = new Date().toLocaleTimeString();
            output.textContent = `[${timestamp}] ${message}\\n` + output.textContent;
        }

        async function testEcho() {
            await waitForBridge();
            const message = document.getElementById('message').value || 'Hello from AI!';
            try {
                const result = await window.auroraview.api.echo(message);
                log(`Echo result: ${result}`);
            } catch (e) {
                log(`Error: ${e.message}`);
            }
        }

        async function testAdd() {
            await waitForBridge();
            try {
                const result = await window.auroraview.api.add(10, 20);
                log(`Add result: 10 + 20 = ${result}`);
            } catch (e) {
                log(`Error: ${e.message}`);
            }
        }

        async function getSystemInfo() {
            await waitForBridge();
            try {
                const result = await window.auroraview.api.get_system_info();
                log(`System Info: ${JSON.stringify(result, null, 2)}`);
            } catch (e) {
                log(`Error: ${e.message}`);
            }
        }

        // Initialize
        waitForBridge().then(() => {
            log('AuroraView bridge connected!');
            // Store API methods for MCP discovery
            window.__auroraview_api_methods = ['echo', 'add', 'get_system_info', 'multiply'];
        });
    </script>
</body>
</html>
"""


class CDPClient:
    """Simple CDP client for demonstration."""

    def __init__(self, port: int = 9222):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"

    async def get_version(self) -> dict[str, Any]:
        """Get browser version info."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/json/version")
            return resp.json()

    async def get_pages(self) -> list[dict[str, Any]]:
        """Get list of pages/targets."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/json/list")
            return resp.json()

    async def evaluate(self, ws_url: str, expression: str) -> Any:
        """Evaluate JavaScript in page."""
        import websockets

        async with websockets.connect(ws_url) as ws:
            # Send evaluate command
            msg = {
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "returnByValue": True,
                },
            }
            await ws.send(json.dumps(msg))

            # Wait for response
            response = await ws.recv()
            data = json.loads(response)

            if "result" in data and "result" in data["result"]:
                return data["result"]["result"].get("value")
            return data

    async def screenshot(self, ws_url: str) -> bytes:
        """Take screenshot of page."""
        import base64

        import websockets

        async with websockets.connect(ws_url) as ws:
            msg = {"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png"}}
            await ws.send(json.dumps(msg))

            response = await ws.recv()
            data = json.loads(response)

            if "result" in data and "data" in data["result"]:
                return base64.b64decode(data["result"]["data"])
            raise RuntimeError("Failed to capture screenshot")


async def wait_for_cdp(port: int, timeout: float = 30.0) -> bool:
    """Wait for CDP to be available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://127.0.0.1:{port}/json/version",
                    timeout=1.0,
                )
                if resp.status_code == 200:
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


async def test_cdp_client(port: int):
    """Test CDP client functionality."""
    logger.info(f"Testing CDP client on port {port}...")

    client = CDPClient(port)

    # Get version
    version = await client.get_version()
    logger.info(f"Browser: {version.get('Browser', 'Unknown')}")
    logger.info(f"Protocol: {version.get('Protocol-Version', 'Unknown')}")

    # Get pages
    pages = await client.get_pages()
    logger.info(f"Found {len(pages)} page(s)")

    if pages:
        page = pages[0]
        ws_url = page.get("webSocketDebuggerUrl")
        logger.info(f"Page: {page.get('title', 'Untitled')}")
        logger.info(f"URL: {page.get('url', 'N/A')}")

        if ws_url:
            # Evaluate JavaScript
            title = await client.evaluate(ws_url, "document.title")
            logger.info(f"Document title: {title}")

            # Take screenshot
            screenshot = await client.screenshot(ws_url)
            screenshot_path = "cdp_screenshot.png"
            with open(screenshot_path, "wb") as f:
                f.write(screenshot)
            logger.info(f"Screenshot saved to {screenshot_path}")


async def test_browser_use(port: int):
    """Test browser-use integration."""
    try:
        from browser_use import Agent, Browser
        from browser_use.browser.browser import BrowserConfig
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.error("browser-use not installed. Run: pip install browser-use langchain-openai")
        return

    logger.info(f"Testing browser-use integration on port {port}...")

    # Connect to AuroraView via CDP
    browser = Browser(
        config=BrowserConfig(
            cdp_url=f"http://127.0.0.1:{port}",
            headless=False,
        )
    )

    agent = Agent(
        task="""
        1. Find the input field with id "message"
        2. Type "Hello from browser-use!"
        3. Click the "Test Echo API" button
        4. Report what appears in the output section
        """,
        llm=ChatOpenAI(model="gpt-4o"),
        browser=browser,
    )

    result = await agent.run()
    logger.info(f"browser-use result: {result}")


def run_webview(port: int, ready_event: threading.Event):
    """Run the WebView in a separate thread."""
    import platform

    from auroraview import AuroraView

    class DemoApp(AuroraView):
        def __init__(self):
            super().__init__(
                html=DEMO_HTML,
                title="AI Agent CDP Demo",
                width=900,
                height=700,
                debug=True,
                devtools_port=port,
                api=self,
            )

        def echo(self, message: str) -> str:
            """Echo the message back."""
            return f"Echo: {message}"

        def add(self, a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        def multiply(self, x: float, y: float) -> float:
            """Multiply two numbers."""
            return x * y

        def get_system_info(self) -> dict[str, Any]:
            """Get system information."""
            return {
                "platform": platform.system(),
                "python_version": platform.python_version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            }

        def on_ready(self):
            """Called when WebView is ready."""
            logger.info("WebView ready!")
            ready_event.set()

    app = DemoApp()
    app.run()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="AI Agent CDP Integration Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run demo with default CDP port
    python ai_cdp_integration.py

    # Custom CDP port
    python ai_cdp_integration.py --cdp-port 9223

    # Test CDP client only
    python ai_cdp_integration.py --test-cdp-client

    # Test browser-use integration
    python ai_cdp_integration.py --test-browser-use

Connect with AI Tools:
    - MCP: via dcc-mcp-core gateway (see try-auroraview/auroraview#364)
    - browser-use: pip install browser-use
    - chrome-devtools MCP: npx @anthropic/mcp-chrome-devtools
""",
    )
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=9222,
        help="CDP remote debugging port (default: 9222)",
    )
    parser.add_argument(
        "--test-cdp-client",
        action="store_true",
        help="Run CDP client test after WebView is ready",
    )
    parser.add_argument(
        "--test-browser-use",
        action="store_true",
        help="Run browser-use automation test",
    )
    parser.add_argument(
        "--no-webview",
        action="store_true",
        help="Skip starting WebView (assume already running)",
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    print("=" * 60)
    print("AI Agent CDP Integration Demo")
    print("=" * 60)
    print()
    print(f"CDP Port: {args.cdp_port}")
    print(f"CDP URL: http://127.0.0.1:{args.cdp_port}")
    print()
    print("Connect with:")
    print(f"  curl http://127.0.0.1:{args.cdp_port}/json/version")
    print(f"  curl http://127.0.0.1:{args.cdp_port}/json/list")
    print()
    print("MCP:")
    print("  auroraview now plugs into dcc-mcp-core's gateway; see")
    print("  https://github.com/try-auroraview/auroraview/issues/364 for wiring.")
    print()

    ready_event = threading.Event()

    if not args.no_webview:
        # Start WebView in background thread
        webview_thread = threading.Thread(
            target=run_webview,
            args=(args.cdp_port, ready_event),
            daemon=True,
        )
        webview_thread.start()

        # Wait for WebView to be ready
        print("Starting WebView...")
        if not ready_event.wait(timeout=30):
            logger.error("Timeout waiting for WebView")
            sys.exit(1)

    # Wait for CDP to be available
    print("Waiting for CDP...")
    if not asyncio.run(wait_for_cdp(args.cdp_port)):
        logger.error("CDP not available")
        sys.exit(1)

    print(f"CDP ready on port {args.cdp_port}")
    print()

    # Run tests if requested
    if args.test_cdp_client:
        asyncio.run(test_cdp_client(args.cdp_port))

    if args.test_browser_use:
        asyncio.run(test_browser_use(args.cdp_port))

    if not args.no_webview:
        print("WebView running. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nExiting...")


if __name__ == "__main__":
    main()
