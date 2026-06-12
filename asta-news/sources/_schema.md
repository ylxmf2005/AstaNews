# Source 注册表 Schema 与贡献规范

`sources/*.yaml` 是 asta-news 的默认数据源注册表，按 stack layer 主题分文件。本地私有源写 `${CLAUDE_PLUGIN_DATA}/sources.local.yaml`（同 schema，同 `id` 覆盖默认条目）。

## 条目 Schema

```yaml
sources:
  - id: arxiv-cs-cl              # 必填，全局唯一，kebab-case
    name: arXiv cs.CL            # 必填，人读名称
    layers: [model, post-training] # 必填，见下方 13 层枚举，1-3 个
    type: rss                    # 必填：rss | atom | json | github-releases | rsshub | html
    url: https://rss.arxiv.org/rss/cs.CL  # 必填；rsshub 类型填路径（如 /anthropic/news）
    priority: P0                 # 必填：P0 每日必抓且参与裁决 / P1 增强 / P2 按需或备用
    parser: ""                   # type=json 时必填，见 fetch_sources.py --help 的 parser 列表
    needs_proxy: false           # true → 经 ASTA_PROXY 抓取；未配代理时跳过并警告
    requires_env: []             # 依赖的 env（如 TWITTER_AUTH_TOKEN），缺失时跳过并警告
    enabled: true                # false → 默认不抓（保留条目供参考/待修复）
    freq: daily                  # daily | weekly | monthly，probe 的新鲜度阈值
    verified: 2026-06-12         # 必填：最近一次 probe 通过的日期
    exclude_pattern: ""          # 可选：标题命中此正则（re.I 由你自带 (?i)）的条目丢弃，用于降噪
    notes: ""                    # 坑位、过滤建议、备用方案
```

**Layer 枚举（13）**：`model` `post-training` `eval` `data` `infra` `serving` `maas` `agent` `embodied` `safety` `product` `business` `devtool`

**type 说明**
- `rss` / `atom`：标准 feed，feedparser 解析。
- `github-releases`：`https://github.com/{owner}/{repo}/releases.atom`，按 atom 解析并提取版本号。
- `json`：结构化 API，需指定 `parser`（hn_algolia / hf_daily_papers / openrouter_models / oss_insight / github_org_repos / swebench / mcp_registry / hf_hub_list / reddit_top / kaggle_datasets / evalplus / aider_yaml）。
- `rsshub`：经 `ASTA_RSSHUB`（默认 `http://127.0.0.1:1200`）的 RSSHub 路由。
- `html`：无 feed 的页面。抓取层只登记 URL 与标题线索，由策展 agent 按需阅读（不做 CSS 选择器爬取——选择器会烂）。

## 贡献验收标准（PR 必读）

1. **先验证再提交**：`uv run asta-news/scripts/probe_source.py --url <url> --type <type>` 必须通过（可达 + 能解析出条目 + 最新条目在 `freq` 阈值内）。把通过日期写进 `verified`。
2. **新鲜度 ≠ HTTP 200**：feed 可能 200 但停更（见下方坑列表）。probe 会查最新条目时间。
3. **优先一手源**：官方 blog/changelog/release > 转述媒体。转述类源只配 P1/P2。
4. **噪声要注明过滤**：每日多版本的仓库（llama.cpp 每次 CI build 都发 release）、alpha/rc 刷屏的（openai/codex、TensorRT-LLM）必须在 `notes` 写过滤规则。
5. **被墙源标 `needs_proxy: true`**，需要凭证的写 `requires_env`，未就绪的设 `enabled: false` 而不是删除。

## 已知坑（加源前先查这里，全部验证于 2026-06-12）

| 坑 | 事实 | 替代 |
|---|---|---|
| Papers with Code | 已死，paperswithcode.com 302 → huggingface.co/papers/trending | HF Daily Papers API |
| `semianalysis.com/feed` | 停更于 2025-09 的旧 feed | `newsletter.semianalysis.com/feed` |
| `qwenlm.github.io/blog/index.xml` | 停更于 2025-09；qwen.ai/blog 是 JS SPA 抓不到 | GitHub org `QwenLM` repos API |
| 机器之心 | RSSHub 路由已移除，jiqizhixin.com/rss 已死 | 量子位 `/qbitai/category/资讯` |
| `*.substack.com` 域名 | 数据中心 IP 被 502；自定义域名的 Substack 正常 | 优先收录自定义域（interconnects.ai、latent.space 等） |
| Anthropic 全站 | 无任何 RSS；部分地区 docs 被 region-block | RSSHub `/anthropic/news`、`/anthropic/engineering`（实测可用） |
| OpenAI / Groq / Ai2 changelog 页 | Cloudflare/Vercel bot 墙 403 | OpenAI 用 `openai.com/news/rss.xml`；codex 用 GitHub releases |
| Reddit | 数据中心 IP 403；无 OAuth 限 ~10 req/min 且必须自定义 UA | 默认 `enabled: false`，热点由 HN/Smol AI 兜底 |
| SWE-bench JSON | raw 在 **master** 分支（main 404），swebench.com 路径 404 | 已收录 raw.githubusercontent master URL |
| LiveBench | 数据文件带日期戳（`table_YYYY_MM_DD.json`），URL 不固定 | 经 GitHub contents API 发现最新文件名（见 notes） |
| ARC-AGI / OSWorld / BFCL 榜单 | 客户端渲染，无静态 JSON | 用 Epoch AI `benchmark_data.zip` 聚合数据替代 |
| X/Twitter | 官方 API 贵；Nitter 不可靠 | 自部署 RSSHub + `TWITTER_AUTH_TOKEN`（cookie）；twitterapi.io（按量付费）为备选 |
