"use client";
import { useEffect, useMemo, useState } from "react";
import { LAYERS, lz, layerName, layerEmoji, layerColor, TIERS, PERSPECTIVES, BASE } from "../lib/config";

function baseScore(it, i) {
  if (typeof it.score === "number") return it.score;
  if (it.scores) {
    const w = { novelty: 0.35, leading_edge: 0.3, impact: 0.25, cross_stack: 0.1 };
    return Object.entries(w).reduce((s, [k, v]) => s + (it.scores[k] || 0) * v, 0);
  }
  return Math.max(0, 10 - (it.rank ?? i));
}

function applyPerspective(items, persp) {
  if (!persp || persp.key === "all") return items;
  return [...items]
    .map((it, i) => ({ it, s: baseScore(it, i) + (persp.boost[lz(it.layer)] || 0) * 1.6 }))
    .sort((a, b) => b.s - a.s)
    .map((x) => x.it);
}

function Story({ it, n, related, lead }) {
  const body = it.readable || it.take || "";
  const facts = it.facts || [];
  const links = [];
  if (it.links?.primary) links.push(["一手源", it.links.primary]);
  if (it.links?.discussion) links.push(["讨论", it.links.discussion]);
  const rel = (related?.[it.links?.primary] || []).filter((r) => r.score >= 0.35).slice(0, 3);
  return (
    <article className={lead ? "story lead" : "story"}>
      <div className="num">{n}</div>
      <div className="dept"><span>{layerEmoji(it.layer)}</span>{layerName(it.layer)}</div>
      <h2>{it.title}</h2>
      {it.image?.url && <img className="thumb" src={it.image.url} alt="" loading="lazy" />}
      {body && <div className="body">{body}</div>}
      {facts.length > 0 && <ul className="facts">{facts.map((f, i) => <li key={i}>{f}</li>)}</ul>}
      {links.length > 0 && (
        <div className="links">{links.map(([t, u]) => <a key={u} href={u} target="_blank" rel="noopener">{t}</a>)}</div>
      )}
      {rel.length > 0 && (
        <div className="related">
          <span className="rel-label">相关</span>
          {rel.map((r) => (
            <a key={r.url} href={r.url} target="_blank" rel="noopener" title={`相似度 ${r.score}`}>
              <span className="rel-lb">{layerName(r.layer)}</span>{r.title}
            </a>
          ))}
        </div>
      )}
    </article>
  );
}

function FullRows({ items }) {
  const by = {};
  for (const c of items) (by[c.source] = by[c.source] || []).push(c);
  return (
    <div>
      {Object.keys(by).sort().map((src) => (
        <div key={src} style={{ marginBottom: 18 }}>
          <div className="sec" style={{ margin: "20px 0 8px" }}>{src} · {by[src].length}</div>
          <ul className="rows">
            {by[src].map((c, i) => (
              <li className="row" key={i}>
                <div className="rhead">
                  <span className="lb">{layerName(c.layer)}</span>
                  <a href={c.url} target="_blank" rel="noopener">{c.title}</a>
                </div>
                {c.summary && <div className="rsum">{c.summary}</div>}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export default function EditionView({ edition }) {
  const [tier, setTier] = useState("daily");
  const [persp, setPersp] = useState("all");   // 视角（大）：重排+框定
  const [cat, setCat] = useState("all");        // 类别（小）：按 layer 硬筛
  const [related, setRelated] = useState(null); // 预计算的相关新闻（向量近邻）
  useEffect(() => {
    fetch(`${BASE}/data/related.json`).then((r) => r.json()).then(setRelated).catch(() => setRelated({}));
  }, []);
  const tiers = edition.tiers || { group: edition.selected || [], daily: edition.selected || [], full: edition.all_candidates || [] };
  const perspObj = PERSPECTIVES.find((p) => p.key === persp) || PERSPECTIVES[0];

  // 当前 tier 里出现的类别（只展示有内容的，按数量排序）
  const cats = useMemo(() => {
    const cnt = {};
    for (const it of tiers[tier] || []) { const k = lz(it.layer); if (k) cnt[k] = (cnt[k] || 0) + 1; }
    return Object.entries(cnt).sort((a, b) => b[1] - a[1]);
  }, [tier, edition.date]);

  const items = useMemo(() => {
    let raw = tiers[tier] || [];
    if (tier !== "full") raw = applyPerspective(raw, perspObj);
    if (cat !== "all") raw = raw.filter((it) => lz(it.layer) === cat);
    return raw;
  }, [tier, persp, cat, edition.date]);

  const perspLede = edition.perspectives?.[persp]?.lede;

  return (
    <div>
      <div className="controls">
        <div className="ctl-group">
          <span className="ctl-label">级别</span>
          <div className="seg">
            {TIERS.map((t) => (
              <button key={t.key} className={tier === t.key ? "on" : ""} onClick={() => setTier(t.key)} title={t.desc}>
                {t.label}<span style={{ opacity: .6, marginLeft: 5, fontSize: 11 }}>{(tiers[t.key] || []).length}</span>
              </button>
            ))}
          </div>
        </div>
        {tier !== "full" && (
          <div className="ctl-group">
            <span className="ctl-label">视角</span>
            <div className="seg">
              {PERSPECTIVES.map((p) => (
                <button key={p.key} className={persp === p.key ? "on" : ""} onClick={() => setPersp(p.key)}>{p.label}</button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 类别（小）：独立的 layer 硬筛 */}
      <div className="cats">
        <span className="ctl-label">类别</span>
        <button className={`chip ${cat === "all" ? "on" : ""}`} onClick={() => setCat("all")}>全部</button>
        {cats.map(([k, n]) => (
          <button key={k} className={`chip ${cat === k ? "on" : ""}`} onClick={() => setCat(cat === k ? "all" : k)}
            style={cat === k ? { background: layerColor(k), borderColor: layerColor(k), color: "#f4efe6" } : { borderColor: layerColor(k) + "66" }}>
            {layerEmoji(k)} {layerName(k)} <span style={{ opacity: .6 }}>{n}</span>
          </button>
        ))}
      </div>

      {tier !== "full" && persp !== "all" && (
        <p className="persp-lede">{perspLede || `${perspObj.label}视角`}</p>
      )}

      <div className="sec">
        {TIERS.find((t) => t.key === tier)?.label}
        {tier !== "full" && persp !== "all" ? ` · ${perspObj.label}视角` : ""}
        {cat !== "all" ? ` · ${layerName(cat)}` : ""}
        <span style={{ fontFamily: "var(--mono)", color: "var(--faint)", marginLeft: 8 }}>{items.length}</span>
      </div>

      {tier === "full"
        ? <FullRows items={items} />
        : items.length === 0
          ? <p className="empty">该类别下暂无条目。</p>
          : items.map((it, i) => <Story key={it.id || i} it={it} n={i + 1} related={related} lead={i === 0} />)}

      {tier !== "full" && edition.gaps?.length > 0 && (
        <>
          <div className="sec">数据缺口</div>
          <div className="note"><h3>编者按 · 今日未覆盖</h3>
            <ul>{edition.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul></div>
        </>
      )}
    </div>
  );
}
