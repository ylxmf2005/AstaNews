"use client";
import { useMemo, useState } from "react";
import { LAYERS, lz, layerName, layerEmoji, TIERS, PERSPECTIVES } from "../lib/config";

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

function Story({ it, n }) {
  const body = it.readable || it.take || "";
  const facts = it.facts || [];
  const links = [];
  if (it.links?.primary) links.push(["一手源", it.links.primary]);
  if (it.links?.discussion) links.push(["讨论", it.links.discussion]);
  return (
    <article className="story">
      <div className="num">{n}</div>
      <div className="dept"><span>{layerEmoji(it.layer)}</span>{layerName(it.layer)}</div>
      <h2>{it.title}</h2>
      {it.image?.url && <img className="thumb" src={it.image.url} alt="" loading="lazy" />}
      {body && <div className="body">{body}</div>}
      {facts.length > 0 && <ul className="facts">{facts.map((f, i) => <li key={i}>{f}</li>)}</ul>}
      {links.length > 0 && (
        <div className="links">{links.map(([t, u]) => <a key={u} href={u} target="_blank" rel="noopener">{t}</a>)}</div>
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
  const [persp, setPersp] = useState("all");
  const tiers = edition.tiers || { group: edition.selected || [], daily: edition.selected || [], full: edition.all_candidates || [] };
  const perspObj = PERSPECTIVES.find((p) => p.key === persp) || PERSPECTIVES[0];

  const items = useMemo(() => {
    const raw = tiers[tier] || [];
    if (tier === "full") return raw;
    return applyPerspective(raw, perspObj);
  }, [tier, persp, edition.date]);

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

      {tier !== "full" && persp !== "all" && (
        <p className="persp-lede">{perspLede || `${perspObj.label}视角 — ${PERSPECTIVES.find(p=>p.key===persp)?.label}` }</p>
      )}

      <div className="sec">{TIERS.find((t) => t.key === tier)?.label}{tier !== "full" && persp !== "all" ? ` · ${perspObj.label}视角` : ""}</div>

      {tier === "full"
        ? <FullRows items={items} />
        : items.map((it, i) => <Story key={it.id || i} it={it} n={i + 1} />)}

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
