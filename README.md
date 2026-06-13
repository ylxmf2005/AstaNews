# AstaNews

**🌐 在线网页：https://ylxmf2005.github.io/AstaNews/**

AI 全栈综合资讯平台。每天从 **121+ 个已验证数据源**（论文、模型发布、评测榜单、infra/serving、MaaS changelog、agent、具身、安全、产品/商业、devtool、X KOL、中文媒体、newsletter…）抓取，经确定性脚本去重，由 agent 按编辑准则**层层筛选、多视角呈现**。

**核心特性**
- **三级筛选**：完整级（当天全部）→ 日报级（~20）→ 群聊级（5-8 精选，微信群发）。数量可配。
- **两类 filter**：视角（全栈/技术/产品/商业/研究/具身，重排）× 类别（13 个 stack layer，硬筛），可任意组合。
- **多犀利度**：中性新闻体 / 锐评，一键切换。
- **用图说话**：精选配 AI 找的信息图（评测图/架构图），日报配 og:image。
- **可搜可订**：语义检索（本地向量，跨语言）+ 关键词；每条带"相关新闻"（向量近邻）；Atom 订阅 + 社交分享卡。
- **网站即控制台**：[在线站](https://ylxmf2005.github.io/AstaNews/) 公开只读；本地连后端可服务端检索 / 编辑配置 / 触发运行 / 生成公众号 HTML。
- **全自动**：GitHub Actions + Pages 每日产出并部署；产物即仓库（`site/data/<date>.json`），去重用"仓库即状态"。

底层是一个 Claude Code plugin（编排）+ React 多页站（`web/`）+ FastAPI 后端（`services/`），模块化配置在 `asta-news/config/`。设计与数据流见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 与 [docs/ROADMAP.md](docs/ROADMAP.md)。一条命令体检全平台：`uv run asta-news/scripts/doctor.py`。

## 安装

```bash
# marketplace（推荐）
/plugin marketplace add ylxmf2005/AstaNews
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

## 网页（综合资讯站）

[ylxmf2005.github.io/AstaNews](https://ylxmf2005.github.io/AstaNews/) 是 React 多页应用（`web/`，Next 静态导出）。三级筛选（日报/精选/全部）× 视角（全栈/技术/产品/商业/研究/具身）× 类别（13 layer）任意组合；精选配 AI 信息图；每条带"相关新闻"（向量近邻）；搜索页支持语义 + 关键词。数据来自 `site/data/<date>.json`（digest 产物）。

```bash
cd web && npm install && npm run dev     # 本地开发 http://localhost:3000
# 或静态构建：npm run build → out/（GitHub Actions 自动构建部署）
```

> `site/`（旧的纯静态 fallback）已被 `web/` 取代，保留备查。

## 自动部署（GitHub Actions + Pages）

仓库就是部署单元，Pages 已开启、站点已上线。`.github/workflows/daily-digest.yml` 每天 UTC 01:00（北京 09:00）跑 digest，把产物 commit 进 `site/data/` 与 `editions/`；`deploy-pages.yml` 在产物变化时自动部署 Pages。

要让定时 digest 真正跑起来，只差填一个密钥（用 **API URL + Key** 跑 Claude Code，不是 OAuth）：

```bash
gh secret set ANTHROPIC_API_KEY  --repo ylxmf2005/AstaNews    # 必填
gh secret set ANTHROPIC_BASE_URL --repo ylxmf2005/AstaNews    # 可选：自建/中转 endpoint，留空=官方
gh variable set ANTHROPIC_MODEL  --repo ylxmf2005/AstaNews --body "claude-fable-5"   # 可选
```

GitHub runner 在墙外，被墙的源直连即可（无需代理），数据覆盖反而比本机全；去重用"仓库即状态"（读历史 `site/data/*.json`），无本地依赖。每 60 天自动 prune 旧的全量候选保持仓库精简。原理见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

> 想把仓库迁到 `AstaLab` 组织：到 [github.com/organizations/plan](https://github.com/organizations/plan) 建免费组织（仅此一步需网页，GitHub 不开放 API 建组织），建好后一条命令迁移：
> `gh api -X POST repos/ylxmf2005/AstaNews/transfer -f new_owner=AstaLab`，Pages 与 Actions 自动跟随（Pages 新地址 `astalab.github.io/AstaNews`）。

## 仓库结构

```
.claude-plugin/marketplace.json   # marketplace 清单
asta-news/                        # plugin 本体（skills + scripts + sources）
site/                             # 静态站点（从 data/ 自动加载每日产物）
docs/ARCHITECTURE.md              # 原理：怎么工作、为什么这么设计
docs/superpowers/plans/           # 实施计划
research/                         # 数据源验证报告、参考项目分析、RSSHub 实测
```
