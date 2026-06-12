# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "feedparser", "pyyaml"]
# ///
"""asta-news 抓取器：source 注册表 -> candidates.jsonl

并发抓取所有启用的源，按 type/parser 解析为统一候选格式，best-effort：
单源失败只记警告，不影响整体。type=html 的源不在此抓取（由策展 agent 按需阅读），
会列入 --manifest 输出供 agent 参考。

候选行格式:
  {"id","source","layers","title","url","published","summary","extra"}

退出码: 0=有新候选  1=零候选  2=配置错误
"""
import argparse
import concurrent.futures as cf
import hashlib
import html
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import yaml

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
UA = "AstaNews/0.1 (+https://github.com/asta-lab/AstaNews)"
TIMEOUT = 20


def data_dir() -> Path:
    for env in ("ASTA_NEWS_HOME", "CLAUDE_PLUGIN_DATA"):
        if os.environ.get(env):
            return Path(os.environ[env]).expanduser()
    return Path.home() / ".claude" / "plugins" / "data" / "asta-news"


def load_registry(sources_dir: Path) -> list[dict]:
    by_id: dict[str, dict] = {}
    files = sorted(sources_dir.glob("*.yaml"))
    local = data_dir() / "sources.local.yaml"
    if local.exists():
        files.append(local)
    for f in files:
        doc = yaml.safe_load(f.read_text()) or {}
        for s in doc.get("sources", []):
            by_id[s["id"]] = s  # local 同 id 覆盖默认
    return list(by_id.values())


def expand_env(url: str) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), url)


def strip_html(text: str, limit: int = 1200) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit]


def to_iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):  # unix ts
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    if isinstance(value, time.struct_time):
        return datetime(*value[:6], tzinfo=timezone.utc).isoformat()
    if isinstance(value, str):
        for fmt in (None, "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                if fmt is None:
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                else:
                    dt = datetime.strptime(value, fmt)
                if dt.tzinfo is None:  # 纯日期/无时区一律按 UTC，保证下游可与 aware 时间比较
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                continue
    return None


def within(published: str | None, cutoff: datetime) -> bool:
    if published is None:
        return True  # 无日期的条目放行，由策展层判断
    try:
        dt = datetime.fromisoformat(published)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= cutoff
    except ValueError:
        return True


# 只认 ASTA_PROXY：环境可能注入不可靠的 HTTP(S)_PROXY（如 IDE 内部代理），必须忽略
SESSION = requests.Session()
SESSION.trust_env = False


def fetch(url: str, source: dict, as_json: bool = False):
    proxy = os.environ.get("ASTA_PROXY")
    proxied = {"http": proxy, "https": proxy} if proxy else None
    if source.get("needs_proxy"):
        if not proxy:
            raise RuntimeError("needs_proxy 但未设置 ASTA_PROXY")
        attempts = [proxied, proxied]
    else:
        # 直连优先；失败且有代理时走代理兜底（GFW 环境下 github.com 等直连时好时坏）
        attempts = [None, proxied, None] if proxied else [None, None]
    headers = {"User-Agent": UA, "Accept": "*/*"}
    # 声明式鉴权头：headers_env: {Header-Name: ENV_VAR}
    for hname, env in (source.get("headers_env") or {}).items():
        if os.environ.get(env):
            headers[hname] = os.environ[env]
    if "api.github.com" in url and os.environ.get("GITHUB_ACCESS_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_ACCESS_TOKEN']}"
    last_exc: Exception = RuntimeError("unreachable")
    for i, proxies in enumerate(attempts):
        try:
            r = SESSION.get(url, timeout=TIMEOUT, proxies=proxies, headers=headers)
            r.raise_for_status()
            return r.json() if as_json else r.text
        except Exception as exc:
            last_exc = exc
            if i < len(attempts) - 1:
                time.sleep(1)
    raise last_exc


def mk(source: dict, title: str, url: str, published=None, summary: str = "", extra: dict | None = None) -> dict:
    # url+title 联合哈希：diff 型源（榜单/registry）的多个条目共享同一 URL，只哈希 URL 会互相碰撞
    key = hashlib.sha1(f"{url}|{title}".encode()).hexdigest()[:12]
    return {
        "id": f"{source['id']}:{key}",
        "source": source["id"],
        "layers": source["layers"],
        "title": strip_html(title, 300),
        "url": url,
        "published": to_iso(published),
        "summary": strip_html(summary),
        "extra": extra or {},
    }


# ---------- feed 类 ----------

def parse_feed(source: dict, text: str) -> list[dict]:
    fp = feedparser.parse(io.BytesIO(text.encode("utf-8", "ignore")))
    exclude = source.get("exclude_pattern")
    kept = []
    for e in fp.entries:  # 先过滤再截断：arXiv 大日子 new>60 条时不能让 replace/cross 占掉名额
        if e.get("arxiv_announce_type") not in (None, "new"):
            continue  # arXiv replace/cross 不算新条目
        if exclude and re.search(exclude, e.get("title", "")):
            continue
        kept.append(e)
    return [mk(source, e.get("title", ""), e.get("link", ""),
               e.get("published_parsed") or e.get("updated_parsed"), e.get("summary", ""))
            for e in kept[:80]]


# ---------- json parsers（全部防御式：结构不符 -> 空列表而非崩溃）----------

def p_hf_daily_papers(source, data):
    # publishedAt 是论文提交日（常 >36h，会被时间窗整批误杀）；上榜本身就是"今天"的事件，
    # 统一盖当前时间戳，跨天重复交给 seen.db 去重
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for it in data if isinstance(data, list) else []:
        p = it.get("paper", {})
        out.append(mk(source, p.get("title", ""), f"https://huggingface.co/papers/{p.get('id','')}",
                      now, p.get("summary", ""),
                      {"upvotes": p.get("upvotes"), "arxiv_id": p.get("id"),
                       "paper_date": it.get("publishedAt")}))
    return out


def p_hf_hub_list(source, data):
    # 模型页在 hf.co/{id}，只有数据集带 /datasets/ 前缀（/models/{id} 是 404）
    prefix = "datasets/" if "/datasets" in source["url"] else ""
    out = []
    for it in data if isinstance(data, list) else []:
        rid = it.get("id", "")
        out.append(mk(source, rid, f"https://huggingface.co/{prefix}{rid}",
                      it.get("createdAt") or it.get("lastModified"), "",
                      {"likes": it.get("likes"), "downloads": it.get("downloads")}))
    return out


def p_hn_algolia(source, data):
    out = []
    for h in data.get("hits", []):
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        out.append(mk(source, h.get("title", ""), url, h.get("created_at"), "",
                      {"points": h.get("points"), "comments": h.get("num_comments"),
                       "hn": f"https://news.ycombinator.com/item?id={h.get('objectID')}"}))
    return out


def p_oss_insight(source, data):
    rows = (data.get("data") or {}).get("rows", [])
    out = []
    for r in rows[:30]:
        name = r.get("repo_name", "")
        out.append(mk(source, f"{name} — {r.get('description') or ''}",
                      f"https://github.com/{name}", None, "",
                      {"stars": r.get("stars"), "forks": r.get("forks")}))
    return out


def p_github_org_repos(source, data):
    out = []
    for r in data if isinstance(data, list) else []:
        ts = r.get("pushed_at") if "sort=pushed" in source["url"] else r.get("created_at")
        out.append(mk(source, f"{r.get('full_name','')} — {r.get('description') or ''}",
                      r.get("html_url", ""), ts, "",
                      {"stars": r.get("stargazers_count")}))
    return out


def p_reddit_top(source, data):
    out = []
    for c in (data.get("data") or {}).get("children", []):
        d = c.get("data", {})
        out.append(mk(source, d.get("title", ""),
                      "https://www.reddit.com" + d.get("permalink", ""),
                      d.get("created_utc"), "", {"score": d.get("score")}))
    return out


def p_kaggle_datasets(source, data):
    out = []
    for d in data if isinstance(data, list) else []:
        ref = d.get("ref") or d.get("id", "")
        out.append(mk(source, d.get("title", str(ref)), f"https://www.kaggle.com/datasets/{ref}",
                      d.get("lastUpdated"), d.get("subtitle", "")))
    return out


def p_swebench(source, data):
    """diff 型：榜单条目的 date 字段严重滞后于实际合并时间，不能按时间窗筛，
    只报'相对上次快照新出现的条目'。"""
    entries = {}
    boards = data.get("leaderboards", []) if isinstance(data, dict) else []
    for lb in boards:
        for e in lb.get("results", []) or []:
            name = e.get("name") or e.get("model")
            if not name:
                continue
            score = e.get("resolved") or e.get("score")
            entries[f"{lb.get('name','?')}:{name}"] = str(score)
    new_keys = _diff_state(source, entries)
    now = datetime.now(timezone.utc).isoformat()
    return [mk(source, f"SWE-bench [{k.split(':',1)[0]}] new entry: {k.split(':',1)[1]} ({entries[k]}%)",
               "https://www.swebench.com/", now) for k in new_keys[:20]]


# probe/doctor 等只读场景置 True：算 diff 但不推进快照，避免验证工具偷偷消费当天的增量
DIFF_DRY_RUN = False


def _diff_state(source, current: dict[str, str]) -> list[str]:
    """与上次快照对比，返回新增 key；快照存 data_dir/runs/state/<id>.json"""
    if not current:
        # 上游 200 但空体（故障/改版）：宁可报错也不能用空快照顶掉好快照，
        # 否则恢复后全量条目都会被当成"新增"刷屏
        raise RuntimeError("payload 为空，拒绝更新 diff 快照")
    state_file = data_dir() / "runs" / "state" / f"{source['id']}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    prev = None
    if state_file.exists():
        try:
            prev = json.loads(state_file.read_text())
        except (json.JSONDecodeError, OSError):
            prev = None  # 快照损坏按首跑处理（自愈），下面会原子重写
    if not DIFF_DRY_RUN:
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=0))
        os.replace(tmp, state_file)
    if prev is None:
        return []  # 首跑只建快照不报，避免把全量当新闻
    return [k for k in current if k not in prev]


def p_openrouter_models(source, data):
    models = {m["id"]: m.get("name", m["id"]) for m in data.get("data", []) if m.get("id")}
    new_ids = _diff_state(source, models)
    return [mk(source, f"New on OpenRouter: {models[i]}",
               f"https://openrouter.ai/models/{i}", datetime.now(timezone.utc).isoformat())
            for i in new_ids]


def p_mcp_registry(source, data):
    """配合 URL 里的 ?updated_since={window_start_iso}：registry 返回的就是窗口内
    新/更新的 server（按名字排序的全量 diff 法会被字母窗口截断，不可用）。"""
    out = []
    for s in data.get("servers", [])[:15]:
        body = s.get("server", s)
        name = body.get("name", "")
        repo = (body.get("repository") or {}).get("url") or "https://registry.modelcontextprotocol.io/"
        meta = (s.get("_meta") or {}).get("io.modelcontextprotocol.registry/official", {})
        out.append(mk(source, f"MCP registry: {name} — {body.get('description','')[:160]}",
                      repo, meta.get("updatedAt"), "",
                      {"version": body.get("version")}))
    return out


def p_github_releases_api(source, data):
    """REST releases API：能拿 prerelease 标志，适合 atom 窗口被 alpha/rc 刷满的仓库"""
    out = []
    for r in data if isinstance(data, list) else []:
        if r.get("prerelease") or r.get("draft"):
            continue
        out.append(mk(source, f"{r.get('name') or r.get('tag_name','')}",
                      r.get("html_url", ""), r.get("published_at"),
                      (r.get("body") or "")[:600]))
    return out


def p_evalplus(source, data):
    models = {k: str(v)[:100] for k, v in data.items()} if isinstance(data, dict) else {}
    new_keys = _diff_state(source, models)
    return [mk(source, f"EvalPlus new model: {k}", "https://evalplus.github.io/leaderboard.html",
               datetime.now(timezone.utc).isoformat()) for k in new_keys[:10]]


def p_aider_yaml(source, text):
    rows = yaml.safe_load(text) or []
    models = {str(r.get("model", "")): str(r.get("pass_rate_2", r.get("pass_rate_1", "")))
              for r in rows if isinstance(r, dict)}
    new_keys = _diff_state(source, models)
    return [mk(source, f"Aider polyglot new entry: {k} ({models[k]}%)",
               "https://aider.chat/docs/leaderboards/", datetime.now(timezone.utc).isoformat())
            for k in new_keys[:10]]


def p_generic(source, data):
    return [mk(source, json.dumps(data)[:200], source["url"], None)]


PARSERS = {
    "hf_daily_papers": p_hf_daily_papers, "hf_hub_list": p_hf_hub_list,
    "hn_algolia": p_hn_algolia, "oss_insight": p_oss_insight,
    "github_org_repos": p_github_org_repos, "reddit_top": p_reddit_top,
    "kaggle_datasets": p_kaggle_datasets, "swebench": p_swebench,
    "openrouter_models": p_openrouter_models, "mcp_registry": p_mcp_registry,
    "evalplus": p_evalplus, "aider_yaml": None,  # 文本型，fetch_source 特判
    "github_releases_api": p_github_releases_api, "generic": p_generic,
}
# diff 型 parser：与本地快照对比报增量，首跑 0 条属正常（probe/doctor 据此判断）
DIFF_PARSERS = {"openrouter_models", "evalplus", "aider_yaml", "swebench"}


def fetch_source(source: dict, cutoff: datetime) -> tuple[str, list[dict], str]:
    """returns (status, items, detail)"""
    stype = source["type"]
    missing = [e for e in source.get("requires_env", []) if not os.environ.get(e)]
    if missing:
        return ("skipped", [], f"缺 env: {','.join(missing)}")
    url = expand_env(source["url"]).replace("{window_start_iso}",
                                            cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if stype == "html":
        return ("agent_read", [], url)
    if stype == "rsshub":
        base = os.environ.get("ASTA_RSSHUB", "http://127.0.0.1:1200")
        url = base.rstrip("/") + url
    try:
        if stype in ("rss", "atom", "github-releases", "rsshub"):
            items = parse_feed(source, fetch(url, source))
        elif stype == "json":
            parser = source.get("parser", "generic")
            if parser == "aider_yaml":
                items = p_aider_yaml(source, fetch(url, source))
            else:
                items = PARSERS[parser](source, fetch(url, source, as_json=True))
        else:
            return ("error", [], f"未知 type {stype}")
    except Exception as exc:  # best-effort：单源失败不影响整体
        return ("error", [], f"{type(exc).__name__}: {exc}"[:200])
    fresh = [i for i in items if within(i["published"], cutoff)]
    return ("ok", fresh, f"{len(fresh)}/{len(items)} 条在窗口内")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="可用 parser（type=json 源的必填字段）: " + ", ".join(sorted(PARSERS))
               + f"\n其中 diff 型（与本地快照比增量，首跑 0 条属正常）: {', '.join(sorted(DIFF_PARSERS))}, mcp_registry 走 URL 的 updated_since 参数")
    ap.add_argument("--sources-dir", default=str(PLUGIN_ROOT / "sources"))
    ap.add_argument("--only", help="逗号分隔 source id")
    ap.add_argument("--layers", help="逗号分隔 layer 过滤")
    ap.add_argument("--priority", default="P0,P1", help="默认 P0,P1；填 P0,P1,P2 取全部")
    ap.add_argument("--include-disabled", action="store_true")
    ap.add_argument("--window-hours", type=int, default=36)
    ap.add_argument("--out", help="输出 jsonl 路径；默认 data_dir/runs/<date>/candidates.jsonl")
    ap.add_argument("--manifest", help="抓取结果清单 json（含 agent_read 源）；默认同目录 manifest.json")
    args = ap.parse_args()

    sources = load_registry(Path(args.sources_dir))
    if not sources:
        print("配置错误：注册表为空", file=sys.stderr)
        return 2
    prios = set(args.priority.split(","))
    only = set(args.only.split(",")) if args.only else None
    layers = set(args.layers.split(",")) if args.layers else None
    selected = []
    for s in sources:
        if only and s["id"] not in only:
            continue
        if only is None:
            if not s.get("enabled", True) and not args.include_disabled:
                continue
            if s.get("priority") not in prios:
                continue
            if layers and not (set(s["layers"]) & layers):
                continue
        selected.append(s)
    if not selected:
        print("配置错误：筛选后无源", file=sys.stderr)
        return 2

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.window_hours)
    run_dir = data_dir() / "runs" / datetime.now().strftime("%Y-%m-%d")
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else run_dir / "candidates.jsonl"
    manifest_path = Path(args.manifest) if args.manifest else out_path.parent / "manifest.json"

    results, all_items = {}, []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_source, s, cutoff): s for s in selected}
        for fut in cf.as_completed(futs):
            s = futs[fut]
            status, items, detail = fut.result()
            results[s["id"]] = {"status": status, "count": len(items), "detail": detail,
                                "priority": s.get("priority"), "layers": s["layers"],
                                "url": expand_env(s["url"]), "name": s["name"]}
            all_items.extend(items)

    # (url, title) 联合判重：diff 型源多个条目共享 URL，不能只按 URL 收敛
    seen_keys = set()
    deduped = []
    for it in sorted(all_items, key=lambda x: x["published"] or "", reverse=True):
        key = (it["url"], it["title"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(it)

    with out_path.open("w") as f:
        for it in deduped:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    manifest_path.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "window_hours": args.window_hours, "candidates": len(deduped),
        "sources": results,
    }, ensure_ascii=False, indent=1))

    ok = sum(1 for r in results.values() if r["status"] == "ok")
    err = {k: r for k, r in results.items() if r["status"] == "error"}
    skipped = {k: r["detail"] for k, r in results.items() if r["status"] == "skipped"}
    agent_read = [k for k, r in results.items() if r["status"] == "agent_read"]
    print(f"== fetch 完成: {len(deduped)} 候选 | {ok}/{len(selected)} 源成功 ==", file=sys.stderr)
    for k, r in sorted(results.items(), key=lambda kv: -kv[1]["count"]):
        if r["status"] == "ok" and r["count"]:
            print(f"  {k:28s} {r['count']:4d}  {r['detail']}", file=sys.stderr)
    if agent_read:
        print(f"  [agent 直读 html 源] {', '.join(agent_read)}", file=sys.stderr)
    for k, d in skipped.items():
        print(f"  [跳过] {k}: {d}", file=sys.stderr)
    for k, r in err.items():
        print(f"  [失败] {k}: {r['detail']}", file=sys.stderr)
    print(f"candidates -> {out_path}\nmanifest   -> {manifest_path}", file=sys.stderr)
    return 0 if deduped else 1


if __name__ == "__main__":
    sys.exit(main())
