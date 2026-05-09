# Security Policy

## 报告安全问题

如果你发现安全漏洞，请优先使用 GitHub Security Advisory 私下报告。不要公开创建 issue，也不要公开粘贴 token、密钥、真实账号、数据库文件或日志中的敏感内容。

如果当前仓库暂未开启 GitHub Security Advisory，请通过仓库所有者公开资料中的联系方式先发起简短说明，不要附带可直接利用的细节。维护者确认安全渠道后，再补充复现步骤。

## 本地安全边界

序时默认只监听 `127.0.0.1`，并使用本地 token 保护 API。请不要将 daemon 暴露到公网。

## Token 处理

- 不要公开粘贴 token。
- 不要把 `~/.xushi/config.json` 提交到版本控制。
- 如果 token 泄露，请重新运行 `xushi init --force --show-token` 生成新配置，或手动替换配置文件里的 `api_token`。

## 支持范围

当前 v1 重点覆盖本地 daemon、CLI、OpenClaw 插件、SQLite 存储和安装脚本。第三方 agent、webhook 接收端和用户自定义命令的安全边界由对应系统负责。
