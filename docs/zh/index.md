---
layout: home

hero:
  name: AuroraView
  text: DCC 软件的轻量级 WebView 框架
  tagline: 为 Maya、Houdini、Blender 等软件构建现代 Web UI，具有 Rust 级别的性能
  image:
    src: /logo.png
    alt: AuroraView
  actions:
    - theme: brand
      text: 快速开始
      link: /zh/guide/getting-started
    - theme: alt
      text: GitHub
      link: https://github.com/try-auroraview/auroraview

features:
  - icon: 🚀
    title: 轻量级
    details: 约 5MB 包大小，对比 Electron 的约 120MB。原生 Rust 性能，内存占用极低。
  - icon: 🎨
    title: DCC 优先设计
    details: 专为 Maya、Houdini、3ds Max、Blender、Photoshop 和 Unreal Engine 集成而构建。
  - icon: 🔗
    title: 无缝集成
    details: 简洁的 Python API，支持 Qt 小部件，可创建可停靠面板和原生 DCC 集成。
  - icon: 🌐
    title: 现代 Web 技术栈
    details: 使用 React、Vue 或任何 Web 框架。完整的 Python ↔ JavaScript 双向通信。
  - icon: 🔒
    title: 安全可靠
    details: Rust 的内存安全保证。线程安全操作和自动生命周期管理。
  - icon: 📦
    title: 简易打包
    details: 将应用打包成单个可执行文件，内嵌 Python 运行时，支持离线分发。
---

## 为什么选择 AuroraView？

### 我们要解决的问题

游戏和影视特效开发者长期以来一直在为 DCC 软件构建现代化、用户友好的工具而苦恼。传统方法往往意味着：

- **过时的 UI 框架** - Qt Designer 或原生 DCC 控件，样式选项有限
- **陡峭的学习曲线** - 每个 DCC 都有自己的 UI 范式和 API
- **糟糕的用户体验** - 工具感觉与现代 Web 应用脱节
- **缓慢的迭代周期** - 重建和重新加载工具需要太长时间

### AI 驱动的开发时代

我们正处于一个激动人心的时代，**AI 可以快速生成高质量的前端代码**。现代 AI 助手擅长创建 React、Vue 和 Web 界面。AuroraView 将这种能力桥接到 DCC 软件：

- **AI 友好的架构** - 我们的 API 设计易于 AI 助手理解和生成
- **现代 Web 技术栈** - 使用 AI 擅长的相同技术（React、Vue、TypeScript、Tailwind）
- **快速原型开发** - 从想法到可用工具只需几分钟，而不是几天

### 超越传统工具

AuroraView 不仅仅是另一个 UI 框架。它实现了全新的工作流程：

| 能力 | 描述 |
|------|------|
| **浏览器扩展** | 构建与 DCC 软件通信的基于浏览器的工具 |
| **AI Agent 集成** | 通过 MCP 协议使 AI Agent 能够控制和自动化 DCC 应用程序 |
| **跨平台工具** | 相同的代码库可在 Maya、Houdini、Blender 和独立模式下运行 |
| **实时协作** | Web 技术支持实时协作功能 |

### 为现代开发者打造

无论你是构建流程工具的 TD、创建自定义工作流的艺术家，还是开发专有解决方案的工作室，AuroraView 都能让你：

- **利用 AI** 加速开发
- **使用熟悉的 Web 技术** 而不是学习 DCC 特定的 UI 框架
- **构建美观、响应式的 UI** 让艺术家真正喜欢使用
- **更快交付** 通过热重载开发和简易打包

## 快速开始

### 安装

```bash
# 基础安装
pip install auroraview

# 带 Qt 支持（用于 Maya、Houdini、Nuke）
pip install auroraview[qt]
```

### 桌面应用

```python
from auroraview import run_desktop

run_desktop(
    title="我的应用",
    url="http://localhost:3000"
)
```

### Maya 集成

```python
from auroraview import QtWebView
import maya.OpenMayaUI as omui

webview = QtWebView(
    parent=maya_main_window(),
    url="http://localhost:3000",
    width=800,
    height=600
)
webview.show()
```

## 支持的 DCC 软件

| 软件 | 状态 | 集成模式 |
|------|------|----------|
| Maya | ✅ 已支持 | Qt 模式 |
| Houdini | ✅ 已支持 | Qt 模式 |
| 3ds Max | ✅ 已支持 | Qt 模式 |
| Blender | ✅ 已支持 | 桌面 / 原生模式 |
| Photoshop | 🚧 计划中 | - |
| Unreal Engine | 🚧 计划中 | 原生模式 (HWND) |
