# Pack Architecture

Design notes for `crates/auroraview-pack` that are not covered by the
user-facing [Application Packing](../guide/packing.md) guide or the crate
README. Preserved here when the `.codebuddy/` agent configuration directory was
removed; the constraints below are still normative.

The `REPOSITORY` metadata in `Cargo.toml`, `pyproject.toml`,
`packages/auroraview-sdk/package.json` and the install scripts must all agree —
`vx just check-repository-links` enforces this.

## Builders

Platform-specific build logic is implemented through the `Builder` trait.

| Builder | ID | Targets |
|---------|-----|---------|
| `WinBuilder` | win | windows, win64, win32 |
| `MacBuilder` | mac | macos, darwin, osx |
| `LinuxBuilder` | linux | linux, ubuntu, debian |
| `IOSBuilder` | ios | ios, iphone, ipad |
| `AndroidBuilder` | android | android |
| `WebBuilder` | web | web, pwa, static |
| `WeChatBuilder` | wechat | wechat, weixin, wx |
| `AlipayBuilder` | alipay | alipay, ali |
| `ByteDanceBuilder` | bytedance | bytedance, douyin, tiktok |

### Builder capabilities

```rust
pub enum BuilderCapability {
    Standalone,    // standalone executable
    Installer,     // installer package
    Portable,      // portable build / ZIP
    CodeSign,      // code signing
    Notarize,      // notarization (macOS)
    PythonEmbed,   // embed a Python runtime
    NodeEmbed,     // embed a Node.js runtime
    Extensions,    // Chrome extension support
    DevTools,      // developer tooling support
    AppStore,      // app store distribution
    HotReload,     // hot reload
}
```

## Overlay format

A packed executable appends configuration and assets using an overlay:

```
[Original Executable]
[Overlay Header]
  - Magic: "AVPK" (4 bytes)
  - Version: u32 LE (4 bytes)
  - Config Length: u64 LE (8 bytes)
  - Assets Length: u64 LE (8 bytes)
[Config Data] (JSON, zstd compressed)
[Assets Data] (tar archive, zstd compressed)
[Footer]
  - Overlay Start Offset: u64 LE (8 bytes)
  - Magic: "AVPK" (4 bytes)
```

**Content hash**: BLAKE3 over every asset, used as the runtime cache key.
Identical content yields an identical hash and skips extraction; different
content gets a new cache directory. This lets multiple versions coexist.

## Python standalone runtime

A full Python runtime is embedded using
[python-build-standalone](https://github.com/indygreg/python-build-standalone).

| Platform | Distribution |
|------|--------|
| Windows x64 | `cpython-{version}+{release}-x86_64-pc-windows-msvc-install_only.tar.gz` |
| Linux x64 | `cpython-{version}+{release}-x86_64-unknown-linux-gnu-install_only.tar.gz` |
| macOS x64 | `cpython-{version}+{release}-x86_64-apple-darwin-install_only.tar.gz` |
| macOS ARM64 | `cpython-{version}+{release}-aarch64-apple-darwin-install_only.tar.gz` |

Workflow:

1. **Pack time**: download the prebuilt Python distribution.
2. **Embed**: compress it into the overlay.
3. **Runtime**: extract to a cache directory on first run, reuse afterwards.

## Pack hooks

Custom logic can be inserted across the packing lifecycle:

```
BeforePack → BeforeCollect → AfterCollect → BeforeOverlay →
BeforeTarget → [Target Build] → AfterTarget → AfterOverlay → AfterPack
```

Built-in plugins:

- `ExtensionBundlerPlugin`: bundles Chrome extensions.
- `LicenseBundlerPlugin`: embeds license validation.
