# JavaScript Asset Management

All JavaScript injected into the WebView is managed centrally rather than
embedded as hardcoded strings in Rust source. Preserved here when the
`.codebuddy/` agent configuration directory was removed; the convention below is
still normative.

## Rationale

Injected JavaScript that is scattered across `event_loop.rs`,
`backend/native.rs`, `backend/mod.rs`, `webview_inner.rs` and `standalone.rs` is
hard to find, review and update. Centralising it gives type-safe access, makes
the scripts independently testable, keeps changes visible in version control,
and guarantees every event emit and URL load uses the same template.

## Layout

JavaScript lives in `crates/auroraview-core/src/assets/js/`:

```
crates/auroraview-core/src/assets/js/
├── core/       # core scripts (event_bridge, command_bridge, channel_bridge, ...)
├── features/   # conditionally included based on WebViewConfig
├── plugins/    # plugin scripts (clipboard, dialog, ...)
└── runtime/    # runtime templates (emit_event.js, load_url.js)
```

The crate embeds these at compile time with `rust_embed` and re-exports them
through `auroraview_core::assets`. `src/webview/js_assets.rs` wraps that with the
WebView-facing API.

## Usage

Static assets:

```rust
use crate::webview::js_assets;

let script = js_assets::build_init_script(&config);
```

Runtime templates — escape the payload before interpolating it into the template:

```rust
let json_str = data.to_string();
let escaped_json = json_str.replace('\\', "\\\\").replace('\'', "\\'");
let script = js_assets::build_emit_event_script("my_event", &escaped_json);
let script = js_assets::build_load_url_script("https://example.com");
```

When the `templates` feature is enabled, templates are rendered with Askama for
type-safe generation; otherwise the module falls back to string replacement.
