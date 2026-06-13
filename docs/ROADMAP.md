# AstaNews 综合资讯平台 — PRD & Roadmap（单一事实源）

> 这份文档是产品的总纲，也是 5am 自动迭代循环的输入。每次迭代：读这里 → 选最高价值的未完成项 → 实现 → 验证 → commit → 更新本文件状态 → 继续。不要停。

## 0. 愿景

把 AstaNews 从「每天一条微信精选 digest」升级成 **AI 全栈综合资讯平台**：
- **多级筛选**：完整级（当天全部）→ 日报级（~20，可配）→ 群聊级（~5 精选）。数量可配置，层层筛选。
- **多视角**：同一批新闻，按受众给不同视角（技术 / 产品 / 商业 / 研究 / infra-ops…），各视角有专属排序与改写。
- **多犀利度**：中性叙述 / 锐评 / 深读，几档可选。
- **可搜索**：混合检索（BM25 关键词 + 向量相似），"搜一条新闻 → 找相关"，本地 embedding 模型，不强依赖 OpenAI。
- **配图**：日报与网页都配图（借鉴橘鸦），用图说话。
- **网站即控制台**（终态）：查看 / 触发运行 / 配置 / 定时 / 搜索，全在网站里。账号体系（先不做，但架构预留）。
- **多渠道发布**：网页（已上线）→ 微信群（md）→ 微信公众号（未来自动发布）。

## 1. 现状（Phase 0 ✅ 已完成）

- Claude Code plugin（asta-news）：sources 注册表（98+ 源，含 X KOL per-user 路由、Reddit RSS、RSSHub 本机部署）、fetch/dedup/probe/doctor/publish_site 脚本、daily-digest/setup/manage-sources skills。
- 单级 digest：抓取→去重→并行评分→editor 裁决→Readiness 多段新闻体改写。
- 数据产物在仓库：`site/data/<date>.json`（含精选+全部候选+摘要+链接）、`editions/<date>.md`（微信版）。去重"仓库即状态"。
- gazette 静态站（vanilla JS）+ GitHub Actions + Pages：**已上线 https://ylxmf2005.github.io/AstaNews/** 。
- 部署用 API URL+Key 跑 claude（非 OAuth），runner 墙外直连，60 天 prune。

## 2. 目标架构（模块化，工业级）

仓库即 monorepo，按职责分模块，配置全部独立成文件（方便网站控制）：

```
asta-news/                # Claude Code plugin（编排层：skills + 黑盒脚本）
  config/                 # ← 新增：模块化配置（网站可读写）
    sources/*.yaml        # 数据源注册表（已存在，迁入）
    tiers.yaml            # 多级筛选：完整/日报/群聊 的数量与门槛
    perspectives.yaml     # 多视角定义（受众、排序权重、改写语气）
    sharpness.yaml        # 犀利度档位
    rules.yaml            # 编辑规则（迁入）
    site.yaml             # 站点元信息、栏目
    search.yaml           # 检索配置（BM25/向量权重、模型）
  scripts/                # 抓取/去重/评分/改写/嵌入/检索/发布（模块化、单一职责）
  skills/                 # daily-digest / setup / manage-sources / (+ enrich-images, search)
services/                 # ← 新增：本地后端（控制台 + 检索 API，FastAPI）
  search/                 # 向量索引 + 混合检索
web/                      # ← 新增：React MPA（Next static export → Pages）
  替换现有 site/（site/ 暂留作 fallback，迁移后删）
data/ 或 site/data/       # 每日产物 JSON（schema v2）+ 向量索引
docs/                     # PRD/ROADMAP/ARCHITECTURE/设计稿
```

运行仍用 Claude Code（skills 编排 + Actions 触发），但代码是完整模块化工程，不是"只能在 claude 里跑"的脚本堆。

## 3. 关键设计

### 3.1 数据模型 v2（edition JSON）
向后兼容地扩展现有 schema：
```jsonc
{
  "date","weekday","headline","overview","stats",
  "tiers": {                      // 多级筛选
    "group":  [item...],          // ~5 精选（= 旧 selected）
    "daily":  [item...],          // ~20 日报
    "full":   [candidate...]      // 全部（= 旧 all_candidates，轻量字段）
  },
  "perspectives": {               // 多视角（对 daily/group 的重排+改写）
    "technical": {"order":[id...], "lede": "该视角导语"},
    "product":   {...}, "business": {...}, "research": {...}
  },
  "selected": [...],              // 保留：= tiers.group，旧前端/旧消费者兼容
  "all_candidates": [...]         // 保留兼容
}
```
每个 item 增加：`image`（{url, credit, source}）、`embedding_id`、`sharpness`（各档改写可选）、`perspective_notes`。

### 3.2 多级筛选（tiers.yaml）
```
full   : 全部候选（仅去重，不限量）
daily  : 目标 20（可配），门槛低于群聊，覆盖更多层与长尾
group  : 目标 5（上限 8），最严，微信群发
```
实现：评分一次，按分数/多样性分层切；daily 是 group 的超集语境。

### 3.3 两类 filter：视角（大）× 类别（小）
网站有**两个正交筛选维度**，可组合（再叠加级别 tier = 三维）：
- **视角（大分类）**：受众大镜头——全栈/技术/产品/商业/研究/具身。管"怎么排、给谁看、导语怎么框"，对候选**重排序**（软）。
- **类别（小分类）**：13 个 stack layer（model/eval/infra…）。管"只看哪一层"，对候选**硬筛**。
可组合如"技术视角 × 评测类别"。视角定义（perspectives.yaml），每个 = {受众画像, layer_boost 排序倾向, 导语}：
- `technical`：研究/工程师。偏 model/post-training/infra/eval，重方法与数字。
- `product`：产品/应用。偏 product/agent/devtool/maas，重能力边界与可用性。
- `business`：投资/商业。偏 business/funding/战略，借鉴橘鸦的商业视角。
- `research`：学术。偏 paper/eval，重新意与可复现。
- （可选）`infra-ops`：平台/运维。偏 serving/infra/成本。
视角不重新抓取，只对当天候选重排序 + 可选重写导语。

### 3.4 犀利度（sharpness.yaml）
- `neutral`：客观新闻体（默认，当前风格）。
- `sharp`：锐评，带判断与吐槽，点明"谁在画饼/谁动真格"。
- `deep`：深读，多段背景+技术拆解。
改写层按档位产出（默认 neutral；网站可切）。

### 3.5 检索（search.yaml + services/search）
- 本地 embedding 模型（fastembed/ollama，CPU 可跑），digest 时对每条 item 嵌入，存向量索引（sqlite-vec 或 lancedb，或 numpy+npz）。
- 混合检索：BM25（关键词，rank-bm25）+ 向量余弦，加权融合（RRF 或线性）。
- 入口：网站搜索页。静态模式用预构建索引 + 浏览器内 query 嵌入（transformers.js）或调本地 service；本地模式用 FastAPI。

### 3.6 配图（借鉴橘鸦；skill 教 how-to）
- 优先一手源的 og:image / twitter:image（WebFetch 抓 meta）；arXiv 取首图/构造预览；GitHub 取 social preview；HF 取模型卡图。
- 无图则可选生成占位（layer 主题色卡）。
- skill 段落明确"如何配图"：抓取顺序、版权标注、失败兜底。

### 3.7 网站（React MPA）
- 栈：Next.js（`output: export` 静态导出 → Pages 友好，file-based 路由 = 真多页，React 易维护）。或 Astro+React（备选）。**必须 React + MPA，非 SPA。**
- 页面：首页(今日日报) / `edition/[date]`(某期) / `item/[id]`(单条详情+相关) / `search` / `perspective/[p]` / `archive`(往期) / `about`。
- 静态模式（Pages，公开只读）+ 本地模式（连 services 后端，可触发/配置/搜索）。
- 视觉沿用并升级 gazette（橘鸦式配图 + 情报邸报排版）。

### 3.8 控制台 & 账号（终态，架构预留）
- services 后端暴露 API：列期/取期/触发 digest/读写 config/排程/搜索。
- 网站做控制台 UI。账号体系先不做（假设持有网站即可用），但 API 设计预留 auth 中间件位。

### 3.9 发布渠道
- 网页（✅）。微信群 md（✅）。微信公众号自动发布（未来；先研究橘鸦排版与配图，留接口）。

## 4. 执行 Backlog（按价值×今晚可行排序；循环每次取最高价值未完成项）

状态：⬜ 待办 / 🔵 进行中 / ✅ 完成

- ✅ **P0-DOC** 写本 ROADMAP（PO 总纲）
- ✅ **生产** 2026-06-13 首次端到端 v2 digest 跑通并上线(往期已 2 期)；publish_site 加 facts/links 归一容错
- ✅ **P0-CRON** 5am 北京定时任务已设（durable cron），进入持续迭代循环
- ✅ **P1-EMBED** 本地 embedding（fastembed multilingual-MiniLM，hf-mirror，离线 CPU）+ 向量索引 + 跨语言检索，`scripts/embed.py` 自测通过
- ✅ **P1-CONFIG** `asta-news/config/` 已建：tiers/perspectives/sharpness/site/search.yaml
- ✅ **P1-SCHEMA** v2 schema 固化进 skill，2026-06-13 首次端到端生产跑通(group/daily/full+视角+锐评+配图+向量)
- ✅ **P1-TIERS** 多级筛选固化并生产验证(06-13 真实跑出 group6/daily12/full134)
- ✅ **P1-WEB** React MPA（Next 15 静态导出，真多页：home/edition/archive/search/about）读 v2，gazette 美学，构建通过；部署中
- ✅ **P2-PERSP** 两类 filter 上线：视角(全栈/技术/产品/商业/研究/具身, 重排)×类别(13 layer, 硬筛)，网站可组合切换 + 视角导语
- 🔵 **P2-SEARCH** 关键词搜索 + 相关新闻(预计算近邻)已稳上线；语义搜索框(浏览器 transformers.js 同款模型嵌入 query×vectors.bin)已实现为渐进增强(graceful fallback 到关键词)，真机大概率可用，headless sandbox 加载不了 CDN 模块故未能本地验证——待真机确认/改自托管模型
- ✅ **P2-IMG** 精选 6/6 配 AI 信息图(arXiv 架构图/行为率图)+ daily og:image 兜底(11 张上线)+ enrich_images.py + images.md how-to + 卡片渲染；待续:提升 daily/arXiv 覆盖、防盗链兜底
- ✅ **P2-SHARP** 犀利度上线：中性/锐评 切换(网站控件)，今日 6 精选含 sharp 锐评变体，readiness.md 写明产出规范；深读档待加
- ✅ **P3-STUDY** 橘鸦研究完成(docs/study-juya.md)：发现我们 gazette 美学已天然对齐橘鸦；借鉴'今日概览编号列表'已应用到微信版 md；公众号发布路径(md2juya/md2wechat→微信API)已规划进 P3-WECHAT
- ✅ **P3-SELFCONTAIN** doctor 全绿(110 源/RSSHub/代理自探测)；setup skill 更新：X 用 grab_x_cookie.sh 自动取 cookie + per-user 路由开箱即用、embed 自包含(hf-mirror)、README 指向 web/ Next 流程
- 🔵 **P3-CONSOLE** services/ FastAPI 后端已建并验证：列期/取期/**服务端语义检索(跨语言)**/源概览/读写配置/触发抓取 + require_auth 鉴权钩子(预留账号)；待加排程端点 + web 控制台 UI(P3-WEBCTRL)
- 🔵 **P3-WEBCTRL** 网站 /console 页上线：静态站显引导，连后端则看状态/源、服务端语义检索、触发抓取、**编辑并保存配置(tiers/perspectives/sharpness/…)**；待加排程 UI
- ⬜ **P3-ACCT** 账号体系（API auth 预留 → 实现）
- 🔵 **分发** Atom 订阅 feed + **社交分享卡(OG/Twitter meta:首页+每条 item,带图)**——分享到微信群/推特有预览卡
- 🔵 **P3-WECHAT** md→公众号内联样式 HTML 转换器(publish_wechat.py,橘鸦风,≤1MB,实测渲染 OK)已成；微信 draft/publish API 接口已写好,gated 在 WECHAT_APPID/SECRET(等用户公众号凭证)；services 端点 /api/publish/wechat + 控制台「生成公众号 HTML」按钮已加(实测生成成功,发布等凭证)
- 🔵 **持续** 前端：favicon(轨道印记)+品牌 404 页 + 头条层级 + **item 详情页 + **往期 prev/next 顺序导航**；数据源 121（+TLDR AI/Ben's Bites/Ethan Mollick/Zvi/RunPod/Meta新闻RSS 等）（+The Decoder/MarkTechPost/Together/Google AI/philschmid/r-ML 等，不止 RSSHub）；前端人类视角打磨、文章质量、更多中文/商业/创意源待续

## 5. 循环工作准则（5am 起的自我迭代）

1. 先跑当日 digest 生产（产出新一期），再做改进。
2. 一次只推进 1-2 个 backlog 项到"可验证完成"，commit + push，更新本文件状态。
3. 每个改动都要自验证（脚本自测 / 截图 / 实时站点 curl）。
4. 优先级：能让"网站更综合、更好看、信息更全更易懂"的优先。
5. 预算/用量紧张时，先 commit 已完成的，写清下次从哪继续，再停。
6. 把自己当 PO+开发：想到合理功能就写进 backlog 再做，不必等人确认（非破坏性前提下）。

## 6. 研究参考
- 橘鸦（微信 AI 日报公众号）：易懂写法 + 商业新闻 + 配图。研究其结构与图文。
- Tim / day-day-arxiv（daily-arxiv GitHub Action + Pages 归档）：历史归档站形态。
- 已有研究产物在 `research/`，数据源验证报告与参考项目分析。
