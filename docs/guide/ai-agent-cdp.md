# AI Agent & CDP Integration

> ⚠️ **The standalone `auroraview-mcp` Python package has been retired.**
> AuroraView now exposes itself to agents as a first-class DCC adapter through
> [`dcc-mcp-core`](https://github.com/loonghao/dcc-mcp-core)'s gateway + skills
> pipeline — see the realignment epic [#364](https://github.com/try-auroraview/auroraview/issues/364)
> for status. The `pip install auroraview-mcp` / `uvx auroraview-mcp` instructions
> below refer to the old architecture and are kept only as reference while the
> adapter crate (`crates/auroraview-mcp`) is still landing. For the new wiring,
> track issues #365–#368.

AuroraView provides comprehensive AI Agent capabilities and Chrome DevTools Protocol (CDP) support, enabling automated testing, debugging, and AI-powered interactions with WebView applications.

## Overview

AuroraView's AI integration consists of three main components:

1. **AuroraView MCP Server** - Model Context Protocol server for AI assistants
2. **CDP Support** - Chrome DevTools Protocol for debugging and automation
3. **AI Agent Crate** - Rust-based AI agent with AGUI/A2UI protocols

## Quick Start

### Prerequisites

```bash
# Install AuroraView with MCP server
pip install auroraview auroraview-mcp

# Or install from source
cd packages/auroraview-mcp
pip install -e .
```

### Enable CDP in Your Application

```python
from auroraview import AuroraView

class MyApp(AuroraView):
    def __init__(self):
        super().__init__(
            url="https://example.com",
            debug=True,  # Enables CDP on port 9222
            devtools_port=9222,  # Custom CDP port
        )
```

### Start MCP Server

```bash
# Using uvx (recommended)
uvx auroraview-mcp

# Or directly with Python
python -m auroraview_mcp
```

## Using with AI Assistants

### Configuration for Claude Desktop / Cursor

Add to your MCP configuration (`claude_desktop_config.json` or Cursor settings):

```json
{
  "mcpServers": {
    "auroraview": {
      "command": "uvx",
      "args": ["auroraview-mcp"],
      "env": {
        "AURORAVIEW_DEFAULT_PORT": "9222"
      }
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `discover_instances` | Find running AuroraView instances |
| `connect` | Connect to an instance via CDP |
| `disconnect` | Disconnect from current instance |
| `list_pages` | List all available pages |
| `select_page` | Select a page to operate on |
| `take_screenshot` | Capture page screenshot |
| `click` | Click on an element |
| `fill` | Fill input fields |
| `evaluate` | Execute JavaScript |
| `call_api` | Call Python backend APIs |
| `get_console_logs` | Get console messages |
| `get_network_requests` | Get network activity |

## Using with browser-use

[browser-use](https://github.com/browser-use/browser-use) is an AI-powered browser automation library that can connect to AuroraView via CDP.

### Installation

```bash
pip install browser-use
```

### Configuration

```python
from browser_use import Agent
from langchain_openai import ChatOpenAI

# Configure browser to connect to AuroraView's CDP
agent = Agent(
    task="Interact with the AuroraView application",
    llm=ChatOpenAI(model="gpt-4o"),
    browser_config={
        "cdp_url": "http://127.0.0.1:9222",  # AuroraView CDP endpoint
    }
)

async def main():
    result = await agent.run()
    print(result)
```

### Example: Automated Testing

```python
import asyncio
from browser_use import Agent, Browser
from browser_use.browser.browser import BrowserConfig
from langchain_openai import ChatOpenAI

async def test_auroraview_app():
    """Test AuroraView application using browser-use."""
    
    # Connect to running AuroraView instance
    browser = Browser(config=BrowserConfig(
        cdp_url="http://127.0.0.1:9222",
        headless=False,
    ))
    
    agent = Agent(
        task="""
        1. Click on the 'Gallery' button
        2. Find and click on 'API Demo'
        3. Fill the input with 'Hello AuroraView'
        4. Click the submit button
        5. Verify the response shows in the output area
        """,
        llm=ChatOpenAI(model="gpt-4o"),
        browser=browser,
    )
    
    result = await agent.run()
    return result

asyncio.run(test_auroraview_app())
```

## Using with chrome-devtools MCP

The [chrome-devtools MCP server](https://github.com/anthropics/anthropic-quickstarts/tree/main/mcp-chrome-devtools) provides direct CDP access for AI assistants.

### Configuration

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "vx",
      "args": [
        "npx@20",
        "chrome-devtools-mcp@latest",
        "--browser-url=http://127.0.0.1:9222"
      ]
    }
  }
}
```

### Usage with AuroraView

1. **Start your AuroraView application with CDP enabled:**

```python
from auroraview import AuroraView

app = AuroraView(
    html="<h1>My App</h1>",
    debug=True,
    devtools_port=9222,
)
app.run()
```

2. **Use chrome-devtools MCP tools:**

```
# Available tools
- navigate_page: Navigate to a URL
- take_screenshot: Capture the page
- click: Click on elements
- fill: Fill form inputs
- evaluate_script: Execute JavaScript
- list_pages: List available pages
- take_snapshot: Get accessibility tree
```

3. **Example AI interaction:**

```
User: Take a screenshot of my AuroraView app running on port 9222

AI: I'll connect to your AuroraView instance and take a screenshot.

[Uses chrome-devtools MCP to:]
1. list_pages - Find the AuroraView page
2. select_page - Select it
3. take_screenshot - Capture and return the image
```

## Using with Playwright MCP

[Playwright MCP](https://github.com/microsoft/playwright-mcp) is Microsoft's official MCP server that provides browser automation capabilities using Playwright.

### Features

- **Fast and lightweight** - Uses Playwright's accessibility tree instead of pixel-based input
- **LLM-friendly** - No vision models needed, operates purely on structured data
- **Deterministic tool application** - Avoids ambiguity common in screenshot-based approaches

### Configuration

**Basic configuration:**

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"]
    }
  }
}
```

**Connect to AuroraView CDP endpoint:**

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--cdp-endpoint=http://127.0.0.1:9222"
      ]
    }
  }
}
```

**With configuration file:**

Create `playwright-mcp-config.json`:

```json
{
  "browser": {
    "cdpEndpoint": "http://127.0.0.1:9222",
    "cdpTimeout": 30000
  },
  "capabilities": ["core"],
  "network": {
    "allowedOrigins": ["*"]
  }
}
```

Then use:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--config=playwright-mcp-config.json"
      ]
    }
  }
}
```

### Available Tools

| Tool | Description |
|------|-------------|
| `browser_navigate` | Navigate to a URL |
| `browser_click` | Click on an element |
| `browser_type` | Type text into inputs |
| `browser_snapshot` | Get page accessibility snapshot |
| `browser_evaluate` | Execute JavaScript |
| `browser_tabs` | Manage browser tabs |

### Example Usage

```
User: Navigate to the Gallery page and click on the "Cookie Demo" sample

AI: I'll use Playwright to navigate and interact with the page.

[Uses playwright MCP to:]
1. browser_snapshot - Get current page structure
2. browser_click - Click on Gallery link
3. browser_snapshot - Get updated structure
4. browser_click - Click on Cookie Demo
```

## Combined MCP Configuration

For maximum flexibility, you can use multiple MCP servers together:

```json
{
  "mcpServers": {
    "auroraview": {
      "command": "uvx",
      "args": ["auroraview-mcp"],
      "env": {
        "AURORAVIEW_DEFAULT_PORT": "9222"
      }
    },
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@latest",
        "--cdp-endpoint=http://127.0.0.1:9222"
      ]
    },
    "chrome-devtools": {
      "command": "vx",
      "args": [
        "npx@20",
        "chrome-devtools-mcp@latest",
        "--browser-url=http://127.0.0.1:9222"
      ]
    }
  }
}
```

This allows AI assistants to:
- Use `auroraview` tools for Python API calls and instance management
- Use `playwright` tools for accessibility-based browser automation
- Use `chrome-devtools` tools for low-level CDP operations

## CDP API Reference

### Discovery Endpoints

```bash
# Get browser version info
curl http://127.0.0.1:9222/json/version

# List all pages/targets
curl http://127.0.0.1:9222/json/list

# Get protocol info
curl http://127.0.0.1:9222/json/protocol
```

### WebSocket Connection

```javascript
// Connect to page debugger
const ws = new WebSocket("ws://127.0.0.1:9222/devtools/page/<pageId>");

// Send CDP command
ws.send(JSON.stringify({
    id: 1,
    method: "Page.navigate",
    params: { url: "https://example.com" }
}));

// Receive response
ws.onmessage = (event) => {
    const response = JSON.parse(event.data);
    console.log(response);
};
```

### Supported CDP Domains

| Domain | Description | Key Methods |
|--------|-------------|-------------|
| **Page** | Page navigation & lifecycle | `navigate`, `reload`, `captureScreenshot` |
| **Runtime** | JavaScript execution | `evaluate`, `callFunctionOn` |
| **DOM** | DOM inspection & manipulation | `getDocument`, `querySelector`, `setNodeValue` |
| **Network** | Network monitoring | `enable`, `setRequestInterception` |
| **Console** | Console message handling | `enable`, `clearMessages` |
| **Input** | Input event simulation | `dispatchMouseEvent`, `dispatchKeyEvent` |
| **Accessibility** | Accessibility tree | `getFullAXTree`, `queryAXTree` |

## Python SDK for CDP

AuroraView provides a Python SDK for CDP interactions:

```python
from auroraview_mcp.connection import CDPConnection, PageConnection

async def automate_webview():
    # Connect to CDP
    conn = CDPConnection(port=9222)
    await conn.connect()
    
    # Get page connection
    page = await conn.get_page()
    
    # Navigate
    await page.send("Page.navigate", {"url": "https://example.com"})
    
    # Execute JavaScript
    result = await page.evaluate("document.title")
    print(f"Page title: {result}")
    
    # Take screenshot
    screenshot = await page.send("Page.captureScreenshot", {"format": "png"})
    
    # Click element
    await page.evaluate("""
        document.querySelector('button.submit').click()
    """)
    
    await conn.disconnect()
```

## AI Agent Architecture

### AGUI Protocol Events

The AI Agent uses the AGUI (Agent-GUI) protocol for streaming communication:

```typescript
// Event types
type AGUIEvent = 
    | { type: "RunStarted", runId: string }
    | { type: "TextMessageStart", messageId: string }
    | { type: "TextMessageContent", delta: string }
    | { type: "TextMessageEnd" }
    | { type: "ToolCallStart", toolCallId: string, name: string }
    | { type: "ToolCallArgs", delta: string }
    | { type: "ToolCallEnd" }
    | { type: "ToolCallResult", result: any }
    | { type: "RunFinished" }
    | { type: "RunError", error: string };
```

### A2UI Protocol Components

The A2UI (Agent-to-UI) protocol defines UI components for AI responses:

```typescript
// Component types
type A2UIComponent = 
    | { type: "Container", children: A2UIComponent[] }
    | { type: "Text", content: string }
    | { type: "Code", language: string, code: string }
    | { type: "Button", label: string, action: string }
    | { type: "Input", placeholder: string, name: string }
    | { type: "Table", headers: string[], rows: string[][] }
    | { type: "Chart", chartType: string, data: ChartData }
    | { type: "Image", src: string, alt: string };
```

### Provider Configuration

```python
from auroraview.ai import AIAgent, AIConfig

# Configure AI provider
config = AIConfig(
    provider="openai",  # or "anthropic", "gemini", "ollama"
    model="gpt-4o",
    api_key="sk-...",  # or use OPENAI_API_KEY env var
)

# Create agent
agent = AIAgent(config)

# Start conversation
response = await agent.chat("Help me debug this WebView")
```

## DCC Integration

### Maya

```python
import maya.cmds as cmds
from auroraview.dcc.maya import MayaWebView

class MayaAIAssistant(MayaWebView):
    def __init__(self):
        super().__init__(
            title="AI Assistant",
            debug=True,
            devtools_port=9222,
        )
        
    def get_scene_info(self):
        """API exposed to AI for scene analysis."""
        return {
            "objects": cmds.ls(type="mesh"),
            "selection": cmds.ls(sl=True),
            "frame": cmds.currentTime(q=True),
        }

# Register for AI access
assistant = MayaAIAssistant()
assistant.bind_call("scene.info", assistant.get_scene_info)
```

### Blender

```python
import bpy
from auroraview.dcc.blender import BlenderWebView

class BlenderAIAssistant(BlenderWebView):
    def __init__(self):
        super().__init__(
            title="AI Assistant",
            debug=True,
            devtools_port=9223,  # Different port for Blender
        )
        
    def get_scene_info(self):
        """API exposed to AI for scene analysis."""
        return {
            "objects": [obj.name for obj in bpy.data.objects],
            "selection": [obj.name for obj in bpy.context.selected_objects],
            "frame": bpy.context.scene.frame_current,
        }
```

## Debugging Tips

### 1. Verify CDP is Running

```bash
# Check if CDP is available
curl -s http://127.0.0.1:9222/json/version | jq

# Expected output:
{
  "Browser": "Chrome/xxx.x.xxxx.xxx",
  "Protocol-Version": "1.3",
  "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/..."
}
```

### 2. Monitor CDP Traffic

```python
import asyncio
import websockets
import json

async def monitor_cdp():
    uri = "ws://127.0.0.1:9222/devtools/page/<pageId>"
    async with websockets.connect(uri) as ws:
        # Enable console
        await ws.send(json.dumps({
            "id": 1,
            "method": "Console.enable"
        }))
        
        # Listen for events
        while True:
            msg = await ws.recv()
            print(json.loads(msg))

asyncio.run(monitor_cdp())
```

### 3. Use Chrome DevTools

Open `chrome://inspect` in Chrome browser and connect to your AuroraView instance for full DevTools access.

### 4. Common Issues

| Issue | Solution |
|-------|----------|
| CDP connection refused | Ensure `debug=True` and correct port |
| Page not found | Wait for WebView to fully load |
| Permission denied | Check firewall settings |
| WebSocket closed | Check for port conflicts |

## Security Considerations

1. **CDP is not secured by default** - Only enable in development or trusted environments
2. **Use authentication** - Consider adding token-based auth for production
3. **Limit exposed APIs** - Only expose necessary backend methods
4. **Network isolation** - Bind CDP to localhost only

```python
# Secure configuration
app = AuroraView(
    debug=os.getenv("DEBUG", "false").lower() == "true",
    devtools_port=9222,
    devtools_host="127.0.0.1",  # Only localhost
)
```

## Next Steps

- [RFC 0008: AI Agent Integration](/rfcs/0008-ai-agent-integration) - Full specification
- [RFC 0001: MCP Server](/rfcs/0001-auroraview-mcp-server) - MCP implementation details
- [Headless Testing Guide](/guide/headless-testing) - Automated testing without UI
- [Gallery Examples](/guide/gallery) - Interactive demos
