# 安装

## 系统要求

- **Python**: 3.7 或更高版本
- **操作系统**: Windows、macOS 或 Linux

## 基本安装

### Windows 和 macOS

```bash
pip install auroraview
```

### 带 Qt 支持

对于基于 Qt 的 DCC 应用程序（Maya、Houdini、Nuke、3ds Max）：

```bash
pip install auroraview[qt]
```

这会安装 QtPy 作为中间层来处理 DCC 应用程序中不同的 Qt 版本。

### Linux

Linux 需要 webkit2gtk 系统依赖：

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

## 使用 uvx（无需安装）

你可以使用 `uvx` 运行 AuroraView 而无需安装：

```bash
uvx auroraview --url https://example.com
```

## 开发安装

从源码构建：

```bash
# 克隆仓库
git clone https://github.com/try-auroraview/auroraview.git
cd auroraview

# 安装 Rust（如果尚未安装）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 构建并安装
pip install -e .
```

## 验证安装

```python
import auroraview
print(auroraview.__version__)
```

或使用 CLI：

```bash
auroraview --version
```
