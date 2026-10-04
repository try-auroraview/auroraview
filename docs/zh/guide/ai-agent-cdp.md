# AI Agent 与 CDP 集成

> ⚠️ **独立的 `auroraview-mcp` Python 包已停用。**
> AuroraView 现在通过 [`dcc-mcp-core`](https://github.com/loonghao/dcc-mcp-core)
> 的 gateway + skills 作为一类 DCC adapter 对 agent 暴露自己 —— 详见统一重构 epic
> [#364](https://github.com/try-auroraview/auroraview/issues/364)。下文的
> `pip install auroraview-mcp` / `uvx auroraview-mcp` 指令仅作历史参考；
> 新架构（`crates/auroraview-mcp` adapter crate）落地中，进度见 #365–#368。

AuroraView 提供全面的 AI Agent 能力和 Chrome DevTools Protocol (CDP) 支持，实现 WebView 应用的自动化测试、调试和 AI 驱动交互。

## 概述

AuroraView 的 AI 集成包含三个主要组件：

1. **AuroraView MCP Server** - 为 AI 助手提供的 Model Context Protocol 服务器
2. **CDP 支持** - Chrome DevTools Protocol，用于调试和自动化
3. **AI Agent Crate** - 基于 Rust 的 AI Agent，支持 AGUI/A2UI 协议

## 快速开始

### 前置条件

```bash
# 安装 AuroraView 和 MCP 服务器
pip install auroraview auroraview-mcp

# 或从源码安装
cd packages/auroraview-mcp
pip install -e .
```

### 在应用中启用 CDP

```python
from auroraview import AuroraView

class MyApp(AuroraView):
    def __init__(self):
        super().__init__(
            url="https://example.com",
            debug=True,  # 在 9222 端口启用 CDP
            devtools_port=9222,  # 自定义 CDP 端口
        )
```

### 启动 MCP 服务器

```bash
# 使用 uvx（推荐）
uvx auroraview-mcp

# 或直接使用 Python
python -m auroraview_mcp
```

## 与 AI 助手配合使用

### 配置 Claude Desktop / Cursor

添加到 MCP 配置文件（`claude_desktop_config.json` 或 Cursor 设置）：

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

### 可用的 MCP 工具

| 工具 | 描述 |
|------|------|
| `discover_instances` | 发现运行中的 AuroraView 实例 |
| `connect` | 通过 CDP 连接到实例 |
| `disconnect` | 断开当前实例连接 |
| `list_pages` | 列出所有可用页面 |
| `select_page` | 选择要操作的页面 |
| `take_screenshot` | 截取页面截图 |
| `click` | 点击元素 |
| `fill` | 填充输入框 |
| `evaluate` | 执行 JavaScript |
| `call_api` | 调用 Python 后端 API |
| `get_console_logs` | 获取控制台消息 |
| `get_network_requests` | 获取网络活动 |

## 与 browser-use 配合使用

[browser-use](https://github.com/browser-use/browser-use) 是一个 AI 驱动的浏览器自动化库，可以通过 CDP 连接到 AuroraView。

### 安装

```bash
pip install browser-use
```

### 配置

```python
from browser_use import Agent
from langchain_openai import ChatOpenAI

# 配置浏览器连接到 AuroraView 的 CDP
agent = Agent(
    task="与 AuroraView 应用交互",
    llm=ChatOpenAI(model="gpt-4o"),
    browser_config={
        "cdp_url": "http://127.0.0.1:9222",  # AuroraView CDP 端点
    }
)

async def main():
    result = await agent.run()
    print(result)
```

### 示例：自动化测试

```python
import asyncio
from browser_use import Agent, Browser
from browser_use.browser.browser import BrowserConfig
from langchain_openai import ChatOpenAI

async def test_auroraview_app():
    """使用 browser-use 测试 AuroraView 应用。"""
    
    # 连接到运行中的 AuroraView 实例
    browser = Browser(config=BrowserConfig(
        cdp_url="http://127.0.0.1:9222",
        headless=False,
    ))
    
    agent = Agent(
        task="""
        1. 点击 'Gallery' 按钮
        2. 找到并点击 'API Demo'
        3. 在输入框中填写 'Hello AuroraView'
        4. 点击提交按钮
        5. 验证输出区域显示响应
        """,
        llm=ChatOpenAI(model="gpt-4o"),
        browser=browser,
    )
    
    result = await agent.run()
    return result

asyncio.run(test_auroraview_app())
```

## 与 chrome-devtools MCP 配合使用

[chrome-devtools MCP 服务器](https://github.com/anthropics/anthropic-quickstarts/tree/main/mcp-chrome-devtools) 为 AI 助手提供直接的 CDP 访问。

### 配置

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

### 与 AuroraView 配合使用

1. **启动启用 CDP 的 AuroraView 应用：**

```python
from auroraview import AuroraView

app = AuroraView(
    html="<h1>My App</h1>",
    debug=True,
    devtools_port=9222,
)
app.run()
```

2. **使用 chrome-devtools MCP 工具：**

```
# 可用工具
- navigate_page：导航到 URL
- take_screenshot：截取页面
- click：点击元素
- fill：填充表单输入
- evaluate_script：执行 JavaScript
- list_pages：列出可用页面
- take_snapshot：获取可访问性树
```

3. **AI 交互示例：**

```
用户：截取我在 9222 端口运行的 AuroraView 应用的截图

AI：我将连接到您的 AuroraView 实例并截图。

[使用 chrome-devtools MCP：]
1. list_pages - 查找 AuroraView 页面
2. select_page - 选择它
3. take_screenshot - 截取并返回图片
```

## 与 Playwright MCP 配合使用

[Playwright MCP](https://github.com/microsoft/playwright-mcp) 是微软官方的 MCP 服务器，使用 Playwright 提供浏览器自动化能力。

### 特性

- **快速且轻量** - 使用 Playwright 的可访问性树，而非基于像素的输入
- **对 LLM 友好** - 不需要视觉模型，完全基于结构化数据操作
- **确定性的工具应用** - 避免了基于截图方法中常见的歧义

### 配置

**基本配置：**

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

**连接到 AuroraView CDP 端点：**

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

**使用配置文件：**

创建 `playwright-mcp-config.json`：

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

然后使用：

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

### 可用工具

| 工具 | 描述 |
|------|------|
| `browser_navigate` | 导航到 URL |
| `browser_click` | 点击元素 |
| `browser_type` | 在输入框中输入文本 |
| `browser_snapshot` | 获取页面可访问性快照 |
| `browser_evaluate` | 执行 JavaScript |
| `browser_tabs` | 管理浏览器标签页 |

### 使用示例

```
用户：导航到 Gallery 页面并点击 "Cookie Demo" 示例

AI：我将使用 Playwright 来导航和交互。

[使用 playwright MCP：]
1. browser_snapshot - 获取当前页面结构
2. browser_click - 点击 Gallery 链接
3. browser_snapshot - 获取更新后的结构
4. browser_click - 点击 Cookie Demo
```

## 组合 MCP 配置

为了获得最大的灵活性，你可以同时使用多个 MCP 服务器：

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

这使 AI 助手能够：
- 使用 `auroraview` 工具进行 Python API 调用和实例管理
- 使用 `playwright` 工具进行基于可访问性的浏览器自动化
- 使用 `chrome-devtools` 工具进行底层 CDP 操作

## CDP API 参考

### 发现端点

```bash
# 获取浏览器版本信息
curl http://127.0.0.1:9222/json/version

# 列出所有页面/目标
curl http://127.0.0.1:9222/json/list

# 获取协议信息
curl http://127.0.0.1:9222/json/protocol
```

### WebSocket 连接

```javascript
// 连接到页面调试器
const ws = new WebSocket("ws://127.0.0.1:9222/devtools/page/<pageId>");

// 发送 CDP 命令
ws.send(JSON.stringify({
    id: 1,
    method: "Page.navigate",
    params: { url: "https://example.com" }
}));

// 接收响应
ws.onmessage = (event) => {
    const response = JSON.parse(event.data);
    console.log(response);
};
```

### 支持的 CDP 域

| 域 | 描述 | 关键方法 |
|----|------|----------|
| **Page** | 页面导航和生命周期 | `navigate`, `reload`, `captureScreenshot` |
| **Runtime** | JavaScript 执行 | `evaluate`, `callFunctionOn` |
| **DOM** | DOM 检查和操作 | `getDocument`, `querySelector`, `setNodeValue` |
| **Network** | 网络监控 | `enable`, `setRequestInterception` |
| **Console** | 控制台消息处理 | `enable`, `clearMessages` |
| **Input** | 输入事件模拟 | `dispatchMouseEvent`, `dispatchKeyEvent` |
| **Accessibility** | 可访问性树 | `getFullAXTree`, `queryAXTree` |

## CDP Python SDK

AuroraView 提供用于 CDP 交互的 Python SDK：

```python
from auroraview_mcp.connection import CDPConnection, PageConnection

async def automate_webview():
    # 连接到 CDP
    conn = CDPConnection(port=9222)
    await conn.connect()
    
    # 获取页面连接
    page = await conn.get_page()
    
    # 导航
    await page.send("Page.navigate", {"url": "https://example.com"})
    
    # 执行 JavaScript
    result = await page.evaluate("document.title")
    print(f"页面标题：{result}")
    
    # 截图
    screenshot = await page.send("Page.captureScreenshot", {"format": "png"})
    
    # 点击元素
    await page.evaluate("""
        document.querySelector('button.submit').click()
    """)
    
    await conn.disconnect()
```

## AI Agent 架构

### AGUI 协议事件

AI Agent 使用 AGUI（Agent-GUI）协议进行流式通信：

```typescript
// 事件类型
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

### A2UI 协议组件

A2UI（Agent-to-UI）协议定义了 AI 响应的 UI 组件：

```typescript
// 组件类型
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

### Provider 配置

```python
from auroraview.ai import AIAgent, AIConfig

# 配置 AI 提供商
config = AIConfig(
    provider="openai",  # 或 "anthropic", "gemini", "ollama"
    model="gpt-4o",
    api_key="sk-...",  # 或使用 OPENAI_API_KEY 环境变量
)

# 创建 agent
agent = AIAgent(config)

# 开始对话
response = await agent.chat("帮我调试这个 WebView")
```

## DCC 集成

### Maya

```python
import maya.cmds as cmds
from auroraview.dcc.maya import MayaWebView

class MayaAIAssistant(MayaWebView):
    def __init__(self):
        super().__init__(
            title="AI 助手",
            debug=True,
            devtools_port=9222,
        )
        
    def get_scene_info(self):
        """暴露给 AI 用于场景分析的 API。"""
        return {
            "objects": cmds.ls(type="mesh"),
            "selection": cmds.ls(sl=True),
            "frame": cmds.currentTime(q=True),
        }

# 注册供 AI 访问
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
            title="AI 助手",
            debug=True,
            devtools_port=9223,  # Blender 使用不同端口
        )
        
    def get_scene_info(self):
        """暴露给 AI 用于场景分析的 API。"""
        return {
            "objects": [obj.name for obj in bpy.data.objects],
            "selection": [obj.name for obj in bpy.context.selected_objects],
            "frame": bpy.context.scene.frame_current,
        }
```

## 调试技巧

### 1. 验证 CDP 是否运行

```bash
# 检查 CDP 是否可用
curl -s http://127.0.0.1:9222/json/version | jq

# 预期输出：
{
  "Browser": "Chrome/xxx.x.xxxx.xxx",
  "Protocol-Version": "1.3",
  "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/..."
}
```

### 2. 监控 CDP 流量

```python
import asyncio
import websockets
import json

async def monitor_cdp():
    uri = "ws://127.0.0.1:9222/devtools/page/<pageId>"
    async with websockets.connect(uri) as ws:
        # 启用控制台
        await ws.send(json.dumps({
            "id": 1,
            "method": "Console.enable"
        }))
        
        # 监听事件
        while True:
            msg = await ws.recv()
            print(json.loads(msg))

asyncio.run(monitor_cdp())
```

### 3. 使用 Chrome DevTools

在 Chrome 浏览器中打开 `chrome://inspect`，连接到您的 AuroraView 实例以获得完整的 DevTools 访问。

### 4. 常见问题

| 问题 | 解决方案 |
|------|----------|
| CDP 连接被拒绝 | 确保 `debug=True` 且端口正确 |
| 找不到页面 | 等待 WebView 完全加载 |
| 权限被拒绝 | 检查防火墙设置 |
| WebSocket 关闭 | 检查端口冲突 |

## 安全注意事项

1. **CDP 默认不安全** - 仅在开发环境或受信任的环境中启用
2. **使用身份验证** - 考虑为生产环境添加基于令牌的认证
3. **限制暴露的 API** - 仅暴露必要的后端方法
4. **网络隔离** - 将 CDP 仅绑定到 localhost

```python
# 安全配置
app = AuroraView(
    debug=os.getenv("DEBUG", "false").lower() == "true",
    devtools_port=9222,
    devtools_host="127.0.0.1",  # 仅 localhost
)
```

## 下一步

- [RFC 0008：AI Agent 集成](/rfcs/0008-ai-agent-integration) - 完整规范
- [RFC 0001：MCP 服务器](/rfcs/0001-auroraview-mcp-server) - MCP 实现细节
- [Headless 测试指南](/guide/headless-testing) - 无界面自动化测试
- [Gallery 示例](/guide/gallery) - 交互式演示
