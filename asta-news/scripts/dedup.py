# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""asta-news 去重库：基于 SQLite 的 seen-items 过滤与登记

两层判重：① URL 规范化精确匹配（去 tracking 参数/www/arXiv 版本号、强制 https）
② 模糊标题匹配（difflib ratio >= 阈值，滑窗内）。
失败开放：库异常时警告并放行全部候选——宁可重复，不可漏报。

用法:
  dedup.py --filter candidates.jsonl [--out fresh.jsonl]   # 输出未见过的候选
  dedup.py --record items.jsonl --status published          # 登记（published|considered）
  dedup.py --stats                                          # 库统计
  dedup.py --self-test                                      # 自检
"""
import argparse
import difflib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
KEEP_PARAMS = {"id", "v"}  # news.ycombinator.com/item?id= 、youtube watch?v= 等承载身份的参数


def data_dir() -> Path:
    for env in ("ASTA_NEWS_HOME", "CLAUDE_PLUGIN_DATA"):
        if os.environ.get(env):
            return Path(os.environ[env]).expanduser()
    return Path.home() / ".claude" / "plugins" / "data" / "asta-news"


def load_rules() -> dict:
    rules = yaml.safe_load((PLUGIN_ROOT / "rules.yaml").read_text())
    local = data_dir() / "rules.local.yaml"
    if local.exists():
        for k, v in (yaml.safe_load(local.read_text()) or {}).items():
            if isinstance(v, dict) and isinstance(rules.get(k), dict):
                rules[k].update(v)
            else:
                rules[k] = v
    return rules


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parts.path)
    path = re.sub(r"(/abs/\d{4}\.\d{4,5})v\d+$", r"\1", path)  # arXiv 版本号
    params = [(k, v) for k, v in parse_qsl(parts.query)
              if k in KEEP_PARAMS and not k.startswith("utm_")]
    return urlunsplit(("https", host, path, urlencode(params), ""))


def open_db() -> sqlite3.Connection:
    db_path = data_dir() / "seen.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE IF NOT EXISTS seen(
        id TEXT PRIMARY KEY, url_norm TEXT, title TEXT, source TEXT,
        status TEXT, first_seen TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_url ON seen(url_norm)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_seen ON seen(first_seen)")
    return conn


def recent_titles(conn, window_days: int) -> list[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    return [r[0] for r in conn.execute(
        "SELECT title FROM seen WHERE first_seen >= ?", (cutoff,))]


def is_dup(item: dict, conn, titles: list[str], window_days: int, threshold: float) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    row = conn.execute(
        "SELECT 1 FROM seen WHERE url_norm=? AND first_seen>=? LIMIT 1",
        (normalize_url(item["url"]), cutoff)).fetchone()
    if row:
        return True
    t = (item.get("title") or "").lower()
    if len(t) >= 20:  # 太短的标题模糊匹配误伤率高
        for known in titles:
            if difflib.SequenceMatcher(None, t, known.lower()).ratio() >= threshold:
                return True
    return False


def cmd_filter(args, rules) -> int:
    items = [json.loads(l) for l in Path(args.filter).read_text().splitlines() if l.strip()]
    try:
        conn = open_db()
        wd = rules["dedup"]["seen_window_days"]
        th = rules["dedup"]["title_similarity"]
        titles = recent_titles(conn, wd)
        fresh = [i for i in items if not is_dup(i, conn, titles, wd, th)]
    except Exception as exc:
        print(f"[警告] 去重库异常，放行全部候选: {exc}", file=sys.stderr)
        fresh = items
    out = Path(args.out) if args.out else Path(args.filter).with_name("fresh.jsonl")
    with out.open("w") as f:
        for i in fresh:
            f.write(json.dumps(i, ensure_ascii=False) + "\n")
    print(f"{len(items)} 候选 -> {len(fresh)} 新条目 ({len(items)-len(fresh)} 已见过) -> {out}",
          file=sys.stderr)
    return 0


def cmd_record(args) -> int:
    items = [json.loads(l) for l in Path(args.record).read_text().splitlines() if l.strip()]
    conn = open_db()
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        for i in items:
            conn.execute("INSERT OR REPLACE INTO seen VALUES(?,?,?,?,?,?)",
                         (i["id"], normalize_url(i["url"]), i.get("title", ""),
                          i.get("source", ""), args.status, now))
    print(f"登记 {len(items)} 条为 {args.status}", file=sys.stderr)
    return 0


def cmd_stats() -> int:
    conn = open_db()
    total = conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
    print(f"seen.db: {total} 条 @ {data_dir()/'seen.db'}")
    for status, n in conn.execute("SELECT status, COUNT(*) FROM seen GROUP BY status"):
        print(f"  {status}: {n}")
    return 0


def cmd_self_test() -> int:
    os.environ["ASTA_NEWS_HOME"] = "/tmp/asta-selftest"
    db = Path("/tmp/asta-selftest/seen.db")
    if db.exists():
        db.unlink()
    conn = open_db()
    a = {"id": "t:1", "url": "https://www.example.com/post?utm_source=x", "title": "Qwen4 released with 1T parameters today", "source": "t"}
    b = {"id": "t:2", "url": "http://example.com/post", "title": "irrelevant", "source": "t"}
    c = {"id": "t:3", "url": "https://other.com/x", "title": "Qwen4 released with 1T parameters", "source": "t"}
    now = datetime.now(timezone.utc).isoformat()
    with conn:
        conn.execute("INSERT INTO seen VALUES(?,?,?,?,?,?)",
                     (a["id"], normalize_url(a["url"]), a["title"], "t", "published", now))
    titles = recent_titles(conn, 14)
    assert is_dup(b, conn, titles, 14, 0.78), "URL 规范化判重失败"
    assert is_dup(c, conn, titles, 14, 0.78), "模糊标题判重失败"
    assert not is_dup({"id": "t:4", "url": "https://new.com/y", "title": "Completely different news about robotics hardware"},
                      conn, titles, 14, 0.78), "误判新条目"
    print("self-test: 3/3 PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--filter", help="输入 candidates.jsonl，输出未见过的")
    g.add_argument("--record", help="登记 jsonl 文件中的条目")
    g.add_argument("--stats", action="store_true")
    g.add_argument("--self-test", action="store_true")
    ap.add_argument("--status", default="published", choices=["published", "considered"])
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.self_test:
        return cmd_self_test()
    if args.stats:
        return cmd_stats()
    if args.record:
        return cmd_record(args)
    return cmd_filter(args, load_rules())


if __name__ == "__main__":
    sys.exit(main())
