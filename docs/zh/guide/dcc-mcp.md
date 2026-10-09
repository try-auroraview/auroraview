# UI 与 Agent 共用工具能力

AuroraView 面板与 Agent 可以调用同一个显式注册的宿主能力。独立的
`auroraview-dcc-mcp` Python 包负责这份契约，不负责渲染、DCC 场景或第二套 MCP 服务。

## 包的职责

| 包 | 职责 |
| --- | --- |
| `auroraview` | 原生 WebView、页面通信与 Python 集成 |
| `@auroraview/sdk` | 前端调用与事件订阅 |
| `auroraview-dcc-mcp` | 显式工具、参数契约、共享业务函数与注册清理 |
| `dcc-mcp-core` | MCP/REST、Skills、发现与宿主执行桥 |
| 宿主适配器 | 场景 API、宿主主线程调度、原生区域与应用生命周期 |

契约包支持 Python 3.7+，Core 范围为 `>=0.20.25,<0.21`。导入时不加载 AuroraView
原生扩展、Qt、Blender 或 Unreal 模块。渲染后端与原生插件各自保留实际支持版本。

Schema 使用 JSON Schema Draft 7、2019-09 或 2020-12 的对象形式；省略 `$schema`
时使用 Draft 7。较旧或未知方言、远程 schema 引用会被拒绝。本地引用，以及包含
`$ref` 的业务字面数据保持可用。

## 声明能力

```python
from auroraview_dcc_mcp import Tool, ToolSet

# host 由应用适配器提供，场景操作留在宿主主线程。
# scene_snapshot 必须读取宿主实际状态。
tools = ToolSet(
    "studio-scene",
    [Tool(
        "scene.rename",
        "重命名对象并读取结果场景",
        input_schema={
            "type": "object",
            "properties": {
                "object_id": {"type": "string"},
                "name": {"type": "string", "minLength": 1},
            },
            "required": ["object_id", "name"],
            "additionalProperties": False,
        },
        handler=host.rename,
        readback=host.scene_snapshot,
        output_schema={
            "type": "object",
            "properties": {"result": {}, "scene": {"type": "object"}},
            "required": ["result", "scene"],
        },
        destructive=True,
    )],
    dcc="maya",
)

ui = tools.bind(webview)
agent = tools.attach(existing_host_server)
```

`existing_host_server` 是宿主正在运行的 `DccServerBase`。挂接使用它的公共 Skill
加载接口与已有执行桥，不另启服务，也不覆盖宿主调度器。重复 Skill 名称会被拒绝。
工具名与 schema 都需要声明；任意按钮不会被自动发现或转换成工具。

`dcc` 应填写适配器的宿主标识，Core 按宿主过滤发现结果时才能找到该 Skill。
UI/session 仍调用 `scene.rename`；Core 的 MCP 工具名不允许点号，因此注册名为
`studio-scene__scene_rename`，映射通过 `agent.method_names` 提供。映射后重名会被拒绝。

MCP 将业务参数放在显式 `params` 外层中：

```json
{
  "name": "studio-scene__scene_rename",
  "arguments": {"params": {"object_id": "cube-1", "name": "Hero"}}
}
```

Core 在调用 Skill 脚本前会过滤顶层私有键。外层结构保留完整业务参数，使共享校验器
拿到与 UI 相同的数据；注册的 MCP input schema 也明确描述这层结构。

页面沿用现有通信 API：

```javascript
const response = await window.auroraview.call('scene.rename', {
  object_id: selectedId,
  name: 'Hero'
})
renderScene(response.scene)
```

业务函数与可选场景回读在同一个宿主调度回调中执行。配置回读后，返回值为
`{result, scene}`；回读工具必须提供 `output_schema`，它描述整个返回值。UI 与 Agent
沿用同一份 JSON Schema 校验，线程不匹配时明确拒绝调用。

## 宿主调度

宿主将 WebView 的 call dispatcher 与 Core 执行桥接到自己的主线程。HTTP、Rust
或渲染工作线程不能直接访问 `bpy`、Unreal 对象或 Qt 控件。工具注册不会创建新的宿主循环。

新建 Qt 面板服务时，现有框架导入保持可用：

```python
from auroraview.dcc_mcp import AuroraViewAdapter, AuroraViewQtHost, start_server

adapter = AuroraViewAdapter(webview, host_dcc="maya")
host_loop = AuroraViewQtHost(dispatcher)
host_loop.start()  # 必须位于 Qt 应用线程
server = start_server(adapter, dispatcher=dispatcher)
server.start()
```

此调用方拥有新建的服务与宿主循环。已经运行 DCC-MCP 的宿主应使用
`tools.attach(existing_host_server)`，保留现有调度器。旧 `start_server` 的
inline 模式为独立运行调用方保留，不能用来证明嵌入宿主的线程安全。
`AuroraViewQtHost.stop()` 会关闭其 dispatcher，因此只有拥有该 dispatcher 的调用方才应创建此循环。

## 所有权与清理

`ToolSet` 拥有业务回调。每个 UI/MCP binding 只拥有自己的注册。关闭一个 binding
会使该入口失效，其他消费者与借用服务继续运行。关闭拥有者 `ToolSet` 会使其所有
入口失效并释放业务回调。已经执行的宿主任务可能完成，失效后发起的新调用会被拒绝。

通用 view 需要显式调用 `ui.close()`。存在公共 `on_closed` 钩子的 view 会自动订阅
绑定清理；独立面板若拥有整个工具集，也必须关闭该拥有者。清理失败会明确报告并允许重试，
不能把失败当作清理完成。

宿主集成应将宿主拥有的 `ToolSet` 与有效的 `AgentBinding` 保留在面板生命周期之外。
关闭面板只释放其 UI binding、借用 session、订阅和 view；重新打开时，将新 view
绑定到同一个 owner。宿主集成卸载时再关闭 owner。

使用公开 Core 0.20.41 与 facade 0.1.0 时，`AgentBinding.close()` 会撤销 token 并
卸载可调用工具，但保留 SkillCatalog 元数据。公开 registry 注销不能移除这些元数据。
因此，用同名新 owner 替换 Agent 注册目前仍会失败；正常面板重开复用有效注册。
已经关闭的 trampoline 仍拒绝旧调用。完整移除需要 Core 提供拥有明确所有权的目录生命周期 API。

业务工具集的借用方使用独立 session：

```python
session = tools.borrow()
available = session.list_tools()
response = session.call("scene.rename", {"object_id": selected_id, "name": "Hero"})
unsubscribe = session.subscribe("scene.changed", on_scene_changed)
unsubscribe()  # 幂等，只注销这条订阅
session.close()  # 释放本面板的订阅，tools/server 继续运行
```

事件订阅通过 `ToolSet(..., subscribe=host.subscribe)` 注入宿主现有的
`subscribe(event, callback)` 函数，它必须返回 unsubscribe 函数。宿主负责事件投递与
线程调度，本包不创建第二套事件总线。拥有者关闭或释放后，借用 session 会拒绝调用。

调用和订阅操作需要位于工具拥有者线程；存在宿主事件资源时，unsubscribe/close 也遵循此约束。
其他线程发起关闭会立即使入口失效，并报告待清理资源；需要回到拥有者线程重试，才能注销宿主资源。

宿主 unsubscribe 回调必须同步完成。返回 `False`、awaitable 或 Future 类对象会违反契约
（`ContractError`），清理资源会保持待处理状态。应保留 session 或 binding，在修复适配器失败后，
回到拥有者线程重试 `close()`。重入关闭不会重复移除同一订阅，也不会提前释放待清理资源；
外层清理成功时会自行完成，无需再重试。

## 安装与迁移

独立契约包与原生 wheel 分开构建、发行。请使用固定的
[preview.2 发行](https://github.com/try-auroraview/auroraview/releases/tag/auroraview-dcc-mcp-v0.1.0-preview.2)
及其不可变的
[wheel 地址](https://github.com/try-auroraview/auroraview/releases/download/auroraview-dcc-mcp-v0.1.0-preview.2/auroraview_dcc_mcp-0.1.0-py3-none-any.whl)。
请在实际宿主的 Python 环境中安装，并替换 `<host-python>`：

```sh
vx uv pip install --python <host-python> "auroraview-dcc-mcp @ https://github.com/try-auroraview/auroraview/releases/download/auroraview-dcc-mcp-v0.1.0-preview.2/auroraview_dcc_mcp-0.1.0-py3-none-any.whl#sha256=3965ce8cb67889b12dbf28efaf0fd2d93a26032e047d2b1fb7d5ba401eb72cd7"
```

地址固定了 wheel 的 SHA-256。仅在需要可选 Core 依赖时，将 requirement 中的
`auroraview-dcc-mcp` 改为 `auroraview-dcc-mcp[core]`。
wheel 元数据版本仍为 `0.1.0`，不可变发行标签用于选定这次构建。
GitHub 预览交付与 PyPI 发行是独立渠道；本指南不表示已经上架 PyPI。

原有 `auroraview.dcc_mcp.AuroraViewAdapter`、`AuroraViewQtHost` 和 `start_server`
保持兼容，它们提供的四个面板检查/导航工具与新增的显式场景能力分别存在。
把新契约包安装到实际宿主的 Python 环境；开发路径依赖或复制源文件不能替代公开发行消费。

[双向通信](./communication)说明 RPC 与事件方向。
[包源码与测试](https://github.com/try-auroraview/auroraview/tree/main/packages/auroraview-dcc-mcp)
提供注册、失效和借用服务行为的实现证据。包与 Core 传输测试不能替代 Blender/Unreal
原生插件验收。每个消费者还需要固定公开产物，在支持的宿主版本中验证场景读回、
可用的 Undo 和生命周期清理。

[Maya Outliner 示例](https://github.com/try-auroraview/auroraview-maya-outliner)
已消费历史 preview.1 wheel 与 Core 0.20.41。
[Maya 2026 standalone 验收凭据](https://github.com/try-auroraview/auroraview-maya-outliner/blob/bc934e7e454c59b8f2fd707bf686c68ef432e55d/docs/receipts/maya-contract-preview-1.json)
记录了 HTTP/MCP 发现、主线程重命名与场景读回、Undo 恢复，以及回调和服务清理。
默认 Vue UI 保留旧路由。
[可选消费者指南（draft PR #53）](https://github.com/try-auroraview/auroraview-maya-outliner/blob/49aa3ae8ffc5c601bd86849fe09bd145177a682e/docs/SHARED_TOOLS.md)
使用 `OutlinerRuntime(existing_server, dockable=True)`，只挂接一次共享工具。
由宿主持有 runtime：`open()` 打开或重新打开面板，`close_view()` 只关闭面板，
`close()` 留到宿主最终卸载时调用。每个面板借用同一个 owner，已有 Core 服务与
dispatcher 仍由宿主拥有。面板在 UI 绑定前选定共享重命名 handler，以兼容公开的 AuroraView 0.5.12。

[Maya 2026 会话记录](https://github.com/try-auroraview/auroraview-maya-outliner/blob/49aa3ae8ffc5c601bd86849fe09bd145177a682e/docs/receipts/maya-gui-partial-2026-10-09.json)
在 2026-10-09 的 `f1231286` 上观察到原生右侧停靠区中的 Vue、UI/MCP 重命名及场景读回、
事件显示、前台 Undo 和面板清理，借用的 owner 与服务保持运行。
仅修改 CSS 的 `434822e3` 检查验证了重命名输入框的行定位，未验证完整的重命名提交。
生命周期实现 `96c98546` 已通过受控测试与[源码 CI](https://github.com/try-auroraview/auroraview-maya-outliner/actions/runs/37876141244)，
其 GUI 关闭/重开验收仍待完成。浮动/重新停靠、窗口调整大小、原生关闭与多 DPI 验收也仍待完成。

[Blender 原生 HTML 消费者](https://github.com/try-auroraview/auroraview-blender/blob/1401b6fec2fdfeae43d565eb8f1428b1699e6260/docs/native-web.md)
从同一个 `ToolSet` 借用 `ToolSession`，Blender 负责场景调度和 GPU 区域。
[Windows Blender 5.1.1 的已记录探针](https://try-auroraview.github.io/evidence/blender-2026-10-09.json)
分别通过 36 项生命周期检查和 36 项公开 wheel/SDK/场景检查，包含实际 `bpy` 读回、
事件隔离及自有资源清理。契约 wheel 使用 preview.1，扩展与 renderer 使用本地实验候选；完整键盘/IME、焦点、
前台正常 Stop 和用户验收仍待完成，这些探针也未验证 MCP 传输发现。
宿主 unsubscribe 必须同步完成，失败时抛异常；公开 session 不支持把 `False`
或 awaitable 返回值作为清理结果。

[Unity Core 消费者（draft PR #1）](https://github.com/try-auroraview/auroraview-unity/blob/ea25683aa9167ecc6c8156ec85422d91b35a6053/docs/core-runtime.md)
在外部 Python 中使用公开 Core 0.20.41 与 preview.1 契约 wheel（元数据版本 0.1.0），不在 Unity 内嵌入 Python。
当前用户命名管道调用与 WebView 共用 C# `SceneContracts`；Unity 仍在
`EditorApplication.update` 中执行场景访问。先针对绑定的 Editor PID 创建 `SceneTools` 实例，
再在已有服务注册的执行线程中调用 `tools.attach(existing_server)` 来借用它；
面板或 binding 关闭时，服务仍由宿主拥有。
新建自有 standalone Core 服务需要显式命令，与打开面板分开。公开预览 `12210315`
早于此消费者。已观察到 Editor 启动，真实 Editor Core 与 GUI 验收仍为 `not_run`。
安装、所有权及验证细节见消费者指南。
