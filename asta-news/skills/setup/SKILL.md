---
name: setup
description: asta-news 初始化与健康检查。安装 plugin 后第一次使用、digest 报数据缺口、需要部署/修复 RSSHub、配置代理或 X/Twitter 源时使用。涵盖数据目录创建、网络代理探测、可选 RSSHub 部署（X/Anthropic/量子位/GitHub Trending）、全链路体检。幂等，可反复运行。
---

# Setup：一次 init，长期自治

按顺序执行，每步幂等。脚本是黑盒，先 `--help`。

## 前置

- [uv](https://docs.astral.sh/uv/)（必需，脚本零安装运行的前提）
- Docker（仅可选步骤 3 需要）

## 1. 数据目录 + 体检

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py --fix
```

逐项解读结果给用户。`--fix` 会创建 `~/.claude/plugins/data/asta-news/`（env `ASTA_NEWS_HOME` 可改位置）并拷贝 `profile.md` / `rules.local.yaml` / `sources.local.yaml` 模板（不覆盖已有文件）。

## 2. 代理（被墙源解锁）

doctor 会探测系统代理并验证能否访问 huggingface.co。若它给出了建议值，帮用户持久化：

```bash
# 写进 shell profile，或 Claude Code settings.json 的 env 段
export ASTA_PROXY=http://127.0.0.1:7897   # 以 doctor 探测结果为准
```

没有可用代理也能跑——`needs_proxy` 的源（HF Daily Papers、Gemini changelog、Mistral 等）会被跳过并如实列入 digest 数据缺口。HF Daily Papers 另有 RSSHub 备路（见 sources/papers.yaml 的 hf-daily-papers-rsshub）。

## 3.（可选）部署 RSSHub

解锁的源：X/Twitter List、Anthropic news/engineering、量子位、GitHub Trending、HF Daily Papers 备路。不需要这些可跳过。

```bash
mkdir -p $DATA/rsshub && cd $DATA/rsshub
cp ${CLAUDE_PLUGIN_ROOT}/skills/setup/assets/docker-compose.rsshub.yml docker-compose.yml
# 创建 .env（凭证只进 .env，不进任何会提交的文件）：
#   TWITTER_AUTH_TOKEN=<x.com cookie 的 auth_token 值>   ← X 源需要
#   GITHUB_ACCESS_TOKEN=<无 scope 的真实 PAT>            ← GitHub Trending 路由需要
docker compose up -d
curl -s http://127.0.0.1:1200/healthz   # 期望输出: ok
```

`restart: always` 保证开机自启、崩溃自拉——init 之后无需再部署。compose 文件内有取 cookie 的具体步骤注释。

## 4.（可选）X/Twitter List

1. 在 X 上建一个 List 收 AI KOL（建议名单见 `sources/community-business.yaml` 中 `x-ai-list` 的 notes），拿到 List id（URL `x.com/i/lists/<id>` 中的数字）。
2. `export ASTA_X_LIST_ID=<id>`（与 ASTA_PROXY 同样方式持久化）。
3. 在 `$DATA/sources.local.yaml` 覆盖启用：

```yaml
sources:
  - id: x-ai-list
    name: X/Twitter AI List (RSSHub)
    layers: [model, agent, product]
    type: rsshub
    url: /twitter/list/${ASTA_X_LIST_ID}
    priority: P0
    requires_env: [TWITTER_AUTH_TOKEN, ASTA_X_LIST_ID]
    enabled: true
    freq: daily
    verified: 2026-06-12
```

## 5. 终检

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py
uv run ${CLAUDE_PLUGIN_ROOT}/scripts/fetch_sources.py --only arxiv-cs-cl,hn-frontpage,openai-news --out /tmp/asta-init-test.jsonl
```

两者通过（fetch 退出码 0 且有候选）即初始化完成。告诉用户：日常只需运行 `/asta-news:daily-digest`。

## Troubleshooting

| 症状 | 处置 |
|---|---|
| needs_proxy 源全跳过 | 步骤 2；确认 `curl -x $ASTA_PROXY https://huggingface.co/api/daily_papers?limit=1` 返回 200 |
| rsshub 源全失败 | `docker ps` 看容器、`curl 127.0.0.1:1200/healthz`；twitter 路由 503 = cookie 失效，换新 auth_token 重启容器 |
| GitHub trending 路由 503 ConfigNotFoundError | PAT 未配或是假的（GraphQL 401），用真实无 scope PAT |
| arXiv 周末零候选 | 正常：arXiv RSS 仅工作日重建 |
| DeepMind feed 偶发超时 | 已知其服务器慢，重试即可 |
