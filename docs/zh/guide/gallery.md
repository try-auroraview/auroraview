# Gallery

AuroraView Gallery 是一个综合展示应用，演示了 AuroraView 框架的所有功能和能力。它既是参考实现，也是开发者的测试平台。

## 下载

获取最新 Gallery 版本：

| 平台 | 下载 |
|------|------|
| Windows | [auroraview-gallery-windows.zip](https://github.com/try-auroraview/auroraview/releases/latest) |

> **注意**：Gallery 是使用 `auroraview-cli` 打包的独立应用程序。它包含所有依赖项，不需要安装 Python。

## 功能概览

Gallery 展示了以下 AuroraView 能力：

### 示例浏览器

按类别浏览和运行示例应用：

- **Getting Started**：快速入门示例和基本用法模式
- **API Patterns**：使用 AuroraView API 的不同方式
- **Window Features**：窗口特效和高级功能
- **DCC Integration**：DCC 特定示例

![Gallery 主界面](/gallery/main.png)

### 类别视图

#### Getting Started

![Getting Started](/gallery/getting_started.png)

#### API Patterns

![API Patterns](/gallery/api_patterns.png)

#### Window Features

![Window Features](/gallery/window_features.png)

### 设置

配置 Gallery 行为和偏好：

![设置](/gallery/settings.png)

### 实时代码查看器

查看和学习任何示例的源代码：

- 语法高亮
- 复制到剪贴板
- 在外部编辑器中打开

### 进程控制台

实时监控运行中的示例：

- stdout/stderr 捕获
- 进程管理（终止、重启）
- 多进程跟踪

### Chrome 扩展支持

在 AuroraView 中测试和开发 Chrome 扩展：

- 扩展安装
- 侧边栏支持
- Chrome API 兼容性测试

### 窗口特效演示

窗口特效的交互式演示：

- 点击穿透模式与交互区域
- 背景模糊（Blur、Acrylic、Mica）
- 实时配置

## 从源码运行

如果你想从源码运行 Gallery：

```bash
# 克隆仓库
git clone https://github.com/try-auroraview/auroraview.git
cd auroraview

# 安装依赖
pip install -e .
cd gallery
npm install

# 构建前端
npm run build

# 运行 Gallery
cd ..
python gallery/main.py
```

## Gallery 架构

Gallery 使用以下技术构建：

- **前端**：React + TypeScript + Tailwind CSS
- **后端**：AuroraView Python API
- **打包**：auroraview-cli pack 系统

```
gallery/
├── src/                 # React 前端
│   ├── components/      # UI 组件
│   ├── hooks/           # 自定义 React hooks
│   └── data/            # 示例定义
├── backend/             # Python 后端
│   ├── samples.py       # 示例管理
│   ├── extension_api.py # 扩展支持
│   └── process_api.py   # 进程管理
├── main.py              # 入口点
└── auroraview.pack.toml # Pack 配置
```

## 示例类别

### 基础示例

| 示例 | 描述 |
|------|------|
| Hello World | 最小 WebView 示例 |
| Load URL | 加载外部网站 |
| Load HTML | 加载内联 HTML 内容 |
| Transparent Window | 透明背景演示 |

### API 示例

| 示例 | 描述 |
|------|------|
| JS to Python | 从 JavaScript 调用 Python |
| Python to JS | 从 Python 执行 JavaScript |
| Event System | 双向事件通信 |
| Async Calls | 异步 API 模式 |

### UI 示例

| 示例 | 描述 |
|------|------|
| Custom Titlebar | 无边框窗口与自定义标题栏 |
| Context Menu | 自定义右键菜单 |
| System Tray | 系统托盘集成 |
| Multi-Window | 多窗口管理 |

### 高级示例

| 示例 | 描述 |
|------|------|
| File Dialog | 原生文件对话框 |
| Clipboard | 剪贴板操作 |
| Window Effects | 点击穿透和毛玻璃效果 |
| Child Windows | 父子窗口关系 |

## 贡献示例

要向 Gallery 添加新示例：

1. 在 `examples/` 目录中创建示例
2. 在 `gallery/backend/samples.py` 中添加示例元数据
3. 使用 `python gallery/main.py` 测试
4. 提交 pull request

示例元数据格式：

```python
{
    "id": "my-sample",
    "name": "My Sample",
    "description": "此示例演示的功能描述",
    "category": "basic",  # basic, api, ui, dcc, advanced
    "tags": ["tag1", "tag2"],
    "file": "examples/my_sample.py",
}
```

## 键盘快捷键

| 快捷键 | 操作 |
|--------|------|
| `Ctrl+R` | 重新加载当前页面 |
| `Ctrl+Shift+I` | 打开开发者工具 |
| `Ctrl+Q` | 退出 Gallery |
| `Escape` | 关闭模态框/面板 |

## 故障排除

### Gallery 无法启动

1. 确保已安装 WebView2 Runtime（Windows）
2. 检查端口 5173 是否可用（开发模式）
3. 尝试使用 `--debug` 标志运行

### 示例运行失败

1. 检查 Python 路径配置
2. 验证示例文件存在
3. 查看进程控制台中的错误

### 扩展无法加载

1. 确保扩展 manifest 有效
2. 检查扩展权限
3. 安装扩展后重启 Gallery
