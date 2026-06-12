import { latestEdition } from "../lib/data";
import EditionView from "../components/EditionView";

export default function Home() {
  const ed = latestEdition();
  if (!ed) return <p className="empty">还没有发布任何 digest。跑一次 /asta-news:daily-digest 后发布即可。</p>;
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
    </>
  );
}
