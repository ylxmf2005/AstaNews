# /// script
# requires-python = ">=3.10"
# dependencies = ["fastembed", "numpy"]
# ///
"""asta-news 本地 embedding + 向量检索（离线 CPU，不依赖 OpenAI）

多语模型 paraphrase-multilingual-MiniLM-L12-v2（384 维，zh+en 跨语言）。
索引为 npz（ids + float32 向量 + sidecar meta json）——语料不大时够用，
后续可平滑换 sqlite-vec/lancedb。混合检索的 BM25 部分在 search.py。

用法:
  embed.py --build site/data            # 扫所有 edition.json 的候选 → 建/更新索引
  embed.py --search "查询词" [--top 10]  # 向量检索
  embed.py --self-test                  # 跨语言相似度自检
索引默认落 ${ASTA_INDEX:-<data>/vectors.npz}
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_model = None


def model():
    global _model
    if _model is None:
        # 默认走 hf-mirror（中国可直连，墙外也可达）；用户可用 HF_ENDPOINT 覆盖
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=MODEL)
    return _model


def embed(texts: list[str]) -> np.ndarray:
    vecs = np.array(list(model().embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.clip(norms, 1e-9, None)  # L2 归一化 → 点积即余弦


def default_index() -> Path:
    if os.environ.get("ASTA_INDEX"):
        return Path(os.environ["ASTA_INDEX"])
    out = Path(os.environ.get("ASTA_OUTPUT_DIR", PLUGIN_ROOT.parent / "site"))
    return out / "data" / "vectors.npz"


def iter_candidates(data_dir: Path):
    """从所有 edition json 收集可检索条目（精选 + 全部候选），去重 by id。"""
    seen = set()
    for f in sorted(data_dir.glob("20*.json")):
        if f.name == "index.json" or f.name == "vectors.npz":
            continue
        try:
            d = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        date = d.get("date", f.stem)
        rows = []
        for it in d.get("selected", []):
            rows.append((it.get("id") or f"{date}:{it.get('title','')}", it.get("title", ""),
                         it.get("readable", "") or " ".join(it.get("facts", [])),
                         (it.get("links") or {}).get("primary", ""), date, True))
        for c in d.get("all_candidates", []):
            cid = f"{c.get('source','')}:{c.get('url','')}"
            rows.append((cid, c.get("title", ""), c.get("summary", ""), c.get("url", ""), date, False))
        for cid, title, body, url, dt, sel in rows:
            if cid in seen:
                continue
            seen.add(cid)
            yield {"id": cid, "title": title, "text": f"{title}. {body}"[:512],
                   "url": url, "date": dt, "selected": sel}


def cmd_build(data_dir: Path, index_path: Path) -> int:
    items = list(iter_candidates(data_dir))
    if not items:
        print("无可索引条目", file=sys.stderr)
        return 1
    vecs = embed([it["text"] for it in items])
    meta = [{k: it[k] for k in ("id", "title", "url", "date", "selected")} for it in items]
    np.savez_compressed(index_path, vectors=vecs, ids=np.array([m["id"] for m in meta]))
    index_path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False))
    print(f"索引 {len(items)} 条 → {index_path} ({vecs.shape[1]} 维)", file=sys.stderr)
    return 0


def load_index(index_path: Path):
    z = np.load(index_path, allow_pickle=False)
    meta = json.loads(index_path.with_suffix(".meta.json").read_text())
    return z["vectors"], meta


def search(query: str, index_path: Path, top: int = 10):
    vecs, meta = load_index(index_path)
    q = embed([query])[0]
    scores = vecs @ q
    order = np.argsort(-scores)[:top]
    return [{**meta[i], "score": float(scores[i])} for i in order]


def cmd_self_test() -> int:
    pairs = [("开源编程模型", "open-source coding model"),
             ("块级稀疏注意力降低长文本显存", "block sparse attention reduces long-context memory")]
    neg = "今天天气不错适合散步"
    for zh, en in pairs:
        v = embed([zh, en, neg])
        sim_cross = float(v[0] @ v[1]); sim_neg = float(v[0] @ v[2])
        print(f"  '{zh}' ↔ '{en}' = {sim_cross:.3f}   vs 无关 = {sim_neg:.3f}")
        assert sim_cross > sim_neg + 0.15, "跨语言相似度未显著高于无关项"
    print("self-test: 跨语言相似检索 PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build", metavar="DATA_DIR", help="扫该目录所有 edition json 建索引")
    g.add_argument("--search", metavar="QUERY")
    g.add_argument("--self-test", action="store_true")
    ap.add_argument("--index", default=str(default_index()))
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()
    idx = Path(args.index)
    if args.self_test:
        return cmd_self_test()
    if args.build:
        idx.parent.mkdir(parents=True, exist_ok=True)
        return cmd_build(Path(args.build), idx)
    for r in search(args.search, idx, args.top):
        star = "★" if r["selected"] else " "
        print(f"{r['score']:.3f} {star} [{r['date']}] {r['title'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
