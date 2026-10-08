# 双向通信

同一宿主能力需要同时供面板与 Agent 调用时，请参阅[UI 与 Agent 工具契约](./dcc-mcp)。

AuroraView 提供完整的 IPC 系统，用于 **JavaScript 与 Python 的双向通信**。

## JavaScript API（window.auroraview）

WebView 会注入桥接脚本，提供一个全局唯一入口：

- `window.auroraview.call(method, params?, options?) -> Promise<any>`
  - **JS → Python（请求/响应）**
  - 支持 `options.timeout`（毫秒）
- `window.auroraview.send_event(event, detail?) -> void`
  - **JS → Python（即发即忘）**
- `window.auroraview.on(event, handler) -> () => void`
  - **Python → JS（订阅）**
- `window.auroraview.off(event, handler?) -> void`
- `window.auroraview.trigger(event, detail?) -> void`
  - **内部接口**：后端用于投递 Python 事件，以及解析 `call()` 的 Promise。
  - 在 JS 里主动调用 `trigger()` 并不会把消息发送到 Python。

> 建议：前端工程优先使用 TypeScript SDK（`@auroraview/sdk`），通过 `createAuroraView()` / `getAuroraView()` 获取客户端。

## Python API 概览

- `webview.emit(event_name, payload)`
  - **Python → JS**（由 `auroraview.on(event, ...)` 接收）
- `@webview.on(event_name)`
  - **JS → Python**（对应 `auroraview.send_event(event, ...)`）
- `@webview.bind_call(method)`
  - **JS → Python**（对应 `auroraview.call(method, params)`）
- `webview.bind_api(api_obj, namespace="api")`
  - 将对象暴露到 JS 为 `auroraview.api.*`（基于 `call()` 实现）

## 通信 API 总览

| 方向 | JavaScript API | Python API | 使用场景 |
|---|---|---|---|
| JS → Python | `auroraview.call(method, params)` | `@webview.bind_call(method)` / `bind_api()` | 带返回值的 RPC |
| JS → Python | `auroraview.send_event(event, detail)` | `@webview.on(event)` | 即发即忘事件 |
| Python → JS | *(后端调用 `auroraview.trigger`)* | `webview.emit(event, payload)` | 推送通知 |
| 仅 JS | `auroraview.on(event, handler)` | - | 接收 Python 事件 |

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                         JavaScript 层                            │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  event_bridge（注入脚本）                                   │ │
│  │  - 定义 window.auroraview                                   │ │
│  │  - call()/send_event() -> window.ipc.postMessage(JSON)      │ │
│  │  - trigger() 分发到 auroraview.on 的订阅者                  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↑
                    window.ipc.postMessage(JSON)
                              ↓ ↑
┌─────────────────────────────────────────────────────────────────┐
│                          Rust IPC 层                             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  IpcHandler                                                 │ │
│  │  - "event" 路由到 WebView.on 的处理器                       │ │
│  │  - "call"  路由到 WebView.bind_call/bind_api 的处理器        │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↑
                           PyO3 绑定
                              ↓ ↑
┌─────────────────────────────────────────────────────────────────┐
│                           Python 层                              │
│  - webview.on(...)                                               │
│  - webview.bind_call(...) / webview.bind_api(...)                 │
│  - webview.emit(...)                                              │
└─────────────────────────────────────────────────────────────────┘
```

## 消息协议（高层）

### JS → Python：`send_event`

```json
{ "type": "event", "event": "export_scene", "detail": { "path": "..." } }
```

### JS → Python：`call`

```json
{ "type": "call", "id": "av_call_...", "method": "api.rename", "params": { "old": "a", "new": "b" } }
```

### Python → JS：`call_result`（内部事件）

后端通过触发内部事件来返回结果：

- 事件名：`__auroraview_call_result`
- 负载结构：

```json
{ "id": "av_call_...", "ok": true, "result": { "success": true } }
```

失败时：

```json
{ "id": "av_call_...", "ok": false, "error": { "name": "ValueError", "message": "..." } }
```

## 示例

### Python → JavaScript（推送事件）

```python
# Python 端
webview.emit("selection_changed", {"items": ["mesh1", "mesh2"]})
```

```javascript
// JavaScript 端
window.auroraview.on("selection_changed", (data) => {
  console.log("Selection:", data.items);
});
```

### JavaScript → Python（即发即忘）

```javascript
window.auroraview.send_event("export_scene", { path: "/tmp/out.fbx", format: "fbx" });
```

```python
@webview.on("export_scene")
def handle_export(data):
    print("Exporting to:", data["path"])
```

### JavaScript → Python（带返回值 RPC）

```python
@webview.bind_call("api.rename_object")
def rename_object(old_name: str, new_name: str):
    # ... 执行重命名 ...
    return {"ok": True, "old": old_name, "new": new_name}
```

```javascript
const result = await window.auroraview.call("api.rename_object", {
  old_name: "cube1",
  new_name: "hero_cube",
});
console.log(result);
```

### API 对象模式（`auroraview.api.*`）

```python
class MyAPI:
    def get_data(self) -> dict:
        return {"items": [1, 2, 3], "count": 3}

view.bind_api(MyAPI(), namespace="api")
```

```javascript
const data = await window.auroraview.call("api.get_data");
// 或（若后端注册了 api 方法）：await auroraview.api.get_data();
console.log(data);
```

## 常见错误

::: danger 不要用浏览器原生事件 API 做 JS → Python
```javascript
// 错误：浏览器事件不会被路由到 Python
window.dispatchEvent(new CustomEvent("my_event", { detail: { a: 1 } }));

// 错误：trigger() 用于 Python → JS 投递；在 JS 里调用不会发送到 Python
window.auroraview.trigger("my_event", { a: 1 });
```
:::

::: tip 正确用法
```javascript
// 即发即忘到 Python
window.auroraview.send_event("my_event", { a: 1 });

// 请求-响应到 Python
const result = await window.auroraview.call("api.my_method", { a: 1 });
```
:::
