import { allDates, getEdition } from "../../../lib/data";
import EditionView from "../../../components/EditionView";
import Link from "next/link";

export function generateStaticParams() {
  return allDates().map((date) => ({ date }));
}

export default async function EditionPage({ params }) {
  const { date } = await params;
  const ed = getEdition(date);
  if (!ed) return <p className="empty">未找到 {date} 这期。</p>;
  return (
    <>
      <div className="dateline">{ed.date} · {ed.weekday || ""}</div>
      {ed.overview && (
        <p className="deck">
          {ed.headline && <span className="lead-in">{ed.headline}。</span>}
          {ed.overview}
        </p>
      )}
      <EditionView edition={ed} />
      <p style={{ marginTop: 30 }}><Link href="/archive">← 往期</Link></p>
    </>
  );
}
