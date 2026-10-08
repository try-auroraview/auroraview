# RFC 0001: AuroraView MCP Server - Implementation Tracker

## 总体进度

| Phase | 状态 | 完成度 | 目标版本 | 预计时间 |
|-------|------|--------|----------|----------|
| Phase 1: Python SDK 核心 | 完成 | 100% | v0.3.0 | 2 周 |
| Phase 2: Gallery 集成 | 完成 | 100% | v0.3.1 | 1 周 |
| Phase 3: DCC 支持 | 完成 | 100% | v0.4.0 | 2 周 |
| Phase 4: Node.js SDK | 待开始 | 0% | v0.4.1 | 2 周 |
| Phase 5: Midscene 集成 | 待开始 | 0% | v0.5.0 | 2 周 |
| Phase 6: 高级功能 | 待开始 | 0% | v0.6.0 | 2 周 |

## 详细进度

### Phase 1: Python SDK 核心功能

> ⚠️ **此实现计划已被 [Epic #364](https://github.com/try-auroraview/auroraview/issues/364)
> supersede**。Python `auroraview-mcp` 包已删除，新实现走 Rust adapter crate +
> `dcc-mcp-core` gateway，详见 RFC 0001 顶部的说明。以下 checkbox 仅保留历史快照。

#### 项目结构搭建
- [x] 创建 `packages/auroraview-mcp/` 目录
- [x] 配置 `pyproject.toml`
- [x] 设置开发环境
- [x] 添加到 monorepo 工作区

#### 实例发现 (`discover_instances`)
- [x] 设计
- [x] 实现端口扫描
- [x] 实现 AuroraView 特征检测
- [x] 测试
- [x] 文档

#### 连接管理 (`connect`, `disconnect`)
- [x] 设计
- [x] 实现 CDP WebSocket 连接
- [x] 实现连接池
- [x] 测试
- [x] 文档

#### 页面操作 (`list_pages`, `select_page`, `get_page_info`)
- [x] 设计
- [x] 实现页面列表
- [x] 实现页面选择（过滤 about:blank）
- [x] 实现页面信息获取
- [x] 测试
- [x] 文档

#### 基本 API 调用 (`call_api`, `list_api_methods`)
- [x] 设计
- [x] 实现 JS 执行桥接
- [x] 实现异步调用支持
- [x] 测试
- [x] 文档

#### 截图 (`take_screenshot`)
- [x] 设计
- [x] 实现 CDP 截图
- [x] 支持元素截图
- [x] 支持全页面截图
- [x] 测试
- [x] 文档

### Phase 2: Gallery 集成

#### Gallery 工具
- [x] `run_gallery` - 启动 Gallery 应用
- [x] `stop_gallery` - 停止 Gallery
- [x] `get_gallery_status` - 获取 Gallery 状态
- [x] `get_samples` - 获取示例列表
- [x] `run_sample` - 运行示例
- [x] `stop_sample` - 停止示例
- [x] `get_sample_source` - 获取源码
- [x] `list_processes` - 列出进程
- [x] `stop_all_samples` - 停止所有示例
- [x] `get_project_info` - 获取项目信息

#### 资源提供者
- [x] `auroraview://instances`
- [x] `auroraview://page/{id}`
- [x] `auroraview://samples`
- [x] `auroraview://sample/{name}/source`
- [x] `auroraview://gallery`
- [x] `auroraview://project`
- [x] `auroraview://processes`

### Phase 3: DCC 支持

#### DCC 实例发现
- [x] `list_dcc_instances` - 发现 DCC 实例
- [x] DCC 类型检测（Maya、Blender、Houdini、Nuke、Unreal、3ds Max）
- [x] 页面标题/URL 检测
- [x] 测试

#### DCC 上下文
- [x] `get_dcc_context` - 获取 DCC 上下文
- [x] 场景信息
- [x] 选择状态
- [x] 当前帧
- [x] 测试

#### DCC 命令
- [x] `execute_dcc_command` - 执行 DCC 命令
- [x] 支持 args 和 kwargs 参数
- [x] 错误处理
- [x] 测试

#### 选择同步
- [x] `sync_selection` - 同步选择状态
- [x] `set_dcc_selection` - 设置 DCC 选择
- [x] 测试

#### 场景和时间线
- [x] `get_dcc_scene_info` - 获取场景信息
- [x] `get_dcc_timeline` - 获取时间线信息
- [x] `set_dcc_frame` - 设置当前帧
- [x] 测试

### Phase 4: Node.js SDK

#### 基础设施
- [ ] 创建 `packages/auroraview-mcp-node/` 目录
- [ ] 配置 `package.json` 和 `tsconfig.json`
- [ ] 设置构建流程

#### MCP Server
- [ ] 实现 TypeScript MCP Server
- [ ] CDP 连接管理
- [ ] 工具注册

#### 核心工具移植
- [ ] 发现工具
- [ ] 页面工具
- [ ] API 工具
- [ ] UI 工具

#### 类型定义
- [ ] 完整 TypeScript 类型
- [ ] 导出类型声明

### Phase 5: Midscene 集成

#### Midscene Agent
- [ ] `AuroraViewMidsceneAgent` 类
- [ ] 上下文增强
- [ ] 错误处理

#### AI 工具
- [ ] `ai_act` - 自然语言 UI 操作
- [ ] `ai_query` - 数据提取
- [ ] `ai_assert` - 断言
- [ ] `ai_wait_for` - 等待条件

#### DCC AI 工具
- [ ] `ai_dcc_action` - DCC 环境 AI 操作
- [ ] DCC 上下文注入

#### 提示模板
- [ ] AuroraView 通用模板
- [ ] Gallery 专用模板
- [ ] DCC 专用模板

### Phase 6: 高级功能

#### 调试工具
- [ ] `get_console_logs` - 控制台日志
- [ ] `get_network_requests` - 网络请求
- [ ] `get_backend_status` - 后端状态
- [ ] `reload_page` - 重载页面

#### UI 交互
- [ ] `get_snapshot` - 页面快照
- [ ] `click` - 点击元素
- [ ] `fill` - 填充输入
- [ ] `evaluate` - 执行 JS

#### 事件系统
- [ ] `emit_event` - 触发事件

#### 高级功能
- [ ] 多实例管理
- [ ] 性能监控工具
- [ ] SSE 传输支持
- [ ] 提示模板 (Prompts)

## 测试计划

### 单元测试
- [x] `test_discovery.py` - 实例发现测试
- [x] `test_connection.py` - 连接管理测试
- [x] `test_tools.py` - 工具函数测试
- [x] `test_gallery.py` - Gallery 工具测试
- [x] `test_dcc.py` - DCC 工具测试

### 集成测试
- [ ] 与 Gallery 集成测试
- [ ] 与 Claude Desktop 集成测试
- [ ] 与 CodeBuddy 集成测试
- [ ] Maya 集成测试
- [ ] Blender 集成测试

### E2E 测试
- [ ] 完整工作流测试
- [ ] DCC 工作流测试
- [ ] Midscene AI 测试
- [ ] 错误处理测试
- [ ] 性能测试

## 文档更新

### Python SDK
- [x] README.md
- [x] README_zh.md
- [x] 安装指南
- [x] 配置指南
- [x] 使用示例
- [ ] API 参考
- [ ] 故障排除

### Node.js SDK
- [ ] README.md
- [ ] 安装指南
- [ ] Midscene 集成指南
- [ ] API 参考
- [ ] TypeScript 类型文档

### DCC 集成
- [x] DCC 工具文档（README.md）
- [ ] Maya 集成指南
- [ ] Blender 集成指南
- [ ] Houdini 集成指南
- [ ] DCC 最佳实践

## 里程碑

| 里程碑 | 目标日期 | 状态 |
|--------|----------|------|
| Python SDK Alpha | 2024-12-30 | 完成 |
| Gallery 集成完成 | 2024-12-30 | 完成 |
| DCC 支持 Beta | 2024-12-31 | 完成 |
| Node.js SDK Alpha | TBD | 待开始 |
| Midscene 集成完成 | TBD | 待开始 |
| v1.0 稳定版 | TBD | 待开始 |

## 更新日志

| 日期 | 变更 |
|------|------|
| 2024-12-30 | 创建跟踪文档 |
| 2024-12-30 | 添加 DCC、Node.js、Midscene 阶段 |
| 2024-12-30 | Phase 1 完成 - Python SDK 核心功能 |
| 2024-12-30 | Phase 2 完成 - Gallery 集成 |
| 2024-12-31 | Phase 3 完成 - DCC 支持（get_dcc_context, execute_dcc_command, sync_selection, set_dcc_selection, get_dcc_scene_info, get_dcc_timeline, set_dcc_frame） |
