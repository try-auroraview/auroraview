# RFC 0001: AuroraView MCP Server

> **状态**: ⚠️ **Superseded** — 参见 [Epic #364](https://github.com/try-auroraview/auroraview/issues/364)
> **作者**: AuroraView Team
> **创建日期**: 2024-12-30
> **更新日期**: 2026-04-17（标记为 superseded）
> **目标版本**: v0.4.0（未达成，方向已变）
>
> **为何被 supersede**：本 RFC 设计时 `dcc-mcp-core` 尚未提供 `DccAdapter`、
> `BridgeKind::WebSocket`、`FileRegistry.extras`、`Capturer`、`dcc-mcp-server`
> binary、progressive skill discovery 等能力，所以规划了独立的 Python
> `auroraview-mcp` 包去实现这些。`dcc-mcp-core` v0.13.2 已经把这些全部做成了
> 可复用的基础设施，因此 auroraview 改为一个 Rust adapter crate +
> CDP bridge + SKILL.md 驱动的 tool 清单 —— 见
> [`crates/auroraview-mcp`](https://github.com/try-auroraview/auroraview/tree/main/crates/auroraview-mcp)（落地中）
> 以及 issues #365–#368。
>
> 本文档保留作为历史设计存档；下文中的包名、命令、架构图不再代表当前实现。

## 摘要

本 RFC 提议为 AuroraView 框架创建一个专用的 MCP (Model Context Protocol) 服务器，使 AI 助手能够直接与 AuroraView 应用进行交互、测试和调试。该服务器将提供一套标准化的工具集，用于连接 WebView 实例、调用 Python API、触发事件、截图、运行示例等操作。

**核心目标**：
1. **Standalone 模式**：支持独立 AuroraView 应用的 AI 自动化
2. **DCC 集成模式**：支持在 Maya、Blender、Houdini、Unreal 等 DCC 软件中运行的 AuroraView 面板
3. **AI 自动化**：结合 Midscene.js 实现自然语言驱动的 UI 自动化
4. **跨语言 SDK**：同时提供 Python 和 TypeScript/Node.js SDK

## 动机

### 当前状态分析

目前，AI 助手与 AuroraView 应用的交互存在以下限制：

1. **间接连接**：需要通过 Chrome DevTools MCP 连接，但该工具会创建新的浏览器实例而非连接到现有 WebView2
2. **配置复杂**：需要手动获取 WebSocket 端点 ID，每次重启应用都需要更新配置
3. **功能受限**：Chrome DevTools MCP 的 `evaluate_script` 对异步操作支持不完善
4. **无法直接调用 Python API**：只能通过 JS 桥接间接调用
5. **DCC 环境受限**：无法连接到嵌入在 Maya/Blender/Houdini 中的 AuroraView 面板

### 行业趋势对比

| 工具 | 特点 | 可借鉴 |
|------|------|--------|
| Chrome DevTools MCP | 通用浏览器调试 | CDP 连接方式 |
| Playwright MCP | 端到端测试 | 页面选择、截图 |
| Tauri MCP (概念) | 桌面应用集成 | 原生 API 调用 |
| ShotGrid MCP | 行业特定集成 | 领域专用工具设计 |
| Midscene.js | AI UI 自动化 | 自然语言交互、视觉理解 |

### 需求分析

1. **自动发现**：自动发现运行中的 AuroraView 实例，无需手动配置
2. **直接 API 调用**：直接调用 Python 后端 API，绕过 JS 桥接
3. **完整测试能力**：支持 UI 测试、API 测试、性能测试
4. **开发调试**：实时日志、状态检查、热重载触发
5. **Gallery 集成**：运行示例、查看源码、管理进程
6. **DCC 支持**：连接和控制 DCC 软件中的 AuroraView 面板
7. **AI 自动化**：自然语言驱动的 UI 操作和测试

## 设计方案

### 技术选型分析：Python vs Node.js

#### 对比分析

| 维度 | Python MCP SDK | TypeScript MCP SDK |
|------|----------------|-------------------|
| **官方支持** | ✅ 官方 SDK | ✅ 官方 SDK (更活跃) |
| **生态成熟度** | 较新 | 更成熟 (11.2k stars) |
| **DCC 兼容性** | ✅ 原生支持 Maya/Houdini/Blender Python | ❌ 需要额外进程 |
| **Midscene 集成** | 需要桥接 | ✅ 原生 TypeScript |
| **异步支持** | asyncio | ✅ 原生 async/await |
| **类型安全** | 可选 (typing) | ✅ 强类型 |
| **部署复杂度** | 简单 (uvx) | 需要 Node.js 环境 |
| **与 AuroraView 集成** | ✅ 直接调用 Python API | 需要 IPC |

#### 推荐方案：双 SDK 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         AI Assistant                                 │
│                    (Claude, GPT, Copilot)                           │
└─────────────────────────────────────────────────────────────────────┘
                                │
                    MCP Protocol (stdio/SSE)
                                │
        ┌───────────────────────┴───────────────────────┐
        │                                               │
        ▼                                               ▼
┌───────────────────┐                       ┌───────────────────┐
│  Python MCP SDK   │                       │   Node.js MCP SDK │
│  (auroraview-mcp) │                       │ (@auroraview/mcp) │
├───────────────────┤                       ├───────────────────┤
│ • DCC 环境优先    │                       │ • Midscene 集成   │
│ • 直接 Python API │                       │ • 前端开发优先    │
│ • 简单部署        │                       │ • 类型安全        │
└─────────┬─────────┘                       └─────────┬─────────┘
          │                                           │
          └─────────────────┬─────────────────────────┘
                            │
                    CDP / WebSocket
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Standalone │     │    Maya     │     │   Unreal    │
│   WebView   │     │  QtWebView  │     │   WebView   │
└─────────────┘     └─────────────┘     └─────────────┘
```

**推荐策略**：
1. **Phase 1**: Python SDK 优先 - 快速验证，支持 DCC 环境
2. **Phase 2**: Node.js SDK - Midscene 深度集成，前端开发体验
3. **共享**: 核心协议和工具定义保持一致

### DCC 集成架构

#### 场景分析

```
┌─────────────────────────────────────────────────────────────────────┐
│                           DCC Application                            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      Maya / Blender / Houdini                │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │                    Qt Host Window                    │   │   │
│  │  │  ┌───────────────────────────────────────────────┐ │   │   │
│  │  │  │              AuroraView Panel                  │ │   │   │
│  │  │  │  ┌─────────────────────────────────────────┐ │ │   │   │
│  │  │  │  │            WebView2 (CDP)               │ │ │   │   │
│  │  │  │  │  ┌─────────────────────────────────┐   │ │ │   │   │
│  │  │  │  │  │     Your Tool UI (React/Vue)    │   │ │ │   │   │
│  │  │  │  │  │                                  │   │ │ │   │   │
│  │  │  │  │  │  window.auroraview.api.xxx()    │   │ │ │   │   │
│  │  │  │  │  └─────────────────────────────────┘   │ │ │   │   │
│  │  │  │  └──────────────────┬──────────────────────┘ │ │   │   │
│  │  │  └─────────────────────┼────────────────────────┘ │   │   │
│  │  └────────────────────────┼──────────────────────────┘   │   │
│  └───────────────────────────┼──────────────────────────────┘   │
└──────────────────────────────┼──────────────────────────────────┘
                               │ CDP (port 9222+)
                               ▼
                    ┌─────────────────────┐
                    │  AuroraView MCP     │
                    │      Server         │
                    └─────────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    AI Assistant     │
                    │  "点击重命名按钮"    │
                    └─────────────────────┘
```

#### DCC 特定工具

```python
# ==================== DCC Tools ====================

@mcp.tool()
async def list_dcc_instances() -> list[dict]:
    """发现所有 DCC 环境中的 AuroraView 实例。
    
    Returns:
        实例列表，包含:
        - dcc_type: "maya" | "blender" | "houdini" | "nuke" | "unreal"
        - dcc_version: "2025.1"
        - panel_name: "Asset Browser"
        - port: 9222
        - pid: 12345
    """

@mcp.tool()
async def get_dcc_context() -> dict:
    """获取当前 DCC 环境上下文。
    
    Returns:
        - scene_path: 当前场景文件路径
        - selected_objects: 选中的对象列表
        - current_frame: 当前帧
        - project_path: 项目路径
    """

@mcp.tool()
async def execute_dcc_command(command: str, **kwargs) -> Any:
    """执行 DCC 原生命令。
    
    Args:
        command: 命令名称（如 "maya.cmds.ls", "bpy.ops.object.select_all"）
        **kwargs: 命令参数
    
    Returns:
        命令执行结果
    
    Example:
        # Maya
        execute_dcc_command("maya.cmds.ls", selection=True)
        
        # Blender
        execute_dcc_command("bpy.ops.object.select_all", action='SELECT')
    """

@mcp.tool()
async def sync_selection() -> dict:
    """同步 DCC 和 WebView 之间的选择状态。
    
    Returns:
        - dcc_selection: DCC 中选中的对象
        - webview_selection: WebView UI 中选中的项目
    """
```

### Midscene.js 集成架构

#### 为什么需要 Midscene 集成？

1. **自然语言 UI 控制**：用户可以说 "点击重命名按钮" 而不是写 CSS 选择器
2. **视觉理解**：AI 可以 "看到" UI 并理解布局
3. **智能断言**：用 "检查是否显示成功消息" 代替精确的元素检查
4. **跨 DCC 通用**：同样的指令在 Maya/Blender/Houdini 中都能工作

#### 集成方案

```typescript
// packages/auroraview-mcp-node/src/midscene-integration.ts

import { MidsceneAgent } from '@anthropic/midscene';
import type { Page } from 'playwright';

export class AuroraViewMidsceneAgent {
  private agent: MidsceneAgent;
  private page: Page;
  
  constructor(page: Page) {
    this.page = page;
    this.agent = new MidsceneAgent(page, {
      model: 'gpt-4o',  // 或其他多模态模型
    });
  }
  
  /**
   * 执行自然语言 UI 操作
   */
  async aiAct(instruction: string): Promise<void> {
    // 注入 AuroraView 上下文
    const context = await this.getAuroraViewContext();
    
    await this.agent.ai(`
      当前应用: AuroraView ${context.appName}
      当前页面: ${context.pageTitle}
      可用 API: ${context.apiMethods.join(', ')}
      
      执行: ${instruction}
    `);
  }
  
  /**
   * 提取结构化数据
   */
  async aiQuery<T>(demand: string): Promise<T> {
    return await this.agent.aiQuery(demand);
  }
  
  /**
   * 自然语言断言
   */
  async aiAssert(assertion: string): Promise<void> {
    await this.agent.aiAssert(assertion);
  }
  
  /**
   * 获取 AuroraView 上下文增强 AI 理解
   */
  private async getAuroraViewContext() {
    return await this.page.evaluate(() => ({
      appName: document.title,
      pageTitle: document.title,
      apiMethods: window.__auroraview_api_methods || [],
      currentState: window.auroraview?.state?.getAll() || {},
    }));
  }
}
```

#### MCP 工具集成

```typescript
// Node.js MCP Server with Midscene

import { McpServer } from '@modelcontextprotocol/server';
import { AuroraViewMidsceneAgent } from './midscene-integration';

const server = new McpServer('auroraview');

// AI 驱动的 UI 操作
server.tool('ai_act', {
  description: '使用自然语言执行 UI 操作',
  parameters: {
    instruction: { type: 'string', description: '自然语言指令' },
  },
  async handler({ instruction }) {
    const agent = await getConnectedAgent();
    await agent.aiAct(instruction);
    return { success: true };
  },
});

// AI 数据提取
server.tool('ai_query', {
  description: '使用自然语言提取页面数据',
  parameters: {
    demand: { type: 'string', description: '数据需求描述' },
  },
  async handler({ demand }) {
    const agent = await getConnectedAgent();
    return await agent.aiQuery(demand);
  },
});

// AI 断言
server.tool('ai_assert', {
  description: '使用自然语言验证页面状态',
  parameters: {
    assertion: { type: 'string', description: '断言描述' },
  },
  async handler({ assertion }) {
    const agent = await getConnectedAgent();
    await agent.aiAssert(assertion);
    return { passed: true };
  },
});

// DCC 特定的 AI 操作
server.tool('ai_dcc_action', {
  description: '在 DCC 环境中执行 AI 驱动的操作',
  parameters: {
    action: { type: 'string', description: '操作描述' },
    dcc_type: { type: 'string', enum: ['maya', 'blender', 'houdini', 'unreal'] },
  },
  async handler({ action, dcc_type }) {
    const agent = await getConnectedAgent();
    
    // 根据 DCC 类型调整上下文
    const dccContext = await getDCCContext(dcc_type);
    
    await agent.aiAct(`
      在 ${dcc_type} 环境中:
      当前选中: ${dccContext.selection.join(', ')}
      当前场景: ${dccContext.scenePath}
      
      执行: ${action}
    `);
    
    return { success: true };
  },
});
```

### 架构概览（更新版）

```
┌─────────────────────────────────────────────────────────────┐
│                      AI Assistant                            │
│                 (Claude, GPT, etc.)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ MCP Protocol (stdio/SSE)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  AuroraView MCP Server                       │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │  Discovery  │ │   Tools     │ │     Resources       │   │
│  │   Module    │ │   Module    │ │      Module         │   │
│  └─────────────┘ └─────────────┘ └─────────────────────┘   │
│         │               │                   │               │
│         └───────────────┼───────────────────┘               │
│                         │                                    │
│              ┌──────────┴──────────┐                        │
│              │   Connection Pool   │                        │
│              └──────────┬──────────┘                        │
└─────────────────────────┼───────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │ WebView  │   │ WebView  │   │ WebView  │
    │ Instance │   │ Instance │   │ Instance │
    │  (CDP)   │   │  (CDP)   │   │  (CDP)   │
    └──────────┘   └──────────┘   └──────────┘
```

### 完整 API 预览

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("auroraview")

# ==================== Discovery Tools ====================

@mcp.tool()
async def discover_instances() -> list[dict]:
    """发现所有运行中的 AuroraView 实例。
    
    Returns:
        实例列表，每个包含 id, port, title, url, pid
    """

@mcp.tool()
async def connect(port: int = 9222) -> dict:
    """连接到指定端口的 AuroraView 实例。
    
    Args:
        port: CDP 端口号，默认 9222
    
    Returns:
        连接状态和实例信息
    """

@mcp.tool()
async def disconnect() -> dict:
    """断开当前连接。"""

# ==================== Page Tools ====================

@mcp.tool()
async def list_pages() -> list[dict]:
    """列出所有页面。
    
    Returns:
        页面列表，每个包含 id, url, title
    """

@mcp.tool()
async def select_page(page_id: str = None, url_pattern: str = None) -> dict:
    """选择要操作的页面。
    
    Args:
        page_id: 页面 ID
        url_pattern: URL 匹配模式（支持通配符）
    
    Returns:
        选中的页面信息
    """

@mcp.tool()
async def get_page_info() -> dict:
    """获取当前页面的详细信息。
    
    Returns:
        包含 url, title, auroraview_ready, api_methods 等
    """

# ==================== API Tools ====================

@mcp.tool()
async def call_api(method: str, **kwargs) -> Any:
    """调用 AuroraView Python API。
    
    Args:
        method: API 方法名（如 "get_samples", "run_sample"）
        **kwargs: 方法参数
    
    Returns:
        API 返回值
    
    Example:
        call_api("run_sample", name="hello_world")
    """

@mcp.tool()
async def list_api_methods() -> list[dict]:
    """列出所有可用的 API 方法。
    
    Returns:
        方法列表，每个包含 name, signature, docstring
    """

@mcp.tool()
async def emit_event(event: str, data: dict = None) -> dict:
    """向前端触发事件。
    
    Args:
        event: 事件名称
        data: 事件数据
    
    Returns:
        发送状态
    """

# ==================== UI Tools ====================

@mcp.tool()
async def take_screenshot(
    selector: str = None,
    full_page: bool = False,
    path: str = None
) -> str:
    """截取页面截图。
    
    Args:
        selector: CSS 选择器（可选，截取特定元素）
        full_page: 是否截取完整页面
        path: 保存路径（可选，不提供则返回 base64）
    
    Returns:
        截图文件路径或 base64 数据
    """

@mcp.tool()
async def get_snapshot() -> dict:
    """获取页面可访问性树快照。
    
    Returns:
        A11y 树结构，包含所有可交互元素
    """

@mcp.tool()
async def click(selector: str = None, uid: str = None) -> dict:
    """点击元素。
    
    Args:
        selector: CSS 选择器
        uid: 快照中的元素 UID
    
    Returns:
        操作结果
    """

@mcp.tool()
async def fill(selector: str, value: str) -> dict:
    """填充输入框。
    
    Args:
        selector: CSS 选择器
        value: 要填充的值
    
    Returns:
        操作结果
    """

@mcp.tool()
async def evaluate(script: str) -> Any:
    """执行 JavaScript 代码。
    
    Args:
        script: JavaScript 代码
    
    Returns:
        执行结果
    """

# ==================== Gallery Tools ====================

@mcp.tool()
async def get_samples(category: str = None, tags: list[str] = None) -> list[dict]:
    """获取示例列表。
    
    Args:
        category: 分类过滤
        tags: 标签过滤
    
    Returns:
        示例列表
    """

@mcp.tool()
async def run_sample(name: str) -> dict:
    """运行示例。
    
    Args:
        name: 示例名称
    
    Returns:
        运行状态和进程信息
    """

@mcp.tool()
async def stop_sample(pid: int = None, name: str = None) -> dict:
    """停止运行中的示例。
    
    Args:
        pid: 进程 ID
        name: 示例名称
    
    Returns:
        停止状态
    """

@mcp.tool()
async def get_sample_source(name: str) -> str:
    """获取示例源代码。
    
    Args:
        name: 示例名称
    
    Returns:
        Python 源代码
    """

@mcp.tool()
async def list_processes() -> list[dict]:
    """列出所有运行中的示例进程。
    
    Returns:
        进程列表
    """

# ==================== Debug Tools ====================

@mcp.tool()
async def get_console_logs(level: str = None, limit: int = 100) -> list[dict]:
    """获取控制台日志。
    
    Args:
        level: 日志级别过滤（log, warn, error）
        limit: 最大条数
    
    Returns:
        日志列表
    """

@mcp.tool()
async def get_network_requests(
    url_pattern: str = None,
    method: str = None
) -> list[dict]:
    """获取网络请求记录。
    
    Args:
        url_pattern: URL 匹配模式
        method: HTTP 方法过滤
    
    Returns:
        请求列表
    """

@mcp.tool()
async def get_backend_status() -> dict:
    """获取 Python 后端状态。
    
    Returns:
        包含 ready, uptime, memory, handlers 等信息
    """

@mcp.tool()
async def reload_page(hard: bool = False) -> dict:
    """重新加载页面。
    
    Args:
        hard: 是否强制刷新（清除缓存）
    
    Returns:
        重载状态
    """

# ==================== Resources ====================

@mcp.resource("auroraview://instances")
async def get_instances_resource() -> str:
    """当前运行的 AuroraView 实例列表。"""

@mcp.resource("auroraview://page/{page_id}")
async def get_page_resource(page_id: str) -> str:
    """指定页面的详细信息。"""

@mcp.resource("auroraview://samples")
async def get_samples_resource() -> str:
    """所有可用示例的列表。"""

@mcp.resource("auroraview://sample/{name}/source")
async def get_sample_source_resource(name: str) -> str:
    """指定示例的源代码。"""

@mcp.resource("auroraview://logs")
async def get_logs_resource() -> str:
    """最近的控制台日志。"""
```

### 详细说明

#### 1. 自动发现机制

```python
class InstanceDiscovery:
    """AuroraView 实例发现器。"""
    
    # 默认扫描端口范围
    DEFAULT_PORTS = [9222, 9223, 9224, 9225]
    
    async def discover(self) -> list[Instance]:
        """扫描本地端口，发现运行中的实例。"""
        instances = []
        
        for port in self.DEFAULT_PORTS:
            try:
                # 尝试获取 CDP 版本信息
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"http://127.0.0.1:{port}/json/version",
                        timeout=1.0
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # 检查是否是 AuroraView 实例
                        if self._is_auroraview(data):
                            instances.append(Instance(
                                port=port,
                                browser=data.get("Browser"),
                                ws_url=data.get("webSocketDebuggerUrl"),
                            ))
            except Exception:
                continue
        
        return instances
    
    def _is_auroraview(self, data: dict) -> bool:
        """检查是否是 AuroraView 实例。"""
        # 通过 User-Agent 或其他特征判断
        return "Edg" in data.get("Browser", "") or "Chrome" in data.get("Browser", "")
```

#### 2. 连接管理

```python
class ConnectionManager:
    """CDP 连接管理器。"""
    
    def __init__(self):
        self._connections: dict[int, CDPConnection] = {}
        self._current: CDPConnection | None = None
    
    async def connect(self, port: int) -> CDPConnection:
        """建立 CDP 连接。"""
        if port in self._connections:
            self._current = self._connections[port]
            return self._current
        
        # 获取 WebSocket URL
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://127.0.0.1:{port}/json/version")
            ws_url = resp.json()["webSocketDebuggerUrl"]
        
        # 建立 WebSocket 连接
        conn = CDPConnection(port, ws_url)
        await conn.connect()
        
        self._connections[port] = conn
        self._current = conn
        return conn
    
    async def get_pages(self) -> list[Page]:
        """获取所有页面。"""
        if not self._current:
            raise RuntimeError("Not connected")
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://127.0.0.1:{self._current.port}/json/list"
            )
            pages_data = resp.json()
        
        pages = []
        for data in pages_data:
            # 过滤掉 about:blank
            if data.get("url") != "about:blank":
                pages.append(Page(
                    id=data["id"],
                    url=data["url"],
                    title=data.get("title", ""),
                    ws_url=data["webSocketDebuggerUrl"],
                ))
        
        return pages
```

#### 3. API 调用桥接

```python
class APIBridge:
    """Python API 调用桥接。"""
    
    def __init__(self, page: Page):
        self._page = page
        self._call_id = 0
    
    async def call(self, method: str, **kwargs) -> Any:
        """调用 Python API。"""
        self._call_id += 1
        call_id = f"mcp_{self._call_id}"
        
        # 构建调用脚本
        if kwargs:
            params_json = json.dumps(kwargs)
            script = f"""
            (async () => {{
                try {{
                    const result = await window.auroraview.call("{method}", {params_json});
                    return {{ ok: true, result }};
                }} catch (e) {{
                    return {{ ok: false, error: e.message }};
                }}
            }})()
            """
        else:
            script = f"""
            (async () => {{
                try {{
                    const result = await window.auroraview.api.{method}();
                    return {{ ok: true, result }};
                }} catch (e) {{
                    return {{ ok: false, error: e.message }};
                }}
            }})()
            """
        
        # 通过 CDP 执行
        result = await self._page.evaluate(script)
        
        if not result.get("ok"):
            raise APIError(result.get("error", "Unknown error"))
        
        return result.get("result")
    
    async def list_methods(self) -> list[dict]:
        """列出所有可用方法。"""
        script = """
        (() => {
            const methods = [];
            if (window.auroraview && window.auroraview.api) {
                // Proxy 对象无法直接枚举，需要后端提供方法列表
                // 这里返回已知的标准方法
                return window.__auroraview_api_methods || [];
            }
            return methods;
        })()
        """
        return await self._page.evaluate(script)
```

#### 4. 截图与快照

```python
class ScreenshotTool:
    """截图工具。"""
    
    async def take_screenshot(
        self,
        page: Page,
        selector: str = None,
        full_page: bool = False,
        path: str = None,
    ) -> str:
        """截取截图。"""
        # 使用 CDP Page.captureScreenshot
        params = {
            "format": "png",
            "captureBeyondViewport": full_page,
        }
        
        if selector:
            # 获取元素边界
            bounds = await page.evaluate(f"""
                (() => {{
                    const el = document.querySelector("{selector}");
                    if (!el) return null;
                    const rect = el.getBoundingClientRect();
                    return {{
                        x: rect.x,
                        y: rect.y,
                        width: rect.width,
                        height: rect.height
                    }};
                }})()
            """)
            if bounds:
                params["clip"] = bounds
        
        result = await page.send_cdp("Page.captureScreenshot", params)
        data = result["data"]  # base64
        
        if path:
            import base64
            with open(path, "wb") as f:
                f.write(base64.b64decode(data))
            return path
        
        return f"data:image/png;base64,{data}"
```

### 项目结构

#### Python SDK 结构

```
packages/auroraview-mcp/
├── pyproject.toml
├── README.md
├── src/
│   └── auroraview_mcp/
│       ├── __init__.py
│       ├── __main__.py          # 入口点
│       ├── server.py            # MCP 服务器主文件
│       ├── discovery.py         # 实例发现
│       ├── connection.py        # CDP 连接管理
│       ├── api_bridge.py        # API 调用桥接
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── discovery.py     # 发现工具
│       │   ├── page.py          # 页面工具
│       │   ├── api.py           # API 工具
│       │   ├── ui.py            # UI 工具
│       │   ├── gallery.py       # Gallery 工具
│       │   ├── debug.py         # 调试工具
│       │   └── dcc.py           # DCC 特定工具
│       └── resources/
│           ├── __init__.py
│           └── providers.py     # 资源提供者
└── tests/
    ├── test_discovery.py
    ├── test_connection.py
    ├── test_api_bridge.py
    └── test_tools.py
```

#### Node.js SDK 结构

```
packages/auroraview-mcp-node/
├── package.json
├── tsconfig.json
├── README.md
├── src/
│   ├── index.ts                 # 入口点
│   ├── server.ts                # MCP 服务器
│   ├── discovery.ts             # 实例发现
│   ├── connection.ts            # CDP 连接
│   ├── midscene/
│   │   ├── index.ts
│   │   ├── agent.ts             # Midscene Agent 封装
│   │   ├── context.ts           # AuroraView 上下文
│   │   └── prompts.ts           # AI 提示模板
│   ├── tools/
│   │   ├── index.ts
│   │   ├── discovery.ts
│   │   ├── page.ts
│   │   ├── api.ts
│   │   ├── ui.ts
│   │   ├── ai.ts                # AI/Midscene 工具
│   │   └── dcc.ts               # DCC 工具
│   └── types/
│       └── index.ts
├── tests/
│   ├── server.test.ts
│   ├── midscene.test.ts
│   └── dcc.test.ts
└── dist/
```

### 配置示例

#### Claude Desktop / CodeBuddy 配置

```json
{
  "mcpServers": {
    "auroraview": {
      "command": "uvx",
      "args": ["auroraview-mcp"],
      "env": {
        "AURORAVIEW_DEFAULT_PORT": "9222",
        "AURORAVIEW_AUTO_CONNECT": "true"
      }
    },
    "auroraview-ai": {
      "command": "npx",
      "args": ["-y", "@auroraview/mcp"],
      "env": {
        "MIDSCENE_MODEL_NAME": "gpt-4o",
        "MIDSCENE_MODEL_API_KEY": "your-api-key"
      }
    }
  }
}
```

#### 开发模式配置

```json
{
  "mcpServers": {
    "auroraview": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/auroraview/packages/auroraview-mcp",
        "run",
        "auroraview-mcp"
      ]
    }
  }
}
```

#### DCC 环境配置

```json
{
  "mcpServers": {
    "auroraview-maya": {
      "command": "uvx",
      "args": ["auroraview-mcp"],
      "env": {
        "AURORAVIEW_DCC_MODE": "maya",
        "AURORAVIEW_SCAN_PORTS": "9222,9223,9224,9225"
      }
    }
  }
}
```

### 使用示例

#### 基本工作流

```
User: 帮我测试 Gallery 的搜索功能

AI: 我来连接 Gallery 并测试搜索功能。

[调用 discover_instances]
→ 发现 1 个实例在端口 9222

[调用 connect(port=9222)]
→ 已连接到 AuroraView Gallery

[调用 get_snapshot]
→ 获取页面结构，找到搜索框

[调用 fill(selector="input[placeholder*='Search']", value="cookie")]
→ 已输入搜索词

[调用 take_screenshot]
→ 截图显示搜索结果

[调用 evaluate("document.querySelectorAll('.sample-card').length")]
→ 返回 1（只显示 Cookie Management Demo）

搜索功能正常工作，输入 "cookie" 后正确过滤出相关示例。
```

#### 运行示例

```
User: 运行 hello_world 示例

AI: [调用 run_sample(name="hello_world")]
→ 示例已启动，PID: 12345

[调用 list_processes]
→ 显示运行中的进程

示例已成功启动，你可以在新窗口中看到效果。
```

#### DCC 环境工作流

```
User: 在 Maya 中帮我测试资产浏览器面板

AI: 我来连接 Maya 中的 AuroraView 面板。

[调用 list_dcc_instances]
→ 发现 Maya 2025 实例，端口 9223，面板: "Asset Browser"

[调用 connect(port=9223)]
→ 已连接到 Maya Asset Browser

[调用 get_dcc_context]
→ 场景: /projects/shot_010.ma
→ 选中: ["pCube1", "pSphere1"]

[调用 ai_act("在资产列表中搜索 'character'")]
→ AI 识别搜索框并输入

[调用 ai_assert("显示了角色资产列表")]
→ 断言通过

[调用 sync_selection]
→ 同步 Maya 和面板的选择状态

资产浏览器面板工作正常。
```

#### AI 自动化工作流 (Midscene)

```
User: 用自然语言测试 Gallery 的完整流程

AI: 我来使用 AI 自动化测试 Gallery。

[调用 ai_act("点击 'Getting Started' 分类")]
→ AI 识别并点击分类按钮

[调用 ai_assert("显示了入门示例列表")]
→ 断言通过

[调用 ai_act("在搜索框中输入 'cookie' 并按回车")]
→ AI 执行搜索操作

[调用 ai_query("{ samples: string[], count: number }")]
→ 返回 { samples: ["Cookie Management Demo"], count: 1 }

[调用 ai_act("点击第一个示例的 'Run Demo' 按钮")]
→ AI 识别并点击按钮

[调用 ai_assert("示例窗口已打开")]
→ 断言通过

Gallery 测试完成，所有功能正常。
```

## 向后兼容性

### 兼容策略

1. **独立包**：作为独立的 Python/Node.js 包发布，不影响现有 AuroraView 功能
2. **可选依赖**：`pip install auroraview[mcp]` 或 `npm install @auroraview/mcp`
3. **版本对齐**：MCP 服务器版本与 AuroraView 主版本保持兼容
4. **DCC 兼容**：支持 Maya 2020+、Blender 3.0+、Houdini 19+、Unreal 5.0+

### 依赖要求

#### Python SDK

```toml
[project]
name = "auroraview-mcp"
requires-python = ">=3.10"  # MCP SDK 要求
dependencies = [
    "mcp>=1.2.0",
    "httpx>=0.25.0",
    "websockets>=12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
midscene = [
    "playwright>=1.40.0",
]
```

#### Node.js SDK

```json
{
  "name": "@auroraview/mcp",
  "dependencies": {
    "@modelcontextprotocol/server": "^1.0.0",
    "playwright": "^1.40.0",
    "zod": "^3.25.0"
  },
  "optionalDependencies": {
    "@anthropic/midscene": "^1.0.0"
  }
}
```

## 实现计划

### Phase 1: Python SDK 核心功能 (v0.3.0) - 2 周

- [x] 项目结构搭建
- [x] 实例发现 (`discover_instances`)
- [x] 连接管理 (`connect`, `disconnect`)
- [x] 页面操作 (`list_pages`, `select_page`, `get_page_info`)
- [x] 基本 API 调用 (`call_api`, `list_api_methods`)
- [x] 截图 (`take_screenshot`)
- [x] 基本测试和文档

### Phase 2: Gallery 集成 (v0.3.1) - 1 周

- [x] Gallery 工具 (`run_gallery`, `stop_gallery`, `get_gallery_status`)
- [x] Gallery 工具 (`get_samples`, `run_sample`, `stop_sample`)
- [x] 源码查看 (`get_sample_source`)
- [x] 进程管理 (`list_processes`, `stop_all_samples`)
- [x] 项目信息 (`get_project_info`)
- [x] 资源提供者实现 (`auroraview://gallery`, `auroraview://project`, `auroraview://processes`)

### Phase 3: DCC 支持 (v0.4.0) - 2 周

- [x] DCC 实例发现 (`list_dcc_instances`)
- [x] DCC 上下文 (`get_dcc_context`)
- [x] DCC 命令执行 (`execute_dcc_command`)
- [x] 选择同步 (`sync_selection`, `set_dcc_selection`)
- [x] 场景信息 (`get_dcc_scene_info`)
- [x] 时间线控制 (`get_dcc_timeline`, `set_dcc_frame`)
- [x] Maya/Blender/Houdini/Nuke/Unreal/3ds Max 类型检测
- [x] 单元测试

### Phase 4: Node.js SDK (v0.4.1) - 2 周

- [ ] TypeScript MCP Server 基础
- [ ] CDP 连接管理
- [ ] 核心工具移植
- [ ] 类型定义

### Phase 5: Midscene 集成 (v0.5.0) - 2 周

- [ ] Midscene Agent 封装
- [ ] AI 工具 (`ai_act`, `ai_query`, `ai_assert`)
- [ ] DCC AI 工具 (`ai_dcc_action`)
- [ ] 上下文增强
- [ ] 提示模板

### Phase 6: 高级功能 (v0.6.0) - 2 周

- [ ] 多实例管理
- [ ] 性能监控
- [ ] 自动化测试集成
- [ ] SSE 传输支持
- [ ] 提示模板 (Prompts)
- [ ] 调试增强 (`get_console_logs`, `get_network_requests`)

## 风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|----------|
| MCP SDK 版本不稳定 | 高 | 锁定稳定版本，关注官方更新 |
| DCC Python 版本限制 | 中 | MCP Server 独立进程，通过 IPC 通信 |
| Midscene 模型成本 | 中 | 支持本地模型，提供缓存机制 |
| CDP 端口冲突 | 低 | 自动端口扫描，支持配置 |

## 参考资料

- [Model Context Protocol 官方文档](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/)
- [Midscene.js 文档](https://midscenejs.com/)
- [AuroraView 项目文档](/guide/getting-started)
- [AuroraView GitHub](https://github.com/try-auroraview/auroraview)

## 项目组织策略

### 推荐方案：混合策略

基于 Anthropic 官方 MCP servers 仓库的组织方式，以及 AuroraView 项目的特点，推荐采用混合策略：

#### Phase 1：在当前项目内开发（快速验证）

```
auroraview/
├── packages/
│   ├── auroraview-sdk/          # 已有 JS SDK
│   ├── auroraview-mcp/          # Python MCP Server
│   │   ├── pyproject.toml       # 独立的 Python 包
│   │   ├── src/
│   │   └── tests/
│   └── auroraview-mcp-node/     # Node.js MCP Server
│       ├── package.json
│       ├── src/
│       └── tests/
```

**选择理由**：

| 方面 | 说明 |
|------|------|
| **快速迭代** | 与 Gallery 一起开发测试 |
| **代码复用** | 直接使用 `auroraview-sdk` 的类型 |
| **版本对齐** | 确保 MCP API 与 AuroraView 兼容 |
| **CI 复用** | 使用现有的 `justfile` 命令 |

#### Phase 2：成熟后考虑拆分（可选）

当 MCP Server 稳定后（v1.0），可以考虑：
- 保留在 monorepo 中（推荐，参考 Anthropic 官方做法）
- 或拆分为独立仓库（如果社区需求强烈）

### 方案对比

#### 方案 A：Monorepo（推荐）

| 方面 | 说明 |
|------|------|
| **代码复用** | 直接使用 `auroraview-sdk` 的类型定义和工具函数 |
| **版本同步** | MCP 版本与 AuroraView 主版本自动对齐 |
| **CI/CD 统一** | 复用现有的 `justfile`、GitHub Actions |
| **测试集成** | 可以直接测试 MCP → Gallery 的完整流程 |
| **开发效率** | 修改 AuroraView API 后可立即更新 MCP |
| **文档统一** | 在同一个 docs 目录下维护 |

**缺点**：
- 增加项目复杂度
- Python 3.7 vs MCP 需要 3.10+（通过独立包解决）
- 发布耦合

#### 方案 B：独立仓库

| 方面 | 说明 |
|------|------|
| **独立发布** | MCP 可以独立版本迭代 |
| **依赖隔离** | 不受主项目 Python 3.7 限制 |
| **社区贡献** | 更容易吸引 MCP 生态贡献者 |
| **轻量安装** | 用户只需安装 MCP 包 |

**缺点**：
- 需要手动维护版本兼容性
- 需要复制部分类型定义
- 需要重新搭建构建系统
- 跨仓库测试更困难

### 依赖隔离策略

```toml
# packages/auroraview-mcp/pyproject.toml
[project]
name = "auroraview-mcp"
requires-python = ">=3.10"  # MCP 独立要求，不影响主项目 3.7
dependencies = [
    "mcp>=1.2.0",
    "httpx>=0.25.0",
]
```

### 发布策略

| 包 | 发布方式 | 版本策略 |
|---|---------|---------|
| `auroraview` | PyPI (maturin) | 主版本 |
| `auroraview-mcp` | PyPI (独立) | 跟随主版本 |
| `@auroraview/mcp` | npm | 跟随主版本 |

### justfile 集成

```makefile
# 在现有 justfile 中添加
mcp-dev:
    cd packages/auroraview-mcp && uv run auroraview-mcp

mcp-test:
    cd packages/auroraview-mcp && uv run pytest

mcp-node-dev:
    cd packages/auroraview-mcp-node && npm run dev

mcp-publish:
    cd packages/auroraview-mcp && uv build && uv publish
```

### 总结

| 维度 | 推荐 | 原因 |
|------|------|------|
| **开发位置** | 当前项目 | 快速迭代、代码复用、版本同步 |
| **包管理** | 独立包 | `auroraview-mcp` 独立于 `auroraview` |
| **Python 版本** | 3.10+ | MCP SDK 要求，不影响主项目 3.7 |
| **发布** | 独立发布 | 可以独立版本迭代 |

## 更新记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2024-12-30 | Draft | 初始草案 |
| 2024-12-30 | Draft v2 | 添加 DCC 集成、Node.js SDK、Midscene 集成分析 |
| 2024-12-30 | Draft v3 | 添加项目组织策略（混合策略） |
| 2024-12-30 | Implementing | Phase 1 实现完成 - Python SDK 核心功能 |
| 2024-12-30 | Implementing | Phase 2 实现完成 - Gallery 集成工具 |
| 2024-12-31 | Implementing | Phase 3 实现完成 - DCC 支持（get_dcc_context, execute_dcc_command, sync_selection, set_dcc_selection, get_dcc_scene_info, get_dcc_timeline, set_dcc_frame） |
