---
name: qt-to-auroraview-migration
description: Convert an existing Qt/PySide/PyQt desktop project (QWebEngineView-based UI, QMainWindow browsers, Qt DCC tools) into an AuroraView project so it ships a lighter, Rust-powered WebView and gets full MCP automation for free. Use this skill whenever the user asks to "migrate", "convert", "port" a Qt/PySide/PyQt app to AuroraView, or when they want MCP-controllable Qt tooling.
---

# Qt → AuroraView migration skill

This skill turns an existing Qt-based Python project (typically one that uses
`QWebEngineView`, a custom `QMainWindow`, or a DCC tool dialog with embedded HTML)
into an **AuroraView** project with:

- A native Rust-powered WebView (~5 MB vs ~120 MB Qt WebEngine)
- Unified `create_webview()` entry point (standalone / Qt parent / HWND)
- Bidirectional Python ↔ JavaScript bridge (`webview.emit` / `@webview.on`)
- **Full MCP control out of the box** via `dcc-mcp-core`'s gateway — every
  AuroraView window registers itself into the gateway and exposes a CDP bridge,
  so agents can click, fill, screenshot, and call Python APIs over standard MCP
  without the user writing any Python glue

## When to use this skill

Use it when you see any of these signals in the source project:

1. `from PySide6.QtWebEngineWidgets import QWebEngineView` (or PySide2 / PyQt5 / PyQt6)
2. `QWebChannel` + `registerObject` for JS↔Python IPC
3. A DCC-embedded Qt dialog that loads an HTML/React/Vue frontend
4. A `QMainWindow` whose central widget is basically a browser
5. The user says "convert/migrate/port this Qt tool to AuroraView" or
   "I want to control this Qt app with MCP"

## Decision tree

```text
Is there a QWidget parent (Maya/Houdini/Nuke/3ds Max)?
├── Yes → use QtWebView path (create_webview(parent=qwidget, ...))
└── No
    ├── Is there a native HWND (Unreal, C++ host)?
    │   └── Yes → use HWND path (create_webview(parent=hwnd, ...))
    └── No → standalone (create_webview(url=..., ...))
```

All three paths return the **same** WebView API; only the `parent` argument differs.

## Migration playbook

Perform these steps in order. Each has a concrete before/after snippet so you
can grep-and-replace safely.

### Step 1 — Dependencies

Replace Qt WebEngine with AuroraView. Keep `qtpy` / a Qt binding only if the
tool still needs Qt widgets around the webview (toolbars, dock panels, DCC
integration).

```toml
# pyproject.toml — remove
# "PySide6-WebEngine"
# "PyQtWebEngine"
# "auroraview-mcp"              # the standalone Python MCP pkg was retired; see #364

# pyproject.toml — add
"auroraview>=0.4.19"            # core
"auroraview[qt]>=0.4.19"        # if embedding inside a Qt host
# MCP control now comes from dcc-mcp-core's gateway + auroraview-cli; no extra
# Python dep is needed on the project itself. Install the tooling separately:
#   pip install dcc-mcp-core    # gateway + skill runtime (PyPI)
#   auroraview-cli skills install --target cursor    # wire agent tools
```

### Step 2 — Replace `QWebEngineView`

```python
# BEFORE
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

view = QWebEngineView(parent)
view.setUrl(QUrl("http://localhost:3000"))
view.show()
```

```python
# AFTER
from auroraview import create_webview

webview = create_webview(parent=parent, url="http://localhost:3000")
webview.show()
```

When there is no Qt parent, pass nothing:

```python
webview = create_webview(url="http://localhost:3000", title="My Tool")
webview.show()
```

### Step 3 — Replace `QWebChannel` IPC

AuroraView ships a first-class bridge — drop `QWebChannel`, `registerObject`,
and the custom JS adapter entirely.

```python
# BEFORE — Qt WebChannel
from PySide6.QtWebChannel import QWebChannel
class Bridge(QObject):
    @Slot(dict, result=dict)
    def export_scene(self, data):
        ...
channel = QWebChannel(view.page())
channel.registerObject("bridge", Bridge())
view.page().setWebChannel(channel)
```

```python
# AFTER — AuroraView
@webview.on("export_scene")
def handle_export(data):
    return {"ok": True, "path": data["path"]}

# Python → JS
webview.emit("scene_updated", {"frame": 120})
```

On the JS side, replace the `qtwebchannel.js` adapter with the AuroraView SDK:

```js
// BEFORE
new QWebChannel(qt.webChannelTransport, (channel) => {
  channel.objects.bridge.export_scene({ path });
});

// AFTER
import { av } from "@auroraview/sdk";
await av.call("export_scene", { path });
av.on("scene_updated", (data) => console.log(data));
```

### Step 4 — Replace `QMainWindow` browser shells

If the project is a custom browser (tabs, URL bar, history), keep the Qt chrome
but swap every `QWebEngineView` for AuroraView. The `@examples/qt_browser.py`
file in this repo is the before; here is the AFTER pattern:

```python
from auroraview import create_webview

class BrowserTab(QWidget):
    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.webview = create_webview(parent=self, url=url)
        layout.addWidget(self.webview.widget())  # expose the native widget
```

Note: for native tab switching/reloading, call `webview.load_url(...)`,
`webview.reload()`, `webview.back()`, `webview.forward()`.

### Step 5 — DCC integration (Maya / Houdini / Nuke / 3ds Max)

Thread-dispatcher backends are already bundled. The migration is literally:

```python
# BEFORE
ptr = omui.MQtUtil.mainWindow()
parent = wrapInstance(int(ptr), QWidget)
view = QWebEngineView(parent)
view.setUrl(QUrl("http://tool"))

# AFTER
from auroraview import create_webview
webview = create_webview(parent=parent, url="http://tool")  # autoloads qt backend
```

For non-Qt DCCs (Unreal) pass the HWND as an `int`:

```python
webview = create_webview(parent=unreal_hwnd, url="http://tool")
hwnd = webview.get_hwnd()  # needed by the host engine
```

### Step 6 — Enable MCP control (the "for free" part)

Once the app is on AuroraView, agents drive it over MCP with **zero extra
code on the project side**. AuroraView windows register themselves into the
shared `dcc-mcp-core` gateway and expose their CDP endpoint automatically;
agents discover them and call tools through the gateway.

```bash
# One-time setup on the developer machine:
pip install dcc-mcp-core                         # gateway + MCP runtime
auroraview-cli skills install --target cursor    # or --target claude / all

# Then simply run the migrated app:
python my_tool.py     # AuroraView registers itself with the gateway on start
```

Agents see tools exposed through `dcc-mcp-core`'s progressive discovery —
`tools/list` stays small because the gateway hides detail-level tools behind
`load_skill`. For AuroraView the shipped skills are:

| Skill                     | Tools (visible by default / after load_skill)                             |
|---------------------------|---------------------------------------------------------------------------|
| `auroraview-diagnostics`  | `list_windows`, `cdp_health`, `dump_console` (implicit-invocation on)     |
| `auroraview-devtools`     | `evaluate_js`, `reload`, `capture_screenshot` (explicit `load_skill`)     |

See [Epic #364](https://github.com/try-auroraview/auroraview/issues/364) for the
rollout status — the Rust adapter crate (`crates/auroraview-mcp`) and the
skills listed above are tracked under issues #365–#368.

To expose custom Python methods to agents, decorate them and bind via
`auroraview.api`:

```python
from auroraview import create_webview, api

class ToolAPI:
    def rename_selected(self, prefix: str = "av_") -> dict:
        ...
    def export_scene(self, path: str) -> dict:
        ...

webview = create_webview(parent=parent, url="http://tool")
api.bind(webview, ToolAPI())
# Now agents can call: mcp.call_api("rename_selected", {"prefix": "hero_"})
```

## One-shot migration checklist

Use this checklist when applying the skill to a repo. Tick every item.

- [ ] Grep for `QWebEngineView` / `QWebEnginePage` / `QWebChannel` — zero hits
- [ ] Grep for `PySide*-WebEngine` / `PyQtWebEngine` in deps — zero hits
- [ ] `from auroraview import create_webview` replaces WebEngine imports
- [ ] `@webview.on(...)` / `webview.emit(...)` replaces `QWebChannel` slots
- [ ] JS side uses `@auroraview/sdk` instead of `qwebchannel.js`
- [ ] Installed `dcc-mcp-core` + ran `auroraview-cli skills install`
- [ ] Verified with the agent: calling `list_windows` from
      `auroraview-diagnostics` returns at least the migrated app's window
- [ ] All DCC entry points use `create_webview(parent=...)` (never `QWebEngineView`)
- [ ] Sample/smoke test: agent `load_skill("auroraview-devtools")` then
      `capture_screenshot` returns a PNG
- [ ] README migration note added

## References (read these on demand)

- `python/auroraview/api.py` — unified `create_webview()` contract
- `python/auroraview/__init__.py` — full public API surface
- `python/auroraview/integration/qt/` — Qt embedding internals
- `examples/qt_browser.py` — canonical BEFORE example (pure Qt WebEngine)
- `examples/maya_qt_echo_demo.py` — canonical AFTER example (Qt host + AuroraView + API bridge)
- `packages/auroraview-sdk/` — JS-side bridge (`@auroraview/sdk`)
- `crates/auroraview-mcp/` — Rust adapter crate that plugs AuroraView into
  `dcc-mcp-core`'s gateway (tracks Epic #364; part of the new MCP story)
- [`dcc-mcp-core` upstream](https://github.com/loonghao/dcc-mcp-core) — gateway,
  skill runtime, and progressive tool discovery; MCP tools ship as `SKILL.md`
  packages delivered via `auroraview-cli skills install`

## Troubleshooting

| Symptom                                                        | Likely cause                                             | Fix                                                                      |
|----------------------------------------------------------------|----------------------------------------------------------|--------------------------------------------------------------------------|
| `RuntimeError: No Qt binding found`                            | `qtpy` can't resolve a binding                           | Install `PySide6` (or pass `parent=None` for standalone)                 |
| Window shows but DCC freezes                                   | Using `WebView` directly in a Qt host                    | Switch to `create_webview(parent=qwidget)` which picks `QtWebView`       |
| `discover_instances` returns empty list                        | WebView was started with `debug=False`                   | Leave `debug=True` (default) so the CDP port opens                       |
| JS `av.call()` hangs                                           | Python handler raised without returning JSON-serializable| Return a plain `dict` / list / str                                       |
| MCP `click(selector=...)` fails                                | Page not selected                                        | Call `select_page(url_pattern=...)` first                                |
