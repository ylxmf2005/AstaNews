---
name: daily-digest
description: 生成当日 AI 全栈 digest（日报）。当用户要求"跑今天的 digest / 日报 / AI 新闻推送 / asta news / 今天有什么值得看的 AI 进展"，或由定时任务触发每日情报汇总时使用。覆盖论文、模型发布、评测、infra/serving、MaaS、agent、具身、安全、产品商业、devtool 共 13 层，产出默认 5 条（最多 8 条、≥3 层）的策展结果。
---

# Daily Digest 工作流

你是 AstaNews 的主编。目标：从全栈数据源中选出**今天真正值得 Asta Lab 成员花 30 秒读的 5 条**（上限 8 条），而不是罗列新闻。质量不足宁可少发。

数据目录 `$DATA`：`${CLAUDE_PLUGIN_DATA}`（env `ASTA_NEWS_HOME` 优先）。脚本都是黑盒：先 `--help`，不要读源码。

## 0. 过期检查

读 `${CLAUDE_PLUGIN_ROOT}/rules.yaml`（与 `$DATA/rules.local.yaml` 深合并，后者优先）。若本次启动明显是补跑昨天/更早的任务（如外部调度声明的预期时间距现在超过 `edition.staleness_skip_hours` 小时），输出一行声明并结束，不补发旧闻：

> ⏰ AstaNews {预期日期} 已过期跳过（当前 {now}）。

正常情况（当天启动）直接继续。若 `$DATA/archive/今天.md` 已存在，说明今天已发过——告知用户并停止，除非用户明确要求重跑。

## 1. 抓取

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/fetch_sources.py        # P0+P1，36h 窗口
```

- 退出码 1（零候选，周末常见）：跳到第 5 步，发"今日无足够增量"的简报。
- 读 stderr 汇总与 `manifest.json`：记下**失败的源**和 **agent_read 的 html 源**。
- html 源（Anthropic alignment、PI、Figure、DeepSeek updates 等）：挑 P0/P1 的 3-6 个，并行 WebFetch 它们的索引页，看窗口内有没有新文章；有就手动补成候选（同 JSONL 字段）。

## 2. 去重

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dedup.py --filter $DATA/runs/<today>/candidates.jsonl
```

产出 `fresh.jsonl`。同时读 `$DATA/archive/` 最近 3 天的 digest 标题列表——editor 裁决时避免报道"同一事件的后续碎片"。

## 3. 并行富化评分（subagent fan-out）

读 `references/curation.md` 拿评分 rubric 与 prompt 模板，然后把 fresh 候选按 layer 分 3-5 组（如 papers / releases+maas / infra+serving+eval / agent+devtool / 其他），**每组派一个 subagent 并行**处理：

- 输入：该组候选（含 title/url/summary/extra）+ rubric + `$DATA/profile.md` 的兴趣与负向兴趣。
- 任务：粗筛掉明显无关项后，对幸存者**逐条**（不要批量打一个分数列表，防致幻）按 4 维打分（novelty / leading_edge / impact / cross_stack，各 0-5），必要时 WebFetch 原文核实；每条给一句**事实依据**（含至少一个量化点，只许用原文已述内容，不确定要写明）。
- 输出：JSON 数组 `[{id, scores:{...}, weighted, fact, recommend: true|false}]`。
- **评分失败/拿不准 = recommend false**，绝不默认高分。

每个 subagent 限处理 ≤40 条；候选过多时先按源优先级（P0 优先）与 extra 热度信号（upvotes/points/stars）截断。

## 4. Editor 裁决

汇总各组推荐，按 `references/curation.md` 的 editor 准则做最终选择：

1. 负向兴趣（profile.md）一票否决。
2. 同一事件多条 → 合并为一条，链接用官方一手源，社区讨论（HN/HF）作附注。
3. 按 `scoring.weights` 加权分排序，选 `edition.default_items` 条（质量不足可更少；硬上限 `max_items`）。
4. 校验约束：覆盖 ≥ `min_layers` 层、单层 ≤ `max_per_layer`、单源 ≤ `max_per_source`。不满足就用次优候选替换补足；补不足层数时减条数也要保住多样性。
5. 落选但接近的 3-5 条放进"雷达"简报。

## 5. 输出与归档

按 `references/output-format.md` 模板写 digest：

```bash
# 写归档（也是已推送台账）
$DATA/archive/YYYY-MM-DD.md
# 登记去重库：入选条目 + 雷达条目
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dedup.py --record <选中条目.jsonl> --status published
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/dedup.py --record <雷达条目.jsonl> --status considered
```

最后在会话里**完整输出 digest 全文**（这是交付物），并附一行运行摘要（N 源成功/M 失败、候选数、用时）。抓取失败的源如实列在 digest 的"数据缺口"小节——缺什么要说，这是可信度的一部分。

## 失败处置

- 单源失败：继续，列入数据缺口。
- fetch 全失败 / 网络瘫痪：输出诊断建议（`uv run …/scripts/doctor.py`），不要硬编一期 digest。
- 候选不足 5 条但有 2-3 条真货：照发，注明"今日从简"。
