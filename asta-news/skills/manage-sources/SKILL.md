---
name: manage-sources
description: 管理 asta-news 的数据源与编辑规则。当用户要"加一个源 / 添加订阅 / 关注某个博客或仓库 / 不想再看某类内容 / 屏蔽某个源 / 调整 digest 条数或口味 / 测一遍源还活着吗 / 怎么给 AstaNews 贡献源"时使用。
---

# 管理数据源与规则

数据目录 `$DATA` = `${CLAUDE_PLUGIN_DATA}`（env `ASTA_NEWS_HOME` 优先）。先读 `${CLAUDE_PLUGIN_ROOT}/sources/_schema.md` 了解 schema 与已知坑（加源前必查"已知坑"表，别掉进 Papers with Code / stale feed 这类坑）。

## 加源

1. 问清/推断：URL、类型（有 RSS 吗？GitHub 仓库就用 `releases.atom`；JS SPA 找它的 API 或 GitHub org）、属于哪 1-3 个 layer、P 几。
2. **先验证再写入**：

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/probe_source.py --url <url> --type rss
```

   PASS（可达 + 有条目 + 新鲜）才继续；STALE 的 feed 帮用户找替代（看 _schema.md 坑表的模式：去 GitHub org、找 newsletter 子域、用 RSSHub 路由）。
3. 按 schema 写入 `$DATA/sources.local.yaml` 的 `sources:` 列表，`verified` 填今天。
4. 跑 `uv run ${CLAUDE_PLUGIN_ROOT}/scripts/fetch_sources.py --only <新id>` 确认端到端出条目。
5. 提醒：这个源对所有人有价值的话，建议向 AstaNews 仓库提 PR 把它加进 `sources/*.yaml`（带 probe 通过截图/输出），让全 Lab 受益。

## 禁源 / 删源

在 `sources.local.yaml` 写同 `id` 条目并 `enabled: false`（本地覆盖默认表，不用改 plugin 文件）。用户说"不想看 X 类内容"而非具体源时，改的是画像不是源——见下。

## 调规则

- 条数/层数/权重/语言：写 `$DATA/rules.local.yaml`（只写要改的键，深合并）。
- 兴趣与负向兴趣、voice：编辑 `$DATA/profile.md` 人写区（`ASTA:STATS` 标记之间的机器区不要动）。
- 全局默认值的修改（影响所有人）：改 plugin 的 `rules.yaml` 走 PR。

## 体检全部源

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/probe_source.py --all
```

把 FAIL 的源整理成表（源 / 原因 / 建议处置：修 URL、找替代、暂时 disable），经用户确认后落实。STALE 是最常见死法——feed 还 200 但内容停更，处置方式参考 _schema.md 坑表。
