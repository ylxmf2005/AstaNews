import Link from "next/link";
import { latestEdition, allDates } from "../lib/data";
import EditionView from "../components/EditionView";

export default function Home() {
  const ed = latestEdition();
  if (!ed) return <p className="empty">还没有发布任何 digest。跑一次 /asta-news:daily-digest 后发布即可。</p>;
  const dates = allDates();
  const prev = dates.length > 1 ? dates[1] : null; // 上一期
  return (
    <>
      <div className="dateline">{ed.date} · {ed.weekday || ""} · 今日日报</div>
      {ed.overview && (
        <p className="deck">
          {ed.headline && <span className="lead-in">{ed.headline}。</span>}
          {ed.overview}
        </p>
      )}
      <EditionView edition={ed} />
      <nav style={{ marginTop: 34, paddingTop: 16, borderTop: "1px solid var(--rule)", display: "flex", justifyContent: "space-between", fontFamily: "var(--mono)", fontSize: 13 }}>
        <span>{prev ? <Link href={`/edition/${prev}`}>← 上一期 {prev}</Link> : <span style={{ color: "var(--faint)" }}>暂无往期</span>}</span>
        <Link href="/archive" style={{ color: "var(--muted)" }}>往期目录（{dates.length} 期）</Link>
      </nav>
    </>
  );
}
