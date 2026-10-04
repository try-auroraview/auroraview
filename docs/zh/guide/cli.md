# CLI 参考

AuroraView 提供两个命令行界面：

1. **`auroraview`** (Python) - 通过 pip 安装，用于快速 WebView 预览
2. **`auroraview-cli`** (Rust) - 独立二进制文件，用于打包和高级功能

## 快速开始

### Python CLI (通过 pip)

```bash
pip install auroraview
# 或
uv pip install auroraview
```

```bash
# 加载 URL
auroraview --url https://example.com

# 加载本地 HTML 文件
auroraview --html /path/to/file.html

# 自定义窗口配置
auroraview --url https://example.com --title "我的应用" --width 1024 --height 768
```

### Rust CLI (用于打包)

从 [GitHub Releases](https://github.com/try-auroraview/auroraview/releases) 下载或从源码构建：

```bash
# 从源码构建
cargo build -p auroraview-cli --release
# 二进制文件: target/release/auroraview-cli (Windows 上是 auroraview-cli.exe)
```

```bash
# 打包基于 URL 的应用
auroraview-cli pack --url https://example.com --output myapp

# 打包前端项目 (React, Vue 等)
auroraview-cli pack --frontend ./dist --output myapp

# 打包全栈应用 (前端 + Python 后端)
auroraview-cli pack --config auroraview.pack.toml
```

## CLI 对比

| 功能 | `auroraview` (Python) | `auroraview-cli` (Rust) |
|------|----------------------|-------------------------|
| 安装方式 | `pip install auroraview` | GitHub Releases 或 `cargo build` |
| URL/HTML 预览 | ✅ | ✅ |
| 应用打包 | ❌ | ✅ |
| 全栈模式 (Python 后端) | ❌ | ✅ |
| 嵌入 Python 运行时 | ❌ | ✅ |
| 无需 Python | ❌ | ✅ |

## Python CLI 选项

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `-u, --url <URL>` | 在 WebView 中加载的 URL | - |
| `-f, --html <FILE>` | 加载的本地 HTML 文件 | - |
| `--assets-root <DIR>` | 本地 HTML 文件的资源根目录 | HTML 文件所在目录 |
| `-t, --title <TITLE>` | 窗口标题 | "AuroraView" |
| `-w, --width <WIDTH>` | 窗口宽度（像素，设为 0 则最大化） | 1024 |
| `-H, --height <HEIGHT>` | 窗口高度（像素，设为 0 则最大化） | 768 |
| `-d, --debug` | 启用调试日志（开发者工具） | false |
| `--allow-new-window` | 允许打开新窗口（如 window.open） | false |
| `--allow-file-protocol` | 启用 file:// 协议支持 | false |
| `--always-on-top` | 保持窗口置顶 | false |
| `-h, --help` | 打印帮助信息 | - |

## Rust CLI 命令

### 预览

```bash
auroraview-cli --url https://example.com
auroraview-cli --html index.html
```

### 打包

```bash
# URL 模式 - 为特定 URL 创建独立浏览器
auroraview-cli pack --url https://example.com --output myapp

# 前端模式 - 打包静态资源
auroraview-cli pack --frontend ./dist --output myapp

# 全栈模式 - 打包前端 + Python 后端
auroraview-cli pack --config auroraview.pack.toml
```

## 打包应用 CLI（Headless 模式）

除了上面两个 CLI，**打包后的应用**本身就是第三个命令行界面。打包 exe 默认是 GUI 应用——双击即打开窗口——但它**同时**支持在终端里直接运行已注册的 Python 命令，无需打开窗口：

```bash
my-app.exe                          # 打开 GUI 窗口（行为不变）
my-app.exe -h                       # 列出已开启 CLI 的命令
my-app.exe list                     # 列出命令（--json 输出机器可读格式）
my-app.exe run export --path ./out  # 执行单个命令，打印结果后退出
my-app.exe -V                       # 打印版本
```

只有当**首个参数**是保留动词（`run`、`list`）或保留标志（`-h`/`--help`、`-V`/`--version`）时才进入 CLI 路径——裸文件路径（文件关联、拖拽）一律打开 GUI。

暴露是逐命令显式开启的，通过 `@webview.command(cli=...)`：

```python
@webview.command(name="export", help="导出工程", cli=True)
def export(path: str, dpi: int = 300) -> dict:
    return {"written": path, "dpi": dpi}
```

退出码：`0` 成功，`1` 命令抛异常，`2` 命令未找到或参数错误。Windows 上请在终端里调用生成的 `my-app.cmd` 包装脚本，输出与退出码才会正确传递。完整参考（别名、传参、`.cmd` 包装脚本、命令清单如何在打包期采集）见
[应用打包指南](/zh/guide/packing)的「命令行模式」一节。

## 示例

### 快速 Web 预览 (Python)

```bash
# 预览网站
auroraview --url https://github.com

# 自定义大小预览
auroraview --url https://github.com --width 1920 --height 1080

# 窗口置顶预览
auroraview --url https://github.com --always-on-top

# 启用开发者工具调试
auroraview --url https://github.com --debug
```

### 本地开发 (Python)

```bash
# 预览本地 HTML 文件
auroraview --html index.html

# 自定义标题预览
auroraview --html dist/index.html --title "我的应用预览"

# 指定资源根目录
auroraview --html dist/index.html --assets-root ./assets

# 启用 file:// 协议加载本地资源
auroraview --html index.html --allow-file-protocol
```

### 使用 uvx（无需安装）

```bash
# 直接运行无需安装
uvx auroraview --url https://example.com

# 加载本地文件
uvx auroraview --html test.html
```

### 应用打包 (Rust CLI)

```bash
# 打包简单 URL 应用
auroraview-cli pack --url https://myapp.com --output myapp

# 打包 React/Vue 前端
auroraview-cli pack --frontend ./build --output myapp --title "我的应用"

# 打包带 Python 后端的全栈应用
auroraview-cli pack --config auroraview.pack.toml
```

## 平台支持

CLI 支持以下平台：

- **Windows**: 使用 WebView2（内置于 Windows 10/11）
- **macOS**: 使用 WKWebView（内置于 macOS）
- **Linux**: 使用 WebKitGTK（需要安装）

### Linux 依赖

在 Linux 上，需要安装 WebKitGTK：

```bash
# Debian/Ubuntu
sudo apt install libwebkit2gtk-4.1-dev

# Fedora/CentOS
sudo dnf install webkit2gtk3-devel

# Arch Linux
sudo pacman -S webkit2gtk
```

## 故障排除

### Windows 上 Python 3.7 使用 uvx

由于 uv/uvx 的[已知限制](https://github.com/astral-sh/uv/issues/10165)，`auroraview` 命令在 Windows 上的 Python 3.7 不工作。

**解决方法**: 使用 `python -m auroraview` 代替：

```bash
# 替代: uvx --python 3.7 auroraview --url https://example.com
# 使用:
uvx --python 3.7 --from auroraview python -m auroraview --url https://example.com

# 或使用 pip 安装的包:
python -m auroraview --url https://example.com
```

### 找不到二进制文件

如果出现 "auroraview: command not found"：

```bash
pip install --force-reinstall auroraview
```

### WebView2 未找到 (Windows)

在 Windows 上需要 WebView2。它预装在 Windows 10/11 上，如果遇到问题：

1. 下载并安装 [WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)

### 权限被拒绝 (Linux/macOS)

如果出现权限错误：

```bash
chmod +x $(which auroraview)
```
