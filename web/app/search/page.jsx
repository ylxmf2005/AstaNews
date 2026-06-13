"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { layerName, BASE, API } from "../../lib/config";

// 混合检索：语义（浏览器内 transformers.js 嵌入 query，与预构建向量点积）+ 关键词。
// 模型 Xenova/paraphrase-multilingual-MiniLM-L12-v2（与索引同款），经 hf-mirror 加载，浏览器缓存。
const MODEL = "Xenova/paraphrase-multilingual-MiniLM-L12-v2";

function kwScore(item, terms) {
  const t = (item.t || "").toLowerCase();
  let s = 0;
  for (const w of terms) if (w && t.includes(w)) s += t.startsWith(w) ? 2 : 1;
  return s;
}

export default function Search() {
  const [q, setQ] = useState("");
  const [meta, setMeta] = useState(null);      // search.json items
  const [vecs, setVecs] = useState(null);      // Float32Array, dim*count
  const [dim, setDim] = useState(384);
  const [model, setModel] = useState(null);    // extractor
  const [status, setStatus] = useState("loading-index");
  const [results, setResults] = useState([]);
  const busy = useRef(false);

  // 加载索引（仅在无后端时；有后端走服务端检索）
  useEffect(() => {
    if (API) { setStatus("api"); return; }
    (async () => {
      try {
        const s = await fetch(`${BASE}/data/search.json`).then((r) => r.json());
        setMeta(s.items); setDim(s.dim);
        const buf = await fetch(`${BASE}/data/vectors.bin`).then((r) => r.arrayBuffer());
        setVecs(new Float32Array(buf));
        setStatus("loading-model");
      } catch { setStatus("keyword-only"); }
    })();
  }, []);

  // 服务端语义检索（连了后端时，最可靠）
  useEffect(() => {
    if (status !== "api" || !q.trim()) { return; }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const d = await (await fetch(`${API}/api/search?q=${encodeURIComponent(q)}&top=40`)).json();
        if (!cancelled) setResults((d.results || []).map((r) => ({ it: { u: r.url, t: r.title, d: r.date, l: r.layer }, sem: r.score })));
      } catch { /* 后端不可达则保持空 */ }
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q, status]);

  // 懒加载语义模型
  useEffect(() => {
    if (status !== "loading-model") return;
    (async () => {
      try {
        const t = await import(/* webpackIgnore: true */ "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.3.3/+esm");
        t.env.allowLocalModels = false;
        t.env.remoteHost = "https://hf-mirror.com";
        t.env.remotePathTemplate = "{model}/resolve/{revision}/";
        const ext = await t.pipeline("feature-extraction", MODEL, { dtype: "q8" });
        setModel(() => ext); setStatus("ready");
      } catch (e) { console.error(e); setStatus("keyword-only"); }
    })();
  }, [status]);

  const terms = useMemo(() => q.toLowerCase().split(/\s+/).filter(Boolean), [q]);

  // 关键词即时结果（模型加载中也能用）
  const kwResults = useMemo(() => {
    if (!meta || !q.trim()) return [];
    return meta.map((it, i) => ({ it, i, s: kwScore(it, terms) })).filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s).slice(0, 40);
  }, [meta, q, terms]);

  // 语义检索（有模型时）
  useEffect(() => {
    if (!q.trim() || !model || !vecs || !meta || busy.current) { return; }
    let cancelled = false;
    (async () => {
      busy.current = true;
      try {
        const out = await model(q, { pooling: "mean", normalize: true });
        const qv = out.data; const n = meta.length;
        const scored = new Array(n);
        for (let i = 0; i < n; i++) {
          let dot = 0; const off = i * dim;
          for (let k = 0; k < dim; k++) dot += qv[k] * vecs[off + k];
          const kw = kwScore(meta[i], terms);
          scored[i] = { it: meta[i], sem: dot, score: dot + kw * 0.06 };
        }
        scored.sort((a, b) => b.score - a.score);
        if (!cancelled) setResults(scored.slice(0, 40));
      } finally { busy.current = false; }
    })();
    return () => { cancelled = true; };
  }, [q, model, vecs, meta, dim, terms]);

  const showSem = (status === "ready" || status === "api") && q.trim() && results.length > 0;
  const list = showSem ? results.map((r) => ({ ...r.it, _sc: r.sem })) : kwResults.map((r) => ({ ...r.it, _kw: r.s }));

  const hint = {
    "api": "服务端语义检索（已连后端）",
    "loading-index": "加载索引…",
    "loading-model": "语义模型加载中（首次约 30MB，之后浏览器缓存）— 先用关键词",
    "ready": `语义检索就绪 · ${meta?.length || 0} 条已索引`,
    "keyword-only": `关键词检索 · ${meta?.length || 0} 条（语义模型不可用）`,
  }[status];

  return (
    <>
      <div className="dateline">搜索 · 全部归档</div>
      <input className="searchbox" autoFocus value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="语义搜索：输入一个新闻、概念、模型名（如 长上下文推理优化 / tactile robot / 开源编程模型）" />
      <div className="search-hint">{q.trim() ? `${list.length} 条命中 · ${showSem ? "语义+关键词" : "关键词"}` : hint}</div>
      <ul className="rows" style={{ marginTop: 20 }}>
        {list.map((it, i) => (
          <li className="row" key={it.u || i}>
            <div className="rhead">
              <span className="lb">{it.d} · {layerName(it.l)}{it._sc != null ? ` · ${(it._sc).toFixed(2)}` : ""}</span>
              <a href={it.u || "#"} target="_blank" rel="noopener">{it.t}</a>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
