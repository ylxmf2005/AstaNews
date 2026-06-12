# asta-news Plugin 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一个 Claude Code plugin（多 skill 一入口），每天由外部启动的 agent 调用，产出覆盖 AI 全栈 13 层（model / post-training / eval / data / infra / serving / maas / agent / embodied / safety / product / business / devtool）的每日精选 digest（默认 5 条、最多 8 条、≥3 层），源注册表社区可贡献。

**Architecture:** 三层：① 确定性脚本层（fetch → normalize → dedup，黑盒脚本，uv run + PEP 723）；② Agent 策展层（daily-digest SKILL 指挥：并行 subagent 按层富化评估 → editor 综合裁决）；③ 数据层（plugin 内 `sources/*.yaml` 为社区 PR 贡献的默认注册表，`~/.claude/plugins/data/asta-news/` 为本地覆盖 + 状态 + 归档，plugin 升级不丢）。部署类（RSSHub）归 `setup` skill，一次 init 后靠 docker `restart: always` 自治。

**Tech Stack:** Claude Code plugin（plugin.json + skills + ${CLAUDE_PLUGIN_ROOT}/${CLAUDE_PLUGIN_DATA}）、Python 3.12（uv run、PEP 723 inline deps：requests/feedparser/pyyaml）、SQLite（去重）、Docker Compose（RSSHub，可选）。

---

## 调查结论摘要（决策依据，全部已验证 2026-06-12）

1. **网络现实（本机）**：直连可达 arXiv/GitHub/OpenAI/HN/MCP registry/smol.ai/interconnects/deepmind；**直连不可达** huggingface.co、reddit.com、anthropic.com、ai.google.dev、mistral.ai、x.ai。系统代理 `http://127.0.0.1:7897` 可解锁 HF/Anthropic/Google/Mistral（HF daily_papers JSON 实测 200）；Reddit 仍 403（数据中心 IP，需 OAuth 或弃用）。→ source 条目需要 `needs_proxy` 标志，脚本读 `ASTA_PROXY` env（doctor 自动探测 `scutil --proxy`）。
2. **RSSHub 实测**（docker 部署成功）：`/anthropic/news`、`/anthropic/engineering`、`/deepmind/blog`、`/qbitai/category/资讯`、`/papers/category/arxiv/cs.AI`、`/huggingface/daily-papers` 零配置可用；`/github/trending` 需真实 GITHUB_ACCESS_TOKEN（GraphQL）；`/twitter/*` 需 `TWITTER_AUTH_TOKEN`（x.com cookie，旧项目同款方案仍有效；`TWITTER_COOKIE` 已废弃）。机器之心无可用源（路由已移除、原生 feed 已死），用量子位替代。
3. **要避开的坑**（来自 5 个项目逐行评估）：批量打分致幻（ArxivDigest 自带 hallucination warning）；LLM 失败给满分置顶（customize-arxiv-daily）；裸 0-10 分校准差（其唯一 open issue）；第三方单点（paperswithcode 已死，302 → HF；个人 censorship worker 挂了悄悄丢论文）；CSS 类爬 JS 站；无界 README 增长。
4. **要继承的资产**：7 天滑窗 ID 去重 + 退出码门控（daily-arXiv-ai-enhanced/check_stats.py）；schema 强制结构化输出；自然语言兴趣画像 + **显式负向兴趣**；事实接地摘要 prompt（daily-ai-papers，"至少一个量化发现 + 对从业者的含义"）；两段式策展（逐条评分 → editor 元裁决，customize-arxiv-daily + openclaw-newsroom llm_editor）；URL 规范化 + 模糊标题 SQLite 去重（openclaw-newsroom/dedup_db.py）；编辑画像文件"人写区 + 机器只改标记小节"（update_editorial_profile.py）；GitHub 链接富化（star/push date）；旧项目 Shieru 的过期跳过（>2h 跳过不补发）与"无更新账号也要列出"的可信度模式。
5. **Plugin 规范**：`.claude-plugin/plugin.json`（仅 name 必填）；skills/ 在 plugin 根；调用名 `asta-news:<skill>`；`${CLAUDE_PLUGIN_ROOT}` 指 plugin 根（升级时被替换）、`${CLAUDE_PLUGIN_DATA}` → `~/.claude/plugins/data/asta-news/`（持久）；本地测试 `claude --plugin-dir`；社区安装走仓库根 `.claude-plugin/marketplace.json`。
6. **PwC 已死**：paperswithcode.com 302 → huggingface.co/papers/trending。任何 source 列表不得包含。
7. **stale feed 陷阱**：semianalysis.com/feed 停在 2025-09，新 feed 是 newsletter.semianalysis.com/feed；qwenlm.github.io feed 停在 2025-09（用 GitHub org 代替）。→ doctor 必须做"新鲜度检查"而不只 HTTP 200。

---

## File Structure

```
AstaNews/                                    # 仓库根（社区贡献入口）
├── .claude-plugin/marketplace.json          # /plugin marketplace add 用
├── README.md                                # 仓库说明 + 安装 + 贡献指南
├── docs/superpowers/plans/…                 # 本计划
├── research/                                # 调查产物（不进 plugin）
└── asta-news/                               # ← plugin 根
    ├── .claude-plugin/plugin.json
    ├── README.md                            # plugin 使用说明
    ├── rules.yaml                           # 编辑规则（条数/层数/权重/语言/画像）
    ├── sources/                             # 默认源注册表（社区 PR 改这里）
    │   ├── _schema.md                       # 条目 schema + 贡献规范
    │   ├── papers.yaml
    │   ├── releases-maas.yaml
    │   ├── infra-serving.yaml
    │   ├── evals-data.yaml
    │   ├── agents-devtool.yaml
    │   ├── embodied-safety.yaml
    │   └── community-business.yaml          # HN/newsletters/X/Reddit/中文媒体
    ├── scripts/                             # 黑盒脚本（--help 优先，不读源码）
    │   ├── fetch_sources.py                 # 注册表 → candidates.jsonl（并发、best-effort、代理感知）
    │   ├── dedup.py                         # SQLite seen 库：URL 规范化 + 模糊标题 + 滑窗
    │   ├── probe_source.py                  # 单源校验（可达性 + 新鲜度），doctor/add-source 共用
    │   └── doctor.py                        # 健康检查：deps/代理/数据目录/P0 源抽样/RSSHub
    ├── skills/
    │   ├── daily-digest/
    │   │   ├── SKILL.md                     # 主工作流（编排 + 裁决规则）
    │   │   └── references/
    │   │       ├── curation.md              # 评分细则 + prompt 模板（逐条 & editor 两段）
    │   │       └── output-format.md         # digest 模板（zh，HTML/MD 双格式注意点）
    │   ├── setup/
    │   │   ├── SKILL.md                     # 一次性 init：数据目录/代理/可选 RSSHub/doctor
    │   │   └── assets/
    │   │       ├── docker-compose.rsshub.yml
    │   │       ├── rules.local.template.yaml
    │   │       └── profile.template.md      # 编辑画像（人写区+机器区标记）
    │   └── manage-sources/
    │       └── SKILL.md                     # 加/删/测源、改规则、引导 PR 回上游
    └── (运行时数据，不在 plugin 内)
        ~/.claude/plugins/data/asta-news/    # = ${CLAUDE_PLUGIN_DATA}，env ASTA_NEWS_HOME 可覆盖
        ├── sources.local.yaml               # 本地增删源（merge 进默认表）
        ├── rules.local.yaml                 # 本地规则覆盖
        ├── profile.md                       # 编辑画像（兴趣/负向兴趣/voice）
        ├── seen.db                          # SQLite 去重库
        ├── runs/YYYY-MM-DD/candidates.jsonl # 当日中间产物
        └── archive/YYYY-MM-DD.md            # digest 归档（也是已推送台账）
```

### 数据 schema

**source 条目**（sources/*.yaml，每文件顶层 `sources:` 列表）：
```yaml
- id: arxiv-cs-cl                  # 唯一，kebab-case
  name: arXiv cs.CL
  layers: [model, post-training]   # 13 层枚举之一/多
  type: rss                        # rss|atom|json|github-releases|rsshub|html
  url: https://rss.arxiv.org/rss/cs.CL
  priority: P0                     # P0 每日必抓 / P1 增强
  needs_proxy: false               # true → 走 ASTA_PROXY
  freq: daily                      # daily|weekly|monthly（doctor 新鲜度阈值）
  notes: "weekdays only; dedupe announce_type=new"
```

**candidates.jsonl 每行**：
```json
{"id":"<source_id>:<item-hash>","source":"arxiv-cs-cl","layers":["model"],"title":"…","url":"…","published":"2026-06-12T03:00:00Z","summary":"原始摘要/正文截断1200字","extra":{"arxiv_id":"2606.12345","stars":123}}
```

**rules.yaml**（完整内容见 Task 3）：max_items 8 / default_items 5 / min_layers 3 / max_per_layer 2 / max_per_source 2 / 权重 novelty 0.35 + leading_edge 0.30 + impact 0.25 + cross_stack 0.10 / 语言 zh（专名保留英文）/ staleness_skip_hours 2。

---

## Task 1: 仓库与 plugin 骨架

**Files:** Create `AstaNews/.claude-plugin/marketplace.json`, `AstaNews/README.md`, `asta-news/.claude-plugin/plugin.json`, `asta-news/README.md`

- [ ] plugin.json：
```json
{
  "name": "asta-news",
  "displayName": "AstaNews — AI Full Stack Daily",
  "description": "Daily AI full-stack digest agent: papers, model releases, evals, infra/serving, agents, embodied, safety, product/business, devtools. Community-extensible sources.",
  "version": "0.1.0",
  "author": { "name": "Asta Lab" },
  "repository": "https://github.com/asta-lab/AstaNews"
}
```
- [ ] marketplace.json（仓库根 `.claude-plugin/`）：`{"name":"asta-lab","plugins":[{"name":"asta-news","source":"./asta-news","description":"…","version":"0.1.0","category":"productivity"}]}`
- [ ] 两个 README：仓库 README 含安装（`/plugin marketplace add <repo>` + `/plugin install asta-news@asta-lab`、本地 `claude --plugin-dir ./asta-news`）、三条编辑铁律、贡献流程（PR 改 sources/*.yaml，CI 思路：跑 probe_source.py）；plugin README 含 skill 清单与数据目录说明。
- [ ] 验证：`python3 -c "import json;json.load(open('asta-news/.claude-plugin/plugin.json'))"` 通过。

## Task 2: source 注册表（核心数据资产）

**Files:** Create `asta-news/sources/_schema.md` + 7 个 yaml

- [ ] 将调查验证过的全部源写入分层 yaml（仅收已验证 URL；UNVERIFIED 的进 notes 标注待生产网络复验；明确排除：paperswithcode、semianalysis 旧 feed、qwenlm.github.io feed、机器之心）。要点清单（详 URL 以 research 报告为准，全部已在对话中验证）：
  - papers.yaml：arXiv RSS（cs.CL/LG/AI/RO/CR/DC/SE/MA，合并语法 `cs.CL+cs.LG`）、HF daily_papers JSON API（needs_proxy）、HF blog feed（needs_proxy）、Interconnects、Ahead of AI、alphaXiv（P2 notes-only，MCP+OAuth）。
  - releases-maas.yaml：OpenAI news RSS、DeepMind blog RSS、Anthropic news/engineering（rsshub type）、DeepSeek /updates（html）、Qwen GitHub org（json，api.github.com）、Moonshot platform.kimi.ai/blog、Z.ai release-notes、MiniMax news、Cohere changelog RSS（docs.cohere.com/changelog.rss）、OpenRouter models JSON（**diff 检测新模型**）、Fireworks changelog.md、Together changelog、Claude API release notes（needs_proxy，html）、Gemini API changelog（needs_proxy）、Mistral news（needs_proxy）、BFL blog、ElevenLabs changelog。
  - infra-serving.yaml：GitHub releases.atom × {vllm, sglang, TensorRT-LLM(滤RC), llama.cpp(滤构建版,P2), ollama, transformers, trl, peft, pytorch, DeepSpeed, Megatron-LM, ray}、SemiAnalysis **newsletter.**semianalysis.com/feed、NVIDIA blog/dev blog RSS、AWS What's New RSS（关键词滤）、Epoch AI data hub（monthly html）。
  - evals-data.yaml：SWE-bench leaderboards.json（**master** 分支 raw）、LiveBench 日期戳文件（经 GitHub contents API 发现最新名）、Epoch benchmark_data.zip、LMArena HF dataset（needs_proxy）、Artificial Analysis API（须 key，notes-only P2）、Aider polyglot YAML raw、EvalPlus results.json、terminal-bench registry.json、HF datasets API sort=createdAt（needs_proxy）、Kaggle list API、RewardBench（needs_proxy）。
  - agents-devtool.yaml：MCP registry API、MCP spec releases.atom、Claude Code raw CHANGELOG.md + releases.atom、Cursor changelog RSS（cursor.com/changelog/rss.xml）、openai/codex releases.atom（滤 alpha）、gemini-cli releases.atom（滤 preview）、LangGraph/LlamaIndex/OpenHands/CrewAI releases.atom、awesome-mcp-servers commits.atom、A2A releases.atom、Simon Willison Atom、Latent Space feed。
  - embodied-safety.yaml：arXiv cs.RO（关键词 VLA/humanoid/manipulation 过滤在策展层）、Physical Intelligence pi.website/blog（html）、Figure/1X/Unitree/Skild/World Labs（html，P1/P2）、Alignment Forum feed.xml、Transformer Circuits（html）、UK AISI（html）、METR（html）、AI Incident Database RSS、Import AI（jack-clark.net/feed）。
  - community-business.yaml：HN Algolia front_page query=AI/LLM、hnrss frontpage、Smol AI News rss、Last Week in AI、ChinAI（notes：substack 数据中心 502）、TechCrunch AI feed、量子位 rsshub、GitHub trending（OSS Insight trends API P0 + mshibanami RSS P1）、X/Twitter rsshub `/twitter/list/{ASTA_X_LIST_ID}`（notes：需 TWITTER_AUTH_TOKEN；KOL 列表继承旧项目 15 人 + DrJimFan 等扩充建议）、Reddit r/LocalLLaMA（notes：本网络 403，需 OAuth 或免）。
- [ ] _schema.md：条目 schema、layer 枚举、P0/P1 标准（P0=每日必抓且影响裁决，P1=增强）、贡献验收（必须先 `uv run scripts/probe_source.py --url …` 通过 + 注明验证日期）。
- [ ] 验证：`uv run --with pyyaml python3 -c "...for f in glob('sources/*.yaml'): yaml.safe_load..."` 全通过 + id 唯一 + layers 合法。

## Task 3: rules.yaml + 画像模板

**Files:** Create `asta-news/rules.yaml`, `asta-news/skills/setup/assets/profile.template.md`, `rules.local.template.yaml`

- [ ] rules.yaml 完整内容：
```yaml
layers: [model, post-training, eval, data, infra, serving, maas, agent, embodied, safety, product, business, devtool]
edition:
  max_items: 8
  default_items: 5
  min_layers: 3
  max_per_layer: 2
  max_per_source: 2
  language: zh            # 中文为主，专有名词保留英文
  staleness_skip_hours: 2 # 启动时间距预定窗口 >2h 则声明过期跳过，不补发旧闻
scoring:
  weights: { novelty: 0.35, leading_edge: 0.30, impact: 0.25, cross_stack: 0.10 }
  window_hours: 36        # 候选新鲜度窗口
  prefer_primary_source: true   # 同一事件优先官方一手源
dedup:
  seen_window_days: 14
  title_similarity: 0.78
```
- [ ] profile.template.md：人写区（兴趣描述、**负向兴趣**、voice）+ 机器区标记 `<!-- ASTA:STATS:START/END -->`。
- [ ] 验证：yaml 可解析。

## Task 4: scripts/fetch_sources.py

**Files:** Create `asta-news/scripts/fetch_sources.py`

- [ ] PEP 723 头（requests, feedparser, pyyaml）；CLI：`--sources-dir --data-dir --only <ids> --layers <…> --window-hours 36 --out candidates.jsonl`；行为：merge sources.local.yaml → 并发抓取（ThreadPoolExecutor 8 workers，每源 timeout 20s）→ 按 type 解析（rss/atom→feedparser；json→每源 jq 风格的 item 抽取规则内置 per-id handler 注册表：hf_daily_papers/openrouter_models_diff/oss_insight/hn_algolia/swebench/mcp_registry…；github-releases→feedparser；rsshub→base url env `ASTA_RSSHUB=http://127.0.0.1:1200`；html→只记 url 留给 agent 读）→ 规范化输出 JSONL → stderr 报每源 ok/fail/条数，**任一源失败不影响整体**（best-effort），结尾打印汇总表。OpenRouter diff：state 文件 `runs/openrouter_models.json` 对比新增模型。需代理的源在无 `ASTA_PROXY` 时跳过并警告。退出码：0 有新候选 / 1 全空 / 2 配置错误。
- [ ] 验证：`uv run scripts/fetch_sources.py --only arxiv-cs-cl,hn-frontpage,openai-news --out /tmp/c.jsonl` 产出真实条目。

## Task 5: scripts/dedup.py + probe_source.py + doctor.py

**Files:** Create 三脚本

- [ ] dedup.py：SQLite `seen(id, url_norm, title, source, layer, status, first_seen)`；URL 规范化（去 query/fragment/www/utm、强制 https、剥 arXiv 版本号）；难例走 difflib 标题相似度 ≥ rules.dedup.title_similarity、窗口 seen_window_days；CLI：`--filter candidates.jsonl`（输出未见过的）、`--record published.jsonl --status published`、`--stats`。失败开放：库损坏时警告并放行全部（宁重复勿丢）。
- [ ] probe_source.py：输入单条 source（--id 从注册表取或 --url 临时）→ 可达性、解析出 ≥1 条目、最新条目时间 vs freq 阈值（新鲜度！防 stale-feed 陷阱）→ 人读报告 + 退出码。
- [ ] doctor.py：检查 uv/python/docker、ASTA_PROXY（自动探测 scutil 7897 类端口并建议）、数据目录完整性、随机抽 3 个 P0 源 probe、RSSHub healthz（若配置）、seen.db 可写。`--fix` 自动建目录/拷模板。
- [ ] 验证：对 dedup.py 跑一个内置 `--self-test`（插入→重查→模糊匹配三断言）；probe arxiv-cs-cl 通过；doctor 全绿（RSSHub 项允许 skip）。

## Task 6: daily-digest SKILL（核心策展）

**Files:** Create `skills/daily-digest/SKILL.md`, `references/curation.md`, `references/output-format.md`

- [ ] SKILL.md（≤300 行，工作流层）：frontmatter `name/description`（pushy：每日 digest、AI 新闻、日报、推送等触发词）。流程：
  1. 过期检查（staleness_skip_hours，旧项目模式：过期则输出一行声明并停止）。
  2. `uv run ${CLAUDE_PLUGIN_ROOT}/scripts/fetch_sources.py …`（黑盒，--help 优先）。
  3. `uv run …/dedup.py --filter` → 新候选。
  4. **并行 subagent 富化**：按层组分 3-5 个 subagent（papers 组读 HF 票数/摘要；releases 组读官方 changelog 原文；community 组交叉验证热度），每个返回结构化 JSON（候选 id、layer、novelty/leading_edge/impact/cross_stack 各 0-5 + 一句事实依据 + 量化发现）。**单条评分不批量**（防致幻）；评分失败 = 弃选不是满分。
  5. Editor 裁决（读 references/curation.md）：负向兴趣过滤 → 加权排序 → 同事件合并（官方一手源优先）→ 选 default_items 条（质量不足可少于 5，上限 8）→ 校验 ≥min_layers 层、≤max_per_layer、≤max_per_source，不满足则替换补足。
  6. 写 archive/YYYY-MM-DD.md（output-format.md 模板）+ 在会话输出全文。
  7. `dedup.py --record` 登记已发布 + 入选/落选简要 ledger（喂未来画像调优）。
  失败处置：单源失败列入"今日数据缺口"小节（可信度模式：缺什么要说）。
- [ ] curation.md：完整评分 rubric（每维 0-5 锚点定义，novelty=信息新增量而非发布日期；leading_edge=是否推进 SOTA/首次公开做法）、subagent 富化 prompt 模板（含"至少一个量化事实，仅限原文已述，不确定要声明"——继承 daily-ai-papers 接地规则）、editor prompt 模板（含 recently-published 列表防重、"3 条优质 > 7 条平庸"——继承 openclaw llm_editor）。
- [ ] output-format.md：digest 模板：标题 `🛰️ AstaNews — {date}`；每条：`[layer emoji+名] **标题**`、2-4 句（是什么/为什么重要/量化点）、链接（一手源优先 + 讨论链接）；尾部：`📡 雷达`（值得关注但未入选 3-5 条一句话）+ `⚠️ 数据缺口`；中文为主专名英文；Telegram HTML 注意事项（U+00A0 缩进 hack，继承旧项目）。
- [ ] 验证：frontmatter 过 skill-creator quick_validate 允许键集合。

## Task 7: setup SKILL + RSSHub assets

**Files:** Create `skills/setup/SKILL.md`, `assets/docker-compose.rsshub.yml`

- [ ] compose 文件 = 实测验证版（research/rsshub-test 的产物：rsshub:chromium-bundled + redis、127.0.0.1:1200、TWITTER_AUTH_TOKEN/GITHUB_ACCESS_TOKEN env 占位、healthcheck、restart always）。
- [ ] SKILL.md（开源 open-notebook 模式：Prerequisites → 步骤 → verify → env 表 → 持久化说明 → troubleshooting）：① `doctor.py --fix` 建数据目录+拷模板；② 代理探测写入 `ASTA_PROXY` 建议（settings env 或 shell profile）；③ 可选 RSSHub：拷 compose 到 `${CLAUDE_PLUGIN_DATA}/rsshub/`、引导取 x.com auth_token cookie + GitHub PAT（无 scope）、`docker compose up -d`、healthz 验证、说明 restart:always 自治无需重部署；④ X List 配置（ASTA_X_LIST_ID）；⑤ 终检 doctor 全绿 + 试跑 `fetch_sources.py --only …`。幂等可重跑。env 表：ASTA_NEWS_HOME / ASTA_PROXY / ASTA_RSSHUB / TWITTER_AUTH_TOKEN / GITHUB_ACCESS_TOKEN / ASTA_X_LIST_ID。
- [ ] 验证：`docker compose -f assets/docker-compose.rsshub.yml config` 通过。

## Task 8: manage-sources SKILL

**Files:** Create `skills/manage-sources/SKILL.md`

- [ ] 功能：加源（先 probe_source.py 验证 + 新鲜度，写 sources.local.yaml，提示"长期有效请向上游仓库提 PR 进 sources/*.yaml"）；删/禁源；测全部源（probe 循环）；改规则（rules.local.yaml 覆盖机制说明）；改画像（profile.md 人写区）。贡献规范引用 sources/_schema.md。
- [ ] 验证：描述触发词覆盖"加个源/添加订阅/不想看X了/调整规则"。

## Task 9: 端到端实测

- [ ] `claude --plugin-dir ./asta-news` 可加载（或人工按 SKILL.md 全流程跑）。
- [ ] 真实跑一次：fetch（≥10 源成功）→ dedup → 按 curation.md 策展 → 生成当日 digest，断言：条数 ≤8、层数 ≥3、每条有一手链接、archive 文件落盘、seen.db 记录、再跑一次 dedup 后这些条目被滤掉（幂等）。
- [ ] 修掉实测暴露的问题；把样例 digest 存 `asta-news/README.md` 示例区。

## Self-Review 结论

- 规格覆盖：每日 5/8 条 ✓(rules+editor)；≥3 层 ✓；新/领先权重 ✓(scoring)；社区贡献 ✓(sources/ PR + manage-sources + marketplace)；setup/部署 ✓(Task 7)；外部启动、不管定时 ✓(无 cron 任务，过期检查兜底)；论文/开源项目/X/changelog 全覆盖 ✓(Task 2 七文件)。
- 类型一致性：candidates.jsonl 字段在 Task 4/5/6 一致；数据目录路径统一 `${CLAUDE_PLUGIN_DATA}`+`ASTA_NEWS_HOME` 覆盖。
- 无 placeholder：源 URL 细节在对话 research 报告中已全量验证，Task 2 执行时照录。
