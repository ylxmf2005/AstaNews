# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "feedparser", "pyyaml"]
# ///
"""asta-news 单源验证：可达性 + 可解析 + 新鲜度

加源 PR 前必须跑通本脚本。新鲜度阈值按 freq：daily=4 天（容周末）、weekly=21 天、monthly=75 天。

用法:
  probe_source.py --id arxiv-cs-cl                # 验证注册表中的源
  probe_source.py --url https://... --type rss    # 验证临时 URL
  probe_source.py --all [--include-disabled]      # 验证全部已启用源
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sources as F  # noqa: E402  复用抓取/解析逻辑

FRESH_DAYS = {"daily": 4, "weekly": 21, "monthly": 75}


def probe(source: dict) -> tuple[bool, str]:
    if source["type"] == "html":
        try:
            text = F.fetch(F.expand_env(source["url"]), source)
        except Exception as exc:
            return False, f"不可达: {exc}"
        if len(text) < 500:
            return False, f"页面过短({len(text)}B)，疑似空壳/软404"
        return True, f"可达 (html, {len(text)}B)；html 源由策展 agent 阅读，无条目级校验"
    # 用超大窗口抓全量，再单独做新鲜度判断
    status, items, detail = F.fetch_source(source, datetime.now(timezone.utc) - timedelta(days=3650))
    if status == "skipped":
        return False, f"跳过: {detail}"
    if status == "error":
        return False, detail
    if not items:
        if source.get("parser") in ("openrouter_models", "mcp_registry", "evalplus", "aider_yaml"):
            return True, "diff 型源：首跑建立快照，0 条属正常"
        return False, "可达但解析出 0 条目"
    dated = [i["published"] for i in items if i["published"]]
    if not dated:
        return True, f"{len(items)} 条目（无日期字段，跳过新鲜度检查）"
    newest = max(dated)
    age = datetime.now(timezone.utc) - datetime.fromisoformat(newest)
    limit = FRESH_DAYS.get(source.get("freq", "daily"), 4)
    if age > timedelta(days=limit):
        return False, f"STALE: 最新条目 {newest[:10]}，已 {age.days} 天无更新（freq={source.get('freq')} 阈值 {limit} 天）"
    return True, f"{len(items)} 条目，最新 {newest[:10]}（{age.days} 天前），新鲜度 OK"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", help="注册表中的 source id")
    g.add_argument("--url", help="临时 URL")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--type", default="rss", help="--url 时的 type")
    ap.add_argument("--parser", help="--url 且 type=json 时的 parser")
    ap.add_argument("--needs-proxy", action="store_true")
    ap.add_argument("--include-disabled", action="store_true")
    args = ap.parse_args()

    registry = {s["id"]: s for s in F.load_registry(F.PLUGIN_ROOT / "sources")}
    if args.url:
        targets = [{"id": "adhoc", "name": "adhoc", "layers": ["model"], "type": args.type,
                    "url": args.url, "parser": args.parser, "needs_proxy": args.needs_proxy,
                    "freq": "daily"}]
    elif args.id:
        if args.id not in registry:
            print(f"未找到 source id: {args.id}", file=sys.stderr)
            return 2
        targets = [registry[args.id]]
    else:
        targets = [s for s in registry.values()
                   if s.get("enabled", True) or args.include_disabled]

    failed = 0
    for s in targets:
        ok, msg = probe(s)
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {s['id']:30s} {msg}")
        failed += (not ok)
    if len(targets) > 1:
        print(f"\n{len(targets)-failed}/{len(targets)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
