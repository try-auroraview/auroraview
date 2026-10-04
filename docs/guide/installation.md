# Installation

## Requirements

- **Python**: 3.7 or higher
- **Operating System**: Windows, macOS, or Linux

## Basic Installation

### Windows and macOS

```bash
pip install auroraview
```

### With Qt Support

For Qt-based DCC applications (Maya, Houdini, Nuke, 3ds Max):

```bash
pip install auroraview[qt]
```

This installs QtPy as a middleware layer to handle different Qt versions across DCC applications.

### Linux

Linux requires webkit2gtk system dependencies:

::: code-group

```bash [Debian/Ubuntu]
sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev
pip install auroraview
```

```bash [Fedora/CentOS]
sudo dnf install gtk3-devel webkit2gtk3-devel
pip install auroraview
```

```bash [Arch Linux]
sudo pacman -S webkit2gtk
pip install auroraview
```

:::

## Using uvx (No Installation)

You can run AuroraView without installing using `uvx`:

```bash
uvx auroraview --url https://example.com
```

## Development Installation

To build from source:

```bash
# Clone the repository
git clone https://github.com/try-auroraview/auroraview.git
cd auroraview

# Install Rust (if not already installed)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build and install
pip install -e .
```

## Verify Installation

```python
import auroraview
print(auroraview.__version__)
```

Or using CLI:

```bash
auroraview --version
```
