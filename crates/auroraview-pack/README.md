# AuroraView Pack

Zero-dependency application packaging for WebView-based desktop applications.

## Features

### 🚀 Packaging Modes

1. **URL Mode**: Wrap any website into a desktop app
   ```bash
   auroraview pack --url https://example.com --output my-app
   ```

2. **Frontend Mode**: Bundle local HTML/CSS/JS
   ```bash
   auroraview pack --frontend ./dist --output my-app
   ```

3. **FullStack Mode**: Bundle frontend + backend (Python/Node/Go/Rust)
   ```bash
   auroraview pack --config auroraview.pack.toml
   ```

### 🎯 Key Benefits

- **Zero Build Tools**: No Rust, Cargo, or compilers needed
- **Self-Replicating**: Uses overlay data approach
- **Python Protection**: Optional bytecode encryption and py2pyd compilation
- **Cross-Platform**: Windows, macOS, Linux support
- **Manifest-Driven**: Declarative configuration via TOML

## Design Philosophy

Unlike traditional packagers that generate source and require compilation, AuroraView Pack uses a **self-replicating approach**:

1. The `auroraview` CLI is itself a fully functional WebView shell
2. During `pack`, it copies itself and appends configuration + assets as overlay data
3. On startup, the packed exe detects the overlay and runs as a standalone app

**No build tools required!**

## Quick Start

### Installation

```bash
cargo add auroraview-pack
```

Or in `Cargo.toml`:

```toml
[dependencies]
auroraview-pack = "0.1"

# Enable Python code protection
auroraview-pack = { version = "0.1", features = ["code-protection"] }
```

### Basic Usage (Rust API)

```rust
use auroraview_pack::{Packer, PackConfig, PackMode};

// URL Mode
let config = PackConfig {
    mode: PackMode::Url {
        url: "https://example.com".to_string(),
    },
    output: "./my-app".into(),
    title: Some("My App".to_string()),
    ..Default::default()
};

let packer = Packer::new(config)?;
packer.pack()?;
```

### Manifest File (auroraview.pack.toml)

```toml
[package]
name = "my-app"
version = "1.0.0"
title = "My Application"
description = "A beautiful desktop app"
authors = ["Your Name <you@example.com>"]

[window]
width = 1200
height = 800
resizable = true
fullscreen = false
decorations = true

# URL Mode
[url]
url = "https://example.com"

# Or Frontend Mode
[frontend]
path = "./dist"
index = "index.html"

# Or FullStack Mode
[backend]
type = "python"
entry = "main.py"
requirements = "requirements.txt"

[frontend]
path = "./frontend/dist"

# Python Protection (optional)
[protection]
enabled = true
mode = "bytecode"  # or "py2pyd"
exclusions = ["test_*", "*/__pycache__/*"]
```

## Packaging Modes

### 1. URL Mode

Wrap any website as a desktop app:

```rust
use auroraview_pack::{PackConfig, PackMode};

let config = PackConfig {
    mode: PackMode::Url {
        url: "https://app.example.com".to_string(),
    },
    output: "./MyApp".into(),
    title: Some("My Web App".to_string()),
    ..Default::default()
};
```

### 2. Frontend Mode

Bundle local static files:

```rust
use auroraview_pack::{PackConfig, PackMode};

let config = PackConfig {
    mode: PackMode::Frontend {
        path: "./dist".into(),
        index: "index.html".to_string(),
    },
    output: "./MyApp".into(),
    ..Default::default()
};
```

### 3. FullStack Mode

Bundle frontend + backend server:

```rust
use auroraview_pack::{PackConfig, PackMode, BackendType};

let config = PackConfig {
    mode: PackMode::FullStack {
        frontend: FrontendConfig {
            path: "./frontend/dist".into(),
            index: "index.html".to_string(),
        },
        backend: BackendConfig {
            backend_type: BackendType::Python,
            entry: "main.py".to_string(),
            requirements: Some("requirements.txt".to_string()),
        },
    },
    output: "./MyApp".into(),
    ..Default::default()
};
```

## Python Protection

AuroraView Pack integrates with [aurora-protect](https://github.com/loonghao/aurora-protect) for Python code protection:

### Enable Protection Feature

```toml
[dependencies]
auroraview-pack = { version = "0.1", features = ["code-protection"] }
```

### Configure Protection

```rust
use auroraview_pack::{PackConfig, ProtectionConfig, ProtectionMode};

let config = PackConfig {
    // ... other fields
    protection: Some(ProtectionConfig {
        enabled: true,
        mode: ProtectionMode::Bytecode,  // or ProtectionMode::Py2Pyd
        exclusions: vec!["test_*".to_string()],
        dcc: None,  // or Some("maya2025".to_string())
    }),
    ..Default::default()
};
```

### Protection Modes

- **Bytecode**: Fast encryption using ECC + AES-256-GCM
- **Py2Pyd**: Compile to native .pyd/.so using Cython

## Overlay Format

AuroraView Pack uses a custom overlay format:

```text
┌─────────────────────────────────────┐
│     Original auroraview.exe         │
│     (WebView shell)                 │
├─────────────────────────────────────┤
│     Magic Header: "AVPK"            │  ← Overlay starts here
├─────────────────────────────────────┤
│     Config (TOML)                   │
├─────────────────────────────────────┤
│     Assets (Zstd compressed)        │
│     - Frontend files                │
│     - Backend files                 │
│     - Icon/resources                │
├─────────────────────────────────────┤
│     Footer: Offset + Magic          │
└─────────────────────────────────────┘
```

On startup, the exe:
1. Detects `AVPK` magic header
2. Reads config and extracts assets to temp
3. Launches WebView with extracted files

## Configuration Reference

### PackConfig

```rust
pub struct PackConfig {
    /// Packaging mode (URL/Frontend/FullStack)
    pub mode: PackMode,
    
    /// Output path (directory or exe name)
    pub output: PathBuf,
    
    /// Application title
    pub title: Option<String>,
    
    /// Window configuration
    pub window: WindowConfig,
    
    /// Python protection (requires "code-protection" feature)
    pub protection: Option<ProtectionConfig>,
    
    /// Custom icon (.ico/.png)
    pub icon: Option<PathBuf>,
}
```

### WindowConfig

```rust
pub struct WindowConfig {
    pub width: u32,
    pub height: u32,
    pub resizable: bool,
    pub fullscreen: bool,
    pub decorations: bool,
}
```

### ProtectionConfig

```rust
pub struct ProtectionConfig {
    /// Enable protection
    pub enabled: bool,
    
    /// Protection mode
    pub mode: ProtectionMode,
    
    /// File exclusion patterns (glob)
    pub exclusions: Vec<String>,
    
    /// DCC app for py2pyd (e.g., "maya2025")
    pub dcc: Option<String>,
}
```

## Examples

See [examples/](examples/) directory:

- `pack_url.rs`: Wrap a website
- `pack_frontend.rs`: Bundle static site
- `pack_fullstack.rs`: Bundle frontend + Python backend
- `pack_with_protection.rs`: Enable Python protection

## Performance

| Operation | Speed |
|-----------|-------|
| Copy base exe | <100ms |
| Compress assets | ~50 MB/s |
| Write overlay | ~100 MB/s |
| Total (small app) | <1s |
| Total (large app) | ~5s |

## Platform Support

- **Windows**: ✅ Full support (WebView2)
- **macOS**: ✅ Full support (WKWebView)
- **Linux**: ✅ Full support (WebKitGTK)

## License

MIT License - see [LICENSE](LICENSE) for details

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Links

- **Repository**: https://github.com/loonghao/auroraview-pack
- **Documentation**: https://docs.rs/auroraview-pack
- **Crates.io**: https://crates.io/crates/auroraview-pack
- **Issues**: https://github.com/loonghao/auroraview-pack/issues

## Related Projects

- [aurora-protect](https://github.com/loonghao/aurora-protect): Python code protection toolkit
- [AuroraView](https://github.com/try-auroraview/auroraview): WebView framework for DCC applications
