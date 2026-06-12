import Link from "next/link";
import { allItems, getItem } from "../../../lib/data";
import { layerName, layerEmoji } from "../../../lib/config";

export function generateStaticParams() {
  return Object.keys(allItems()).map((slug) => ({ slug }));
}

export default async function ItemPage({ params }) {
  const { slug } = await params;
  const it = getItem(slug);
  if (!it) return <p className="empty">未找到该条目。</p>;
  const body = it.readable || it.take || "";
  const facts = Array.isArray(it.facts) ? it.facts : it.facts ? [it.facts] : [];
  const rel = (it.related || []).filter((r) => r.score >= 0.3).slice(0, 6);
  return (
    <article style={{ maxWidth: 760 }}>
      <div className="dateline">
        {it.date} · {layerEmoji(it.layer)} {layerName(it.layer)}
        <Link href={`/edition/${it.date}`} style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 12 }}>← 本期</Link>
      </div>
      <h1 className="ed-title" style={{ fontFamily: "var(--cn-serif)", fontSize: "clamp(24px,3.4vw,34px)", lineHeight: 1.25, margin: "8px 0 16px" }}>{it.title}</h1>
      {it.image?.url && <img className="thumb" src={it.image.url} alt="" style={{ width: "100%", borderRadius: 10, border: "1px solid var(--rule)", marginBottom: 18 }} />}
      {body && <div className="body" style={{ fontSize: 16, whiteSpace: "pre-wrap", color: "var(--ink-2)" }}>{body}</div>}
      {it.sharp && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--seal)", cursor: "pointer" }}>锐评版</summary>
          <div className="body" style={{ fontSize: 15, whiteSpace: "pre-wrap", color: "var(--ink-2)", marginTop: 8 }}>{it.sharp}</div>
        </details>
      )}
      {facts.length > 0 && <ul className="facts" style={{ marginTop: 16 }}>{facts.map((f, i) => <li key={i}>{f}</li>)}</ul>}
      <div className="links" style={{ marginTop: 18 }}>
        {it.links?.primary && <a href={it.links.primary} target="_blank" rel="noopener">一手源</a>}
        {it.links?.discussion && <a href={it.links.discussion} target="_blank" rel="noopener">讨论</a>}
      </div>
      {rel.length > 0 && (
        <>
          <div className="sec" style={{ marginTop: 36 }}>相关</div>
          <ul className="rows">
            {rel.map((r) => (
              <li className="row" key={r.url}>
                <div className="rhead">
                  <span className="lb">{r.date} · {layerName(r.layer)} · {r.score?.toFixed(2)}</span>
                  <a href={r.url} target="_blank" rel="noopener">{r.title}</a>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  );
}
