# 贡献指南

感谢你对 AuroraView 的关注！我们欢迎各种形式的贡献。

## 行为准则

参与本项目即表示你同意遵守我们的[行为准则](https://github.com/try-auroraview/auroraview/blob/main/CODE_OF_CONDUCT.md)。

## 如何贡献

### 报告 Bug

1. 在 [GitHub Issues](https://github.com/try-auroraview/auroraview/issues) 搜索是否已有相关问题
2. 如果没有，创建新 Issue，包含：
   - 清晰的标题和描述
   - 复现步骤
   - 期望行为 vs 实际行为
   - 环境信息（操作系统、Python 版本、DCC 应用版本等）

### 功能请求

1. 在 Issues 中搜索是否已有类似请求
2. 创建新 Issue，说明：
   - 功能的用例和价值
   - 建议的实现方式（可选）
   - 是否愿意参与实现

### 提交代码

1. Fork 仓库
2. 创建功能分支：`git checkout -b feature/my-feature`
3. 提交更改：`git commit -m 'Add some feature'`
4. 推送到分支：`git push origin feature/my-feature`
5. 创建 Pull Request

## 开发环境设置

### 前置要求

- Python 3.7+
- Rust 1.70+
- Node.js 18+
- [just](https://github.com/casey/just) 命令运行器

### 克隆仓库

```bash
git clone https://github.com/try-auroraview/auroraview.git
cd auroraview
```

### 安装依赖

```bash
# 使用 vx 自动管理工具链
vx just setup

# 或手动安装
pip install -e ".[dev]"
npm install
```

### 构建项目

```bash
# 完整构建
just build

# 仅构建 Rust
just build-rust

# 仅构建 Python wheel
just build-wheel
```

### 运行测试

```bash
# 运行所有测试
just test

# 仅 Rust 测试
just test-rust

# 仅 Python 测试
just test-python

# 带覆盖率
just test-coverage
```

## 代码规范

### Rust

- 遵循 [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)
- 使用 `cargo fmt` 格式化代码
- 使用 `cargo clippy` 检查代码质量
- 所有公共 API 需要文档注释

```rust
/// 创建新的 WebView 实例
///
/// # Arguments
///
/// * `options` - WebView 配置选项
///
/// # Returns
///
/// 返回 WebView 句柄
///
/// # Errors
///
/// 如果创建失败，返回 `WebViewError`
pub fn create(options: WebViewOptions) -> Result<WebViewHandle, WebViewError> {
    // ...
}
```

### Python

- 遵循 [PEP 8](https://peps.python.org/pep-0008/)
- 使用 `ruff` 进行代码检查和格式化
- 使用类型注解
- 所有公共 API 需要 docstring

```python
def create_webview(
    url: str | None = None,
    html: str | None = None,
    *,
    title: str = "AuroraView",
    width: int = 800,
    height: int = 600,
) -> WebView:
    """创建新的 WebView 实例。

    Args:
        url: 要加载的 URL
        html: 要加载的 HTML 内容
        title: 窗口标题
        width: 窗口宽度
        height: 窗口高度

    Returns:
        WebView 实例

    Raises:
        ValueError: 如果同时提供 url 和 html
    """
    ...
```

### TypeScript

- 使用 ESLint 和 Prettier
- 所有导出需要类型定义
- 使用 JSDoc 注释

```typescript
/**
 * 调用后端方法
 * @param method - 方法名
 * @param params - 参数
 * @returns Promise 返回调用结果
 * @throws {AuroraViewError} 调用失败时抛出
 */
async call<T>(method: string, params?: unknown): Promise<T> {
  // ...
}
```

## 测试规范

### 单元测试

- 每个新功能都需要测试
- 每个 Bug 修复都需要回归测试
- 测试文件放在 `tests/` 目录

### Rust 测试

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use rstest::*;

    #[rstest]
    fn test_create_webview() {
        let options = WebViewOptions::default();
        let result = create(options);
        assert!(result.is_ok());
    }
}
```

### Python 测试

```python
import pytest
from auroraview import WebView

def test_create_webview():
    wv = WebView(html="<h1>Test</h1>")
    assert wv is not None

@pytest.mark.parametrize("width,height", [
    (800, 600),
    (1024, 768),
    (1920, 1080),
])
def test_window_size(width, height):
    wv = WebView(width=width, height=height)
    assert wv.width == width
    assert wv.height == height
```

## 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### 类型

- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构（不是新功能或修复）
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具相关

### 示例

```
feat(webview): add support for custom user agent

Add ability to set custom user agent string when creating WebView.

Closes #123
```

```
fix(qt): resolve focus issue in Maya 2025

The WebView was not receiving focus events properly when embedded
in Maya's Qt container. This was caused by incorrect HWND parenting.

Fixes #456
```

## Pull Request 流程

1. 确保所有测试通过：`just test`
2. 确保代码风格检查通过：`just lint`
3. 更新相关文档
4. 填写 PR 模板
5. 等待代码审查
6. 根据反馈进行修改
7. 合并后删除功能分支

### CI 并发控制

所有 CI 工作流都配置了并发控制，可以自动取消冗余的运行：

- 当你向 PR 推送新提交时，该 PR 正在进行的 CI 运行会自动取消
- 这可以节省 CI 资源并更快地获得最新更改的反馈
- 并发控制按工作流和 PR 编号分组，因此不同的 PR 独立运行

```yaml
# 所有工作流中使用的并发配置示例
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

这意味着：
- 你不需要等待旧的 CI 运行完成就可以推送新提交
- CI 始终测试你的最新代码
- 发布工作流（标签推送）永远不会被取消，以确保发布完成

### PR 检查清单

- [ ] 代码遵循项目规范
- [ ] 添加了必要的测试
- [ ] 更新了相关文档
- [ ] 提交信息遵循规范
- [ ] CI 检查全部通过

## 发布流程

项目使用 [Release Please](https://github.com/google-github-actions/release-please-action) 自动管理版本和发布。

1. 合并到 `main` 分支的 PR 会自动创建 Release PR
2. Release PR 合并后自动发布新版本
3. 版本号遵循 [语义化版本](https://semver.org/)

## 项目结构

```
auroraview/
├── crates/              # Rust crates
│   ├── auroraview/      # 核心库
│   ├── auroraview-cli/  # CLI 工具
│   └── ...
├── python/              # Python 绑定
│   └── auroraview/
├── packages/            # 前端包
│   └── auroraview-sdk/  # TypeScript SDK
├── docs/                # 文档
├── examples/            # 示例
├── gallery/             # Gallery 应用
└── tests/               # 测试
```

## 获取帮助

- [GitHub Discussions](https://github.com/try-auroraview/auroraview/discussions) - 问题讨论
- [Discord](https://discord.gg/auroraview) - 实时交流
- [文档](https://auroraview.dev) - 官方文档

## 致谢

感谢所有贡献者！

<a href="https://github.com/try-auroraview/auroraview/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=try-auroraview/auroraview" />
</a>
