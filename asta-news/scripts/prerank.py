# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""asta-news 初筛打分 + 漏斗——多信号确定性融合（零 LLM），可选小模型薄层重排。

把 editor 的"初筛/rank"下放成脚本：用全确定性、已抓到的信号给候选打分排序，
把全部候选压到 keep 条；可选再让小模型对 top-keep 结构化重排到 rerank_keep。
agent 最终只看这十几条。信号（全归一到 0–1）：
  source_priority  源权威 P0/P1/P2
  recency          新鲜度（指数衰减）
  consensus        多源共识（dedup 聚类大小）——多方比对的廉价版
  leading_kw       领先/首次关键词命中（对齐"新与领先优先"）
  heat             热度（HN points / stars / likes，对数归一）
  cross_stack      跨层加成（classify 给的）

每条输出加 prerank_score 与 signals 分项（透明可审）。
LLM 重排不可用（无 key/连不上）→ 自动跳过，纯确定性结果。

用法:
  prerank.py --in classified.jsonl --out ranked.jsonl [--keep 30] [--rerank --rerank-keep 15]
  prerank.py --self-test
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent
CONFIG = SCRIPTS.parent / "config" / "prerank.yaml"
sys.path.insert(0, str(SCRIPTS))

PRIORITY = {"P0": 1.0, "P1": 0.6, "P2": 0.3}


def cfg() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def _parse_dt(s: str):
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _heat_raw(extra: dict) -> float:
    if not isinstance(extra, dict):
        return 0.0
    vals = []
    for k in ("points", "upvotes", "score", "stars", "likes", "comments", "num_comments", "reactions"):
        v = extra.get(k)
        if isinstance(v, (int, float)):
            vals.append(float(v))
    return max(vals) if vals else 0.0


def signals(c: dict, conf: dict, now: datetime) -> dict:
    s = {}
    # 源权威
    s["source_priority"] = PRIORITY.get(c.get("priority", "P1"), 0.6)
    # 新鲜度：指数衰减
    dt = _parse_dt(c.get("published"))
    if dt:
        age_h = max(0.0, (now - dt).total_seconds() / 3600)
        s["recency"] = math.exp(-age_h / max(1.0, conf["recency_half_life_hours"]))
    else:
        s["recency"] = 0.4  # 无时间戳 → 中性
    # 多源共识：dedup 聚类大小（缺则 1）
    cluster = int(c.get("cluster_size", 1) or 1)
    s["consensus"] = min(1.0, max(0, cluster - 1) / max(1, conf["consensus_saturate"] - 1))
    # 领先/首次关键词
    hay = f"{c.get('title','')} {c.get('summary','') or c.get('text','')}".lower()
    hits = sum(1 for kw in conf["leading_keywords"] if kw.lower() in hay)
    s["leading_kw"] = min(1.0, hits / 2.0)
    # 热度：对数归一
    hr = _heat_raw(c.get("extra"))
    s["heat"] = min(1.0, math.log1p(hr) / math.log1p(conf["heat_cap"])) if hr > 0 else 0.0
    # 跨层
    s["cross_stack"] = 1.0 if c.get("cross_stack") else 0.0
    return s


def score(c: dict, conf: dict, now: datetime) -> float:
    s = signals(c, conf, now)
    c["signals"] = {k: round(v, 3) for k, v in s.items()}
    w = conf["weights"]
    total = sum(w.get(k, 0) * v for k, v in s.items())
    c["prerank_score"] = round(total, 4)
    return total


def prerank(cands: list[dict], conf: dict, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    for c in cands:
        score(c, conf, now)
    cands.sort(key=lambda c: -c["prerank_score"])
    return cands


def llm_rerank(top: list[dict], rerank_keep: int) -> list[dict]:
    """对 top 条让小模型给 0–10 重要度，与确定性分各半融合重排。LLM 不可用 → 原样返回。"""
    import llm
    if not llm.available():
        print("  prerank: LLM 不可用，跳过重排（纯确定性结果）", file=sys.stderr)
        return top[:rerank_keep]
    brief = [{"id": c.get("id"), "title": c.get("title", ""),
              "summary": (c.get("summary") or c.get("text") or "")[:200], "layer": c.get("layer")} for c in top]
    sys_p = ("你是 AI 全栈情报的初筛编辑。对每条新闻按'对 AI 全栈从业者的重要度'打 0–10 分，"
             "新(信息增量)与领先(SOTA/首次)优先，营销复述与琐碎更新低分。只返回 JSON："
             '{"items":[{"id":"...","importance":0,"reason":"一句中文理由"}]}')
    out = llm.chat_json(sys_p, json.dumps(brief, ensure_ascii=False))
    if not out or "items" not in out:
        print("  prerank: LLM 重排无有效返回，跳过", file=sys.stderr)
        return top[:rerank_keep]
    imp = {it.get("id"): (it.get("importance"), it.get("reason")) for it in out["items"] if isinstance(it, dict)}
    dets = [c["prerank_score"] for c in top]
    lo, hi = min(dets), max(dets)
    for c in top:
        det_norm = (c["prerank_score"] - lo) / (hi - lo) if hi > lo else 0.5
        i, reason = imp.get(c.get("id"), (None, None))
        if isinstance(i, (int, float)):
            c["llm_importance"] = i
            c["llm_reason"] = reason
            c["rerank_score"] = round(0.5 * det_norm + 0.5 * (i / 10.0), 4)
        else:
            c["rerank_score"] = round(0.5 * det_norm + 0.5 * (c["prerank_score"]), 4)
    top.sort(key=lambda c: -c.get("rerank_score", 0))
    return top[:rerank_keep]


def cmd_self_test() -> int:
    now = datetime.now(timezone.utc)
    fresh = now.replace(microsecond=0).isoformat()
    from datetime import timedelta
    old = (now - timedelta(hours=120)).isoformat()
    cands = [
        {"id": "hot", "title": "OpenAI releases first open-weights SOTA model, outperforms all", "summary": "open source breakthrough", "priority": "P0", "published": fresh, "cluster_size": 4, "extra": {"points": 600}, "cross_stack": True},
        {"id": "mid", "title": "Some framework v1.2 minor update", "summary": "small improvements", "priority": "P1", "published": fresh, "cluster_size": 1, "extra": {"points": 20}},
        {"id": "weak", "title": "Library patch release fixes typo", "summary": "bugfix", "priority": "P2", "published": old, "cluster_size": 1, "extra": {}},
    ]
    conf = cfg()
    prerank(cands, conf, now)
    for c in cands:
        print(f"  {c['prerank_score']:.3f}  {c['id']:5s}  sig={c['signals']}")
    order = [c["id"] for c in cands]
    assert order == ["hot", "mid", "weak"], f"排序不符预期：{order}"
    assert cands[0]["prerank_score"] > cands[-1]["prerank_score"] + 0.3, "强弱分差过小"
    print("self-test: 多信号排序 PASS（P0+首次+多源+热门 > 琐碎更新 > 旧 bugfix）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out")
    ap.add_argument("--keep", type=int)
    ap.add_argument("--rerank", action="store_true", help="对 top-keep 调小模型重排")
    ap.add_argument("--rerank-keep", type=int)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return cmd_self_test()
    if not args.inp:
        ap.error("需要 --in 或 --self-test")
    conf = cfg()
    keep = args.keep or conf.get("keep", 30)
    rerank_keep = args.rerank_keep or conf.get("rerank_keep", 15)
    cands = [json.loads(l) for l in Path(args.inp).read_text().splitlines() if l.strip()]
    prerank(cands, conf)
    kept = cands[:keep]
    if args.rerank:
        kept = llm_rerank(kept, rerank_keep)
    out = Path(args.out or args.inp)
    out.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in kept) + "\n")
    print(f"初筛 {len(cands)} → 留 {len(kept)} 条 → {out}"
          + (f"（含 LLM 重排到 {rerank_keep}）" if args.rerank else "（纯确定性）"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
