# Contributing

感谢你愿意参与序时 xushi。

## 开发环境

```powershell
uv sync
uv run xushi init --show-token
uv run xushi-daemon
```

## 提交前检查

请至少运行：

```powershell
uv run pytest
uv run ruff check .
node --check plugins/openclaw-xushi/dist/index.js
uv build --wheel
```

如果改动了 OpenClaw 插件运行时代码，也请同步更新 `plugins/openclaw-xushi/dist/index.js`。

## 需求和设计

- 需求变更同步更新 `docs/PROJECT_REQUIREMENTS.md`。
- 架构、接口、数据模型或分发流程变更同步更新 `docs/TECHNICAL_DESIGN.md`。
- 新行为优先补测试，再实现。

## Pull Request

PR 请尽量保持小而清晰，并说明：

- 改了什么。
- 为什么要改。
- 如何验证。
- 是否有未验证风险。

## 安全与隐私

不要在 issue、PR、日志或截图里公开粘贴 token、密钥、真实账号或个人身份信息。安全问题请按 `SECURITY.md` 处理。
