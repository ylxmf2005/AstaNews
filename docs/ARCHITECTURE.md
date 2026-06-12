# AstaNews 原理

> 这份文档解释系统为什么长这样。改 pipeline、加源、调规则之前请先读完——大部分"看起来可以简化"的地方背后都有一条真实踩过的坑。

## 设计目标

每天从 AI 全栈 13 层（model / post-training / eval / data / infra / serving / maas / agent / embodied / safety / product / business / devtool）的一手信息源里，策展出**默认 5 条、最多 8 条、覆盖 ≥3 层**的 digest。三条铁律：宁缺毋滥、全栈视野、新与领先优先。

核心矛盾：每天有 400+ 条候选，但读者只该看 5 条。所以系统的本质不是"聚合器"，而是一条**漏斗**：

```
~98 个源 ──fetch──▶ ~450 候选 ──dedup──▶ ~430 新条目 ──subagent 评分──▶ ~20 推荐 ──editor──▶ 5-8 条
```

## 一、三层架构：什么交给脚本，什么交给 agent

| 层 | 承担什么 | 为什么 |
|---|---|---|
| **确定性脚本层**（`scripts/`） | 抓取、解析、去重、健康检查 | 这些工作要的是稳定和便宜，LLM 在这里只会引入不确定性。脚本是黑盒（PEP 723 + `uv run` 零安装），agent 只看 `--help` 不读源码，避免污染上下文 |
| **Agent 策展层**（`skills/daily-digest/`） | 粗筛、评分、核实、裁决、撰写 | 这些工作要的是判断力。SKILL.md 是工作流，评分细则在 `references/curation.md`（按需加载，渐进披露） |
| **数据层** | `sources/*.yaml`（社区默认表）+ `~/.claude/plugins/data/asta-news/`（本地状态） | 代码与数据分离：贡献源不用碰代码；plugin 升级不会清掉用户状态 |

## 二、数据流逐步拆解

### 1. 抓取（fetch_sources.py）

- **注册表合并**：`sources/*.yaml`（仓库默认，PR 贡献）+ `sources.local.yaml`（个人，同 id 覆盖）。
- **并发 + best-effort**：8 线程，单源失败只记警告绝不拖垮整体——情报系统的首要可用性原则是"缺一个源也要出报"。
- **六种 type**：`rss`/`atom`/`github-releases` 走 feedparser；`json` 按 `parser` 字段分发到 14 个防御式解析器；`rsshub` 经自部署实例；`html` **不抓**——只登记 URL 给策展 agent 按需阅读（CSS 选择器爬 JS 站必然腐烂，这是评估 5 个同类项目得出的统一教训）。
- **diff 型源**：榜单（SWE-bench/EvalPlus/Aider）和目录（OpenRouter models）没有"发布时间"概念，靠与本地快照（`runs/state/*.json`）对比报增量。三条保护：首跑只建快照不报（防全量刷屏）、空 payload 拒绝覆盖快照（防故障恢复后误报全量）、原子写入（防损坏永久卡死）。
- **时间窗**：默认 36h（`rules.scoring.window_hours`），覆盖时差与隔夜积压；arXiv 周末不更新，零候选属正常。

### 2. 去重（dedup.py，SQLite `seen.db`，14 天滑窗）

两层判重，每层都有一个被实测打过脸的细节：

- **URL 规范化精确匹配**：去 tracking 参数用**黑名单制**（utm_*/fbclid/...）而不是白名单制——白名单会把微信公众号链接（身份全在 query 参数里）全部误判成同一篇。另：arXiv 的 pdf/abs/版本号统一归一。
- **模糊标题匹配**（difflib ≥0.78）：先比**数字/版本 token**——"vLLM v0.23.0" 与 "v0.22.0" 相似度 0.96，但它们是两次发布，token 不同直接判不同事件。
- **失败开放**：库损坏放行全部、单条数据异常只放行该条。宁可重复，不可漏报。

### 3. 并行富化评分（subagent fan-out）

候选按层分 3-5 组并行派 subagent，每个 agent：粗筛 → 对幸存者**逐条**打四维分（批量打分会致幻——ArxivDigest 的代码里自带 hallucination warning）→ 写事实依据。关键纪律：

- **四维加权**：novelty 0.35 + leading_edge 0.30 + impact 0.25 + cross_stack 0.10，锚点定义在 curation.md。novelty 看信息增量不看发布日期。
- **事实接地**：每条必须有一个量化点，**只许用原文已述内容**，原文没有就写"原文未给出量化数据"（继承 daily-ai-papers 的 prompt 纪律）。
- **失败即弃选**：评分失败/拿不准 = recommend false。参考项目 customize-arxiv-daily 的反面教材：LLM 失败给满分，垃圾全部置顶。
- **防致幻校验**：返回的 id 必须在输入集合内，多出的丢弃。

### 4. Editor 裁决

负向兴趣（`profile.md`）一票否决 → 同事件合并（一手源优先，HN/HF 讨论降为附注）→ 加权排序 → 约束校验（≥3 层、单层 ≤2、单源 ≤2）→ 落选但接近的进"雷达"。**抓取失败的源必须写进"数据缺口"**——读者要能区分"没发生"和"没看到"。

### 5. 归档与登记

digest 写 `archive/YYYY-MM-DD.md`（这同时就是已推送台账），入选条目登记 `published`、雷达条目登记 `considered` 进 seen.db——第二天它们不会再成为候选（幂等性是实测验收项）。

## 三、网络层（GFW 环境的工程现实）

- **直连优先，代理兜底**：脚本只认 `ASTA_PROXY`（显式管理），并把 `requests` 的 `trust_env` 关掉——IDE/会话注入的 `HTTPS_PROXY` 是内部代理，会劫持并搞挂 github.com 直连请求（实测）。
- `needs_proxy: true` 的源（HF/Google/Mistral/Anthropic/Reddit-RSS 等）强制走代理；没配代理就跳过并如实进数据缺口。
- **RSSHub 是"无 feed 源的统一适配层"**：X/Twitter、Anthropic、量子位、GitHub Trending 都没有可用原生 feed，自部署一个 RSSHub（docker compose，`restart: always`，一次 init 永久自治）把它们全部变成标准 RSS。凭证（x.com 的 auth_token cookie、GitHub PAT）只进容器 `.env`，不进 shell 环境也不进任何会提交的文件。
- 已知无解的墙：Meta AI blog 对直连和代理一律 bot 墙 400——自动管线放弃，由 HN/transformers releases 兜底，急需时策展 agent 用 agent-browser 渲染。

## 四、源注册表的质量机制

- **P0/P1/P2**：P0 每日必抓且影响裁决；P1 增强；P2 按需/备用。日常抓 P0+P1。
- **加源必须先 probe**：`probe_source.py` 验证可达 + 可解析 + **新鲜度**（最新条目时间 vs freq 阈值）。新鲜度检查是被坑出来的：semianalysis.com/feed 和 qwenlm.github.io feed 都是"HTTP 200 但停更 9 个月"的僵尸。
- **降噪声明在源上**：`exclude_pattern` 过滤 RC/alpha/CI tag。llama.cpp 每次 CI build 发 release、PyTorch 的 atom 里全是 trunk/<sha>——这类源要么换端点（PyPI feed）要么带过滤，否则 digest 会被刷屏。
- **probe/doctor 是只读的**（`DIFF_DRY_RUN`）：验证工具不许推进 diff 快照，否则一次冒烟测试就会偷吃当天的增量。
- 已知坑统一记录在 [`asta-news/sources/_schema.md`](../asta-news/sources/_schema.md) 的坑表——加源先查表。

## 五、状态目录一览

```
~/.claude/plugins/data/asta-news/     # plugin 升级不影响（CLAUDE_PLUGIN_DATA / ASTA_NEWS_HOME）
├── sources.local.yaml    # 个人源（同 id 覆盖默认表）
├── rules.local.yaml      # 个人规则（递归深合并进 rules.yaml）
├── profile.md            # 编辑画像：人写区随便改；机器只动 ASTA:STATS 标记之间
├── seen.db               # 去重库（14 天滑窗）
├── runs/<date>/          # 当日中间产物（candidates/fresh/manifest/分组切片）
├── runs/state/           # diff 型源的快照
├── archive/<date>.md     # digest 归档 = 已推送台账
└── rsshub/               # RSSHub compose + .env（凭证在此）
```

## 六、运行模型

plugin 不内置调度。任何调度器（cron / launchd / Claude Code routines / 有人手动）启动一个 Claude Code agent 执行 `/asta-news:daily-digest` 即可。两道防呆：调度声明的预期时间晚 2 小时以上 → 声明过期跳过（不补发旧闻）；当天 archive 已存在 → 不重发。

## 七、这套设计从哪来

构建前评估了 5 个 arXiv-digest 项目（ArxivDigest / customize-arxiv-daily / daily-arXiv-ai-enhanced / llm-arxiv-daily / daily-ai-papers）、openclaw-newsroom、anthropics/skills 与 claude-code 官方 plugin 范例，以及一个早期内部实现；98 个源全部逐一实测（probe 通过日期记录在每个条目的 `verified` 字段）。"继承什么 / 避开什么"的完整清单见 `research/`，实施计划见 [`docs/superpowers/plans/2026-06-12-asta-news-plugin.md`](superpowers/plans/2026-06-12-asta-news-plugin.md)。
