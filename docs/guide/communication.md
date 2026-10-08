# Bidirectional Communication

To expose one explicitly registered host capability to both a panel and an
agent, see [Shared UI and agent tools](./dcc-mcp).

AuroraView provides a complete IPC system for **bidirectional communication** between JavaScript and Python.

## JavaScript API (window.auroraview)

The WebView injects a bridge script that defines a single global entry:

- `window.auroraview.call(method, params?, options?) -> Promise<any>`
  - **JS → Python (request/response)**
  - `options.timeout` (ms) is supported
- `window.auroraview.send_event(event, detail?) -> void`
  - **JS → Python (fire-and-forget)**
- `window.auroraview.on(event, handler) -> () => void`
  - **Python → JS (subscribe)**
- `window.auroraview.off(event, handler?) -> void`
- `window.auroraview.trigger(event, detail?) -> void`
  - **Internal**: used by the backend to deliver Python events and resolve `call()` Promises.
  - Calling `trigger()` from JS does **not** reach Python.

> Tip: If you are writing frontend code, prefer using the TypeScript SDK (`@auroraview/sdk`) via `createAuroraView()` / `getAuroraView()`.

## Python API Overview

- `webview.emit(event_name, payload)`
  - **Python → JS** (delivered to `auroraview.on(event, ...)`)
- `@webview.on(event_name)`
  - **JS → Python** handler for `auroraview.send_event(event, ...)`
- `@webview.bind_call(method)`
  - **JS → Python** handler for `auroraview.call(method, params)`
- `webview.bind_api(api_obj, namespace="api")`
  - Expose an object to JS as `auroraview.api.*` (implemented on top of `call()`)

## Communication API Summary

| Direction | JavaScript API | Python API | Use Case |
|---|---|---|---|
| JS → Python | `auroraview.call(method, params)` | `@webview.bind_call(method)` / `bind_api()` | RPC with return value |
| JS → Python | `auroraview.send_event(event, detail)` | `@webview.on(event)` | Fire-and-forget events |
| Python → JS | *(backend calls `auroraview.trigger`)* | `webview.emit(event, payload)` | Push notifications |
| JS only | `auroraview.on(event, handler)` | - | Receive Python events |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         JavaScript Layer                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  event_bridge (injected)                                   │ │
│  │  - defines window.auroraview                               │ │
│  │  - call()/send_event() -> window.ipc.postMessage(JSON)     │ │
│  │  - trigger() dispatches to auroraview.on handlers           │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↑
                    window.ipc.postMessage(JSON)
                              ↓ ↑
┌─────────────────────────────────────────────────────────────────┐
│                          Rust IPC Layer                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  IpcHandler                                                 │ │
│  │  - routes "event" to WebView.on handlers                    │ │
│  │  - routes "call"  to WebView.bind_call/bind_api handlers     │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              ↓ ↑
                           PyO3 Bindings
                              ↓ ↑
┌─────────────────────────────────────────────────────────────────┐
│                           Python Layer                           │
│  - webview.on(...)                                               │
│  - webview.bind_call(...) / webview.bind_api(...)                 │
│  - webview.emit(...)                                              │
└─────────────────────────────────────────────────────────────────┘
```

## Message Protocol (High-Level)

### JS → Python: `send_event`

```json
{ "type": "event", "event": "export_scene", "detail": { "path": "..." } }
```

### JS → Python: `call`

```json
{ "type": "call", "id": "av_call_...", "method": "api.rename", "params": { "old": "a", "new": "b" } }
```

### Python → JS: `call_result` (internal event)

The backend delivers results by triggering an internal event:

- event name: `__auroraview_call_result`
- payload shape:

```json
{ "id": "av_call_...", "ok": true, "result": { "success": true } }
```

On error:

```json
{ "id": "av_call_...", "ok": false, "error": { "name": "ValueError", "message": "..." } }
```

## Examples

### Python → JavaScript (push events)

```python
# Python side
webview.emit("selection_changed", {"items": ["mesh1", "mesh2"]})
```

```javascript
// JavaScript side
window.auroraview.on("selection_changed", (data) => {
  console.log("Selection:", data.items);
});
```

### JavaScript → Python (fire-and-forget)

```javascript
window.auroraview.send_event("export_scene", { path: "/tmp/out.fbx", format: "fbx" });
```

```python
@webview.on("export_scene")
def handle_export(data):
    print("Exporting to:", data["path"])
```

### JavaScript → Python (RPC with return value)

```python
@webview.bind_call("api.rename_object")
def rename_object(old_name: str, new_name: str):
    # ... perform rename ...
    return {"ok": True, "old": old_name, "new": new_name}
```

```javascript
const result = await window.auroraview.call("api.rename_object", {
  old_name: "cube1",
  new_name: "hero_cube",
});
console.log(result);
```

### API Object Pattern (`auroraview.api.*`)

```python
class MyAPI:
    def get_data(self) -> dict:
        return {"items": [1, 2, 3], "count": 3}

view.bind_api(MyAPI(), namespace="api")
```

```javascript
const data = await window.auroraview.call("api.get_data");
// or (if the backend registers api methods): await auroraview.api.get_data();
console.log(data);
```

## Common Mistakes

::: danger Don’t use browser-native event APIs for JS → Python
```javascript
// WRONG: browser events are not routed to Python
window.dispatchEvent(new CustomEvent("my_event", { detail: { a: 1 } }));

// WRONG: trigger() is for Python → JS delivery; calling it in JS won’t reach Python
window.auroraview.trigger("my_event", { a: 1 });
```
:::

::: tip Correct usage
```javascript
// Fire-and-forget to Python
window.auroraview.send_event("my_event", { a: 1 });

// Request/response to Python
const result = await window.auroraview.call("api.my_method", { a: 1 });
```
:::
