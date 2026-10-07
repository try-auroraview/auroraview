# Blender 集成

新的 Blender 集成统一在独立仓库
[auroraview-blender](https://github.com/try-auroraview/auroraview-blender)
维护。插件负责 Blender 面板、操作器、主线程调度和宿主清理；AuroraView Core
负责 WebView 引擎、JavaScript 桥、RPC 消息和通用窗口生命周期。

## 选择工具界面

| 界面 | 显示内容 | Core 依赖 |
| --- | --- | --- |
| Blender 原生侧栏面板 | Blender 属性、操作器和布局控件 | 无 |
| 实验性浮动 WebView | 独立 Windows 工具窗口中的 HTML/CSS/JavaScript | 明确兼容的 Core 构建 |
| Blender 编辑器区域内的 HTML | 尚未实现 | 需要独立的渲染与输入集成 |

原生工具面板可以使用 Blender 的侧栏布局，但不显示 HTML。给浮动窗口指定 HWND
父窗口不会使它成为 Blender 面板，`Panel.draw` 也不提供浏览器表面。
在编辑器区域中显示 HTML 需要离屏帧、输入契约和 Blender GPU 集成；当前插件尚未实现。

## 原生插件工具

扩展安装方式和原生面板 API 以
[Blender 仓库](https://github.com/try-auroraview/auroraview-blender)
为准。扩展清单面向 Blender 4.2 及以上版本；安装包包含适配器和 Blender 清单，
不包含 Core 或 WebView 引擎。目前是开发源代码，尚未上架 Blender Extensions。

消费者在 Blender 主线程中，通过已启用的适配器模块注册工具。扩展使用 Blender
按仓库生成的 `bl_ext` 命名空间；将该模块传给集成代码，不要创建顶层模块别名。

```python
def register_tools(adapter):
    def draw(layout, context):
        layout.label(text="Selected: %d" % len(context.selected_objects))
        if context.active_object is not None:
            layout.prop(context.active_object, "location")

    adapter.register_panel("EXAMPLE_PT_transform", "Transform", draw)


def unregister_tools(adapter):
    adapter.unregister_panel("EXAMPLE_PT_transform")
```

绘制回调应保持简短，使用当前传入的上下文。通过 Blender 属性编辑数据，通过操作器
执行动作。消费者插件停用时移除自己的面板；适配器也会追踪已注册面板并负责清理。

## 可选 HTML 工具

插件的
[消费者指南](https://github.com/try-auroraview/auroraview-blender/blob/main/docs/consumer-tools.md)
通过 `BlenderSession.open(..., configure=configure)`，在显示 WebView 之前绑定
公开 Core API。会话通过 `set_call_dispatcher` 和 `set_event_dispatcher`，
将调用与事件通知送入同一个有界主线程队列；JavaScript Promise 和 RPC 协议仍由 Core 管理。
通过 `on`/`register_callback` 注册的通知立即返回，忽略回调返回值；此模式明确拒绝
同步 `closing` 否决回调。原始 signal 连接直接执行，不获得宿主调度保证。

关闭、断开连接和替换调度器会使排队通知失效，包括 `closed`；清理由插件和会话生命周期负责。

该路径需要
[Core PR #497](https://github.com/try-auroraview/auroraview/pull/497)
所跟踪的拥有线程 RPC 与生命周期契约。具体源代码构建要求请查看插件的
[Core 兼容性契约](https://github.com/try-auroraview/auroraview-blender/blob/main/docs/core-compatibility.md)。
本指南不声明任何已发布 Core 版本兼容；安装任意已发布 wheel 不能满足该契约。

Windows 浮动路径仍属实验性功能，尚需真实 WebView 验收。该路径拒绝 Linux/macOS
后台启动；安装 Blender 插件也不会启用独立的 GTK 实验代码。

## 线程与生命周期归属

- 宿主类和计时器注册、会话启动以及 `bpy` 访问必须在 Blender 主线程执行。
  工作线程只能将任务加入队列，不能调用宿主 API
- 不要阻塞 Blender 主线程等待依赖该线程的任务。宿主回调应限制耗时；
  JavaScript 超时不会撤销已经发生的宿主修改
- 在 WebView 异步启动之前绑定宿主命令，使用插件的 `configure` 钩子，
  不要从其他线程注册原生回调
- 停用、文件加载和模块重载时，应丢弃过期队列任务、移除所属宿主注册，并请求关闭所属视图。
  关闭请求与原生清理完成是不同状态；通过 Core 的 `wait(0)` 非阻塞轮询

Blender 的
[Python 线程说明](https://docs.blender.org/api/main/info_gotchas_threading.html)
限制了持续运行的 Python 线程。将宿主调用调度到主线程，不代表长期存活的 WebView
回调线程已经安全。原生侧栏工具无需 WebView 工作线程。

## 兼容性与验证

Core 原有的 `BlenderDispatcherBackend`、公开导入路径和自动宿主检测继续保留，
作为旧代码的兼容路径。它们不提供原生面板 API；检测到 Blender 也不能证明原生渲染
和清理安全。本次文档迁移不改变自动发现的优先级。

无界面导入测试、真实插件注册和调度测试只能证明各自覆盖的行为。
可见 HTML 渲染、JS/Python RPC、多窗口、关闭后重建、卸载和退出，需要针对明确的
Blender、操作系统和 Core 组合单独测试。当前证据与待完成项请查看插件的
[验证记录](https://github.com/try-auroraview/auroraview-blender/blob/main/docs/validation.md)。
