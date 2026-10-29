# API Reference

This section provides detailed API documentation for AuroraView.

## Integration Modes

AuroraView provides three integration modes:

| Mode | Class | Description |
|------|-------|-------------|
| **Desktop** | `WebView` + `show()` | Independent window with own event loop |
| **Native (HWND)** | `WebView` + `parent=hwnd` | Embedded via HWND, no Qt dependency |
| **Qt** | `QtWebView` | Embedded as Qt widget child |

## Core Classes

### WebView

The base WebView class for creating web-based UI. Used in Desktop and Native modes.

```python
from auroraview import WebView

# Desktop Mode
webview = WebView.create(
    title="My App",
    url="http://localhost:3000",
    width=1024,
    height=768
)
webview.show()  # Blocking, owns event loop

# Native Mode (HWND)
webview = WebView.create(
    title="My Tool",
    parent=parent_hwnd,  # HWND from non-Qt app
    mode="owner",
)
```

[Full WebView API →](/api/webview)

### QtWebView

Qt widget wrapper for DCC integration. Used in Qt Mode.

```python
from auroraview import QtWebView

# Qt Mode
webview = QtWebView(
    parent=parent_widget,  # Qt widget
    url="http://localhost:3000"
)
```

[Full QtWebView API →](/api/qt-webview)

### AuroraView

High-level wrapper with HWND access and API binding.

```python
from auroraview import AuroraView

webview = AuroraView(
    url="http://localhost:3000",
    api=MyAPI()
)
```

[Full AuroraView API →](/api/auroraview)

## Convenience Functions

### run_desktop

Launch a standalone desktop application:

```python
from auroraview import run_desktop

run_desktop(
    title="My App",
    url="http://localhost:3000",
    width=1024,
    height=768
)
```

Pass `icon=` to customize the native window icon (title bar and taskbar).
Supported formats: PNG (recommended), ICO, JPEG, BMP, GIF. This is the runtime
window icon; it is separate from the packaged executable icon set by
`auroraview pack --icon`.

```python
run_desktop(
    title="My App",
    width=1024,
    height=768,
    url="http://localhost:3000",
    icon="path/to/my-icon.png",
)
```

### Legacy Aliases

> **Note**: The following legacy aliases are no longer available:
> - `run_standalone`: Removed. Use `run_desktop` instead.

```python
from auroraview import run_desktop

run_desktop(
    title="My App",
    html="<h1>Hello</h1>"
)
```

## Child Window Support

### ChildContext

Context manager for creating child-aware WebViews:

```python
from auroraview import ChildContext

with ChildContext() as ctx:
    webview = ctx.create_webview(
        title="My Example",
        html="<h1>Hello</h1>"
    )
    
    if ctx.is_child:
        ctx.emit_to_parent("ready", {"status": "ok"})
    
    webview.show()
```

### Mode Detection

```python
from auroraview import is_child_mode, get_parent_id, get_child_id

if is_child_mode():
    print(f"Parent: {get_parent_id()}")
    print(f"Child ID: {get_child_id()}")
```

[Full Child Window Guide →](/guide/child-windows)

## Utility Functions

### path_to_file_url

Convert local path to file:// URL:

```python
from auroraview import path_to_file_url

url = path_to_file_url("C:/path/to/file.html")
# Returns: file:///C:/path/to/file.html
```

## Type Definitions

### WindowEventData

```python
from auroraview.core.events import WindowEventData

@webview.on_resized
def on_resized(data: WindowEventData):
    print(f"Size: {data.width}x{data.height}")
    print(f"Position: ({data.x}, {data.y})")
```

### Signal

Qt-like signal system:

```python
from auroraview import Signal

class MyTool(WebView):
    selection_changed = Signal(list)
    progress_updated = Signal(int, str)
```

## JavaScript API

### auroraview Object

Available in the browser context:

```javascript
// Call Python methods
const result = await auroraview.call('api.method', { param: 'value' });

// Send events to Python
auroraview.send_event('event_name', { data: 'value' });

// Listen for Python events
auroraview.on('event_name', (data) => {
    console.log(data);
});

// Access shared state
auroraview.state.key = 'value';
```
