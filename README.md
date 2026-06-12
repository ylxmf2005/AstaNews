# AstaNews

AI 全栈每日情报。一条命令，从论文、模型发布、评测榜单、infra/serving、MaaS changelog、agent 生态、具身智能、安全、产品/商业、devtool 共 **13 个 stack layer** 的已验证数据源中，策展出当日最值得读的内容——**默认 5 条，最多 8 条，覆盖至少 3 层**。

这是一个 Claude Code plugin：数据源注册表开放贡献，抓取与去重由确定性脚本完成，筛选与撰写由 agent 按编辑准则裁决。

## 安装

```bash
# marketplace（推荐）
/plugin marketplace add asta-lab/AstaNews
/plugin install asta-news@asta-lab

# 本地开发
claude --plugin-dir ./asta-news
```

首次使用先运行 `/asta-news:setup`：初始化数据目录、探测网络代理、（可选）部署 RSSHub 以接入 X/Twitter、Anthropic、GitHub Trending 等没有原生 feed 的源。初始化是一次性的，之后日常只需要 `/asta-news:daily-digest`。

## 编辑准则

1. **宁缺毋滥**：每天最多 8 条，默认 5 条，质量不足就少发。
2. **全栈视野**：至少覆盖 3 个 stack layer，单层最多 2 条。
3. **新与领先优先**：信息增量（不是发布日期）和是否推进 SOTA / 首次公开做法，是最重的排序信号。

## Skills

| Skill | 用途 |
|---|---|
| `/asta-news:daily-digest` | 生成当日 digest：抓取 → 去重 → 并行富化评分 → editor 裁决 → 归档输出 |
| `/asta-news:setup` | 初始化与健康检查：数据目录、代理、可选 RSSHub 部署 |
| `/asta-news:manage-sources` | 加/删/测数据源、调整规则、维护兴趣画像 |

定时运行可接入任何调度器（cron / launchd / Claude Code routines），调用 `claude -p "/asta-news:daily-digest"` 即可；digest 自带过期保护，启动太晚会声明跳过而不是补发旧闻。

## 贡献数据源

- **进默认注册表**：改 `asta-news/sources/*.yaml` 提 PR。schema 与验收标准见 [`asta-news/sources/_schema.md`](asta-news/sources/_schema.md)；PR 前必须 `uv run asta-news/scripts/probe_source.py --url <url>` 通过（可达性 + 新鲜度），并在 `notes` 标注验证日期。
- **只想自己用**：`/asta-news:manage-sources` 写入本地 `sources.local.yaml`，不动仓库。
- **调编辑规则**：全局默认在 `asta-news/rules.yaml`（走 PR）；个人口味在本地 `rules.local.yaml`。
- 已知坑收录于 `_schema.md`（Papers with Code 已死、semianalysis 旧 feed 停更、机器之心无可用源等），加源前先看。

## 仓库结构

```
.claude-plugin/marketplace.json   # marketplace 清单
asta-news/                        # plugin 本体
docs/superpowers/plans/           # 设计与实施计划
research/                         # 数据源验证报告、参考项目分析、RSSHub 实测
```
