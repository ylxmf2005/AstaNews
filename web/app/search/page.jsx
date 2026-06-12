"use client";
import { useEffect, useMemo, useState } from "react";
import { layerName, BASE } from "../../lib/config";

// v1：客户端关键词检索（语料 corpus.json 构建期生成）。
// 向量/混合检索接入服务后端或 transformers.js 在后续迭代加（见 ROADMAP P2-SEARCH）。
function score(item, terms) {
  const hay = (item.title + " " + (item.body || "")).toLowerCase();
  let s = 0;
  for (const t of terms) {
    if (!t) continue;
    const inTitle = item.title.toLowerCase().includes(t);
    const inBody = hay.includes(t);
    if (inTitle) s += 3;
    else if (inBody) s += 1;
  }
  return s;
}

export default function Search() {
  const [corpus, setCorpus] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    fetch(`${BASE}/data/corpus.json`).then((r) => r.json()).then((d) => setCorpus(d.items || [])).catch(() => setCorpus([]));
  }, []);

  const results = useMemo(() => {
    if (!corpus || !q.trim()) return [];
    const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
    return corpus.map((it) => ({ it, s: score(it, terms) })).filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s).slice(0, 40).map((x) => x.it);
  }, [corpus, q]);

  return (
    <>
      <div className="dateline">搜索 · 全部归档</div>
      <input className="searchbox" autoFocus placeholder="搜一条新闻、模型名、概念…（如 Kimi、稀疏注意力、tactile）"
        value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="search-hint">
        {corpus == null ? "加载语料…" : q.trim() ? `${results.length} 条命中（共 ${corpus.length} 条索引）` : `${corpus.length} 条已索引 · 关键词检索（向量/语义检索迭代中）`}
      </div>
      <ul className="rows" style={{ marginTop: 20 }}>
        {results.map((it, i) => (
          <li className="row" key={it.id || i}>
            <div className="rhead">
              <span className="lb">{it.date} · {layerName(it.layer)} · {it.tier}</span>
              <a href={it.url || "#"} target="_blank" rel="noopener">{it.title}</a>
            </div>
            {it.body && <div className="rsum">{it.body}</div>}
          </li>
        ))}
      </ul>
    </>
  );
}
