# 文件拖放（File Drop）

AuroraView 提供两种文件拖放语义：浏览器原生 HTML5 拖放，或通过 IPC 转发为
`file_drop_*` 事件以拿到操作系统的绝对路径。两者由
`capture_file_drop` 开关切换，**互斥**，受 wry/WebView2 上游约束影响（详见下文）。

## 默认行为（v0.6+）

所有运行模式默认 `capture_file_drop = false`：

- Standalone / CLI / Packed / DCC（Maya / Houdini / Nuke / Blender）一致；
- 前端可正常使用 `dragover` / `drop` / `DataTransfer` 等 HTML5 API；
- IPC 端不会收到 `file_drop` / `file_drop_hover` / `file_drop_cancelled`。

> ⚠️ **DCC 用户注意（Breaking）**：在 v0.6 之前，DCC 路径**默认开启** IPC 拖放。
> 升级到 v0.6+ 后，DCC 工具如果依赖 `auroraview.on('file_drop', ...)`，必须在
> 构造时显式传入 `capture_file_drop=True`。详见下文「DCC 迁移」。

## 启用 IPC 文件拖放

构造 `AuroraView` 时显式开启：

```python
from auroraview import AuroraView

class MyTool(AuroraView):
    def __init__(self, parent=None):
        super().__init__(
            parent=parent,
            url="...",
            # 把 OS 拖放转发为 IPC file_drop 事件
            capture_file_drop=True,
        )
```

前端订阅事件：

```js
window.addEventListener('auroraviewready', () => {
    window.auroraview.on('file_drop', (data) => {
        // data.paths: string[]   绝对路径
        // data.position: {x, y}  鼠标坐标
        // data.timestamp: number 毫秒
        console.log('files dropped:', data.paths);
    });

    window.auroraview.on('file_drop_hover', (data) => {
        // data.hovering: true
        // data.paths: string[]
    });

    window.auroraview.on('file_drop_cancelled', (data) => {
        // data.hovering: false
        // data.reason: "left_window"
    });
});
```

## ⚠️ 关键限制：HTML5 与 IPC 互斥

由 [wry/WebView2 上游 Bug](https://github.com/tauri-apps/wry/issues/157) 决定：

**只要调用 `with_drag_drop_handler`（即 `capture_file_drop=True`），WebView 内部
所有的 HTML5 `dragenter` / `dragover` / `drop` 事件都会被屏蔽**，无法绕过。

| `capture_file_drop` | HTML5 `drop` | `auroraview.on('file_drop')` |
|---|---|---|
| `False`（默认） | ✅ 可用 | ❌ 不触发 |
| `True` | ❌ 完全失效 | ✅ 可拿到绝对路径 |

如果你的页面使用 Monaco / CodeMirror / 富文本组件需要 HTML5 拖放上传，**保持
`capture_file_drop=False`**，并通过 web-stack 处理（`DataTransfer.files` 给文件
名 + 字节流，但**不暴露绝对路径**——这是 web 安全约束）。

如果你的工具需要绝对路径（导入素材、加载场景），开启 `capture_file_drop=True`。

## 三态契约（Python）

`capture_file_drop` 在 Python 层是 `Optional[bool]` 三态：

| 取值 | 含义 |
|---|---|
| `None`（默认，未传） | 透传到底层，由 Rust `unwrap_or(false)` 兜底为 `False` |
| `True` | 显式启用 |
| `False` | 显式禁用 |

中间层任何 `setdefault('capture_file_drop', False)` / `or False` /
`get('capture_file_drop', True)` 都会破坏三态语义，CI 脚本
`scripts/ci/check_capture_file_drop_defaults.py` 会拦截这些违规模式。

## 多 Tab Browser 模式：不可用

在 `auroraview-browser` 多 Tab 模式（controller + 业务 tab 多个 WebView 叠加）下，
`capture_file_drop` **不可配置**：所有业务 tab 与 controller 永远不挂
`with_drag_drop_handler`。

原因：多 WebView 叠加场景下，OS 拖放在 controller 与业务 tab 像素边界穿越时，
状态机无法收敛（详见 [RFC 0016 §2.1](https://github.com/try-auroraview/auroraview/blob/main/docs/rfcs/0016-browser-mode-disable-capture-file-drop.md#21-why-business-tabs-attached-controller-not-attached-is-unworkable)）。

**替代方案**：把需要绝对路径的页面改造为顶层 `AuroraView` 实例（独立窗口、单
WebView），在该实例上设 `capture_file_drop=True`。

## 子窗口（`window.open` / `new_window_mode="child_webview"`）：永不挂载

通过 `window.open` 创建的 child window 运行在独立事件循环中、与主窗 IPC 通道
不连通。AuroraView 永远不会给 child window 注册 `with_drag_drop_handler`，无论
父窗的 `capture_file_drop` 是何值。

主窗自身的 `file_drop*` 事件不受影响。需要在 child window 内拿到拖入内容，请
直接使用浏览器原生 HTML5 API。

## CLI 与打包

### `auroraview run`

```bash
# 单向 flag（standalone CLI 没有 IPC 后端，这个 flag 主要用于 parity 测试）
auroraview run --url https://example.com --capture-file-drop
```

### `auroraview pack`

```bash
# 一对显式 flag，互斥。不传则沿用 manifest / code default。
auroraview pack --config auroraview.pack.toml --capture-file-drop
auroraview pack --config auroraview.pack.toml --no-capture-file-drop
```

### Manifest

```toml
[security]
capture_file_drop = true   # 可选；省略 = 使用代码默认 (false)
```

合并优先级（高 → 低）：CLI flag > `[security].capture_file_drop` > code 默认 `false`。

### Packed 运行时 env var 逃生口

终端用户拿到 packed exe 后无法重新打包，可用环境变量临时覆盖：

```bash
# 强制开启
$env:AURORAVIEW_CAPTURE_FILE_DROP = "1"   # 或 true / on / yes / enabled
auroraview-packed.exe

# 强制关闭
$env:AURORAVIEW_CAPTURE_FILE_DROP = "0"   # 或 false / off / no / disabled
auroraview-packed.exe
```

取值大小写不敏感、自动 trim。无效值打 `tracing::warn!` 并沿用 overlay 写入值。

> ⚠️ Browser 模式下 packed runtime 不读 `capture_file_drop`，env var 设了**也不会
> 生效**（也不会有提示日志）。这是 RFC 0016 设计的 trade-off。

## 故障排查

如果你设置了 `capture_file_drop=True` 但 `auroraview.on('file_drop', ...)`
没收到事件，请检查：

1. **前端是否仍在订阅 HTML5 事件**：`window.addEventListener('drop', ...)`
   会因上游 Bug 完全失效，与 IPC 模式互斥（详见上文「关键限制」）；
2. **IPC 桥是否就绪**：在 `window.addEventListener('auroraviewready', ...)`
   回调内订阅，避免太早注册；
3. **该 webview 是否真的挂了 handler**：child window / Browser 模式下的
   webview 永远不挂（详见上文）；
4. **Python 层中间层是否蹋平了三态**：CI grep 脚本会在合并前拦截，但本地直接
   编辑 Python 文件时，运行 `vx python scripts/ci/check_capture_file_drop_defaults.py`
   主动检查。

## DCC 迁移（v0.5.x → v0.6+）

之前 DCC 路径默认 `capture_file_drop=True`，自动接管 OS 拖放并转发为 IPC。
v0.6+ 起 DCC 与其它模式一致默认 `False`。

**迁移**：在你的 DCC 工具构造 `AuroraView` 时显式传 `capture_file_drop=True`：

```python
# Before (v0.5.x): 自动启用 IPC 拖放
class MyMayaTool(AuroraView):
    def __init__(self, parent=None):
        super().__init__(parent=parent, url="...")

# After (v0.6+): 必须显式传
class MyMayaTool(AuroraView):
    def __init__(self, parent=None):
        super().__init__(
            parent=parent,
            url="...",
            capture_file_drop=True,
        )
```

**为什么改默认值？**

- 心智模型一致：所有模式同一行为，零特例；
- 与上游 Bug 解耦：v0.5.x 的「DCC 默认 True」实际是建立在 wry/WebView2
  上游 Bug 副作用上的「伪稳态」，前端 HTML5 拖放被屏蔽用户却不知道；
- 迁移成本极低：一行代码。

## 相关 RFC

- [RFC 0013 总览](https://github.com/try-auroraview/auroraview/blob/main/docs/rfcs/0013-default-file-drop-improve.md)
- [RFC 0015 Helper](https://github.com/try-auroraview/auroraview/blob/main/docs/rfcs/0015-attach-drag-drop-helper.md)
- [RFC 0016 Browser 模式](https://github.com/try-auroraview/auroraview/blob/main/docs/rfcs/0016-browser-mode-disable-capture-file-drop.md)
- [RFC 0017 Python 三态](https://github.com/try-auroraview/auroraview/blob/main/docs/rfcs/0017-python-capture-file-drop-tristate.md)
