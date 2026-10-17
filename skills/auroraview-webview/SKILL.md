---
name: auroraview-webview
description: >-
  Drive a live AuroraView WebView from DCC-MCP: evaluate JavaScript, capture
  screenshots, and load URLs or HTML into an embedded browser panel.
license: MIT
compatibility: "dcc-mcp-core 0.20+, AuroraView 0.5+"
metadata:
  dcc-mcp:
    version: "0.1.0"
    dcc: auroraview
    layer: host
    tools: tools.yaml
    search-hint: >-
      auroraview, webview, browser panel, eval js, javascript, screenshot,
      load url, load html, webview2, dcc panel
    search-aliases:
      - aurora view
      - web view
      - embedded browser
    tags: "auroraview, webview, javascript, screenshot, dcc-panel"
---

# AuroraView WebView

Control a running AuroraView instance from the DCC-MCP control plane.

AuroraView is a lightweight WebView host embedded in DCC applications
(Maya, Houdini, Blender, 3ds Max, Nuke, Unreal Engine). It has **no scene
graph, timeline, selection, undo stack, or render farm** of its own, so this
skill scopes itself to what a WebView host genuinely does: run JavaScript,
capture what is on screen, and load content.

## When to use this skill

- Inspect or mutate the DOM of a tool panel built with AuroraView.
- Capture a screenshot of a running AuroraView panel for review or docs.
- Navigate a panel to a URL, or inject HTML for a quick preview.
- Drive an AuroraView panel inside Maya/Houdini/Blender through a single,
  uniform tool set.

## Tools

| Tool | Purpose |
|---|---|
| `list_views` | List live view IDs and generations without touching the WebView. |
| `eval_js` | Evaluate JavaScript in the panel and return the value. |
| `screenshot` | Capture the page as PNG via `window.auroraview.screenshot`. |
| `load_url` | Load a URL (`http://`, `https://`, `file://`). |
| `load_html` | Load raw HTML content. |

## Usage

```bash
# Read the panel title
dcc-mcp-cli call --tool eval_js --params '{"script": "document.title"}'

# Capture the current page
dcc-mcp-cli call --tool screenshot --params '{"format": "png"}'
```

With multiple panels in one process, first call `list_views`, then pass the
selected `view_id` and `generation` to every panel operation. Omitting both is
supported only when exactly one live view exists; it never selects the most
recently opened panel. An old generation fails after its registration closes,
even if a replacement reuses the same view ID.

```bash
dcc-mcp-cli call --tool list_views --params '{}'
dcc-mcp-cli call --tool eval_js --params '{"view_id":"<from list_views>","generation":"<from list_views>","script":"document.title"}'
```

Routing identities are local to the selected host service/process. They are
not authentication tokens. Discover the intended DCC service first; these
arguments do not select a different process or start another server.

## Notes

- `eval_js` waits for the JavaScript result and honours a timeout; it is not
  fire-and-forget.
- `screenshot` relies on the `window.auroraview.screenshot` helper that
  AuroraView injects into every page. Pages that load a strict Content
  Security Policy may block the html2canvas CDN dependency.
- AuroraView runs a Qt event loop. All invocations are dispatched on the host
  thread that owns the WebView.
