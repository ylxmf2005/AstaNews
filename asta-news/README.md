# asta-news plugin

AI 全栈每日 digest 的 plugin 本体。用法见仓库根 README；本文档面向需要了解内部结构的使用者与贡献者。

## 数据目录

所有可变状态在 `${CLAUDE_PLUGIN_DATA}`（默认 `~/.claude/plugins/data/asta-news/`，env `ASTA_NEWS_HOME` 可覆盖），plugin 升级不受影响：

```
sources.local.yaml    # 本地增删源（merge 进 sources/ 默认表，同 id 覆盖）
rules.local.yaml      # 本地规则覆盖
profile.md            # 编辑画像：兴趣 / 负向兴趣 / voice（人写区 + 机器统计区）
seen.db               # SQLite 去重库（14 天滑窗）
runs/YYYY-MM-DD/      # 当日中间产物（candidates.jsonl 等）
archive/YYYY-MM-DD.md # digest 归档，同时是已推送台账
rsshub/               # 可选自部署 RSSHub 的 compose 与 .env
```

## 环境变量

| 变量 | 作用 | 必需 |
|---|---|---|
| `ASTA_NEWS_HOME` | 覆盖数据目录 | 否 |
| `ASTA_PROXY` | HTTP 代理，用于直连不可达的源（HF / Anthropic / Google / Mistral 等），如 `http://127.0.0.1:7897` | 视网络 |
| `ASTA_RSSHUB` | 自部署 RSSHub 地址，默认 `http://127.0.0.1:1200` | 用 rsshub 源时 |
| `TWITTER_AUTH_TOKEN` | x.com 登录 cookie 的 `auth_token`（RSSHub twitter 路由） | 用 X 源时 |
| `GITHUB_ACCESS_TOKEN` | GitHub PAT、无需 scope（RSSHub trending 路由必需；api.github.com 提额） | 建议 |
| `ASTA_X_LIST_ID` | 策展用 X List 的 id | 用 X 源时 |

## 脚本（黑盒：先 `--help`，不必读源码）

```bash
uv run scripts/fetch_sources.py --help   # 注册表 → candidates.jsonl（并发、best-effort、代理感知）
uv run scripts/dedup.py --help           # seen.db 过滤 / 登记 / 统计 / 自检
uv run scripts/probe_source.py --help    # 单源验证：可达性 + 新鲜度
uv run scripts/doctor.py --help          # 健康检查（--fix 自动初始化）
```

全部 PEP 723 inline deps，装了 [uv](https://docs.astral.sh/uv/) 即零安装运行。
