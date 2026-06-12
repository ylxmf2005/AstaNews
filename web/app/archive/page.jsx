import Link from "next/link";
import { editionIndex } from "../../lib/data";
import { layerName } from "../../lib/config";

export const metadata = { title: "往期 · AstaNews" };

export default function Archive() {
  const eds = editionIndex();
  return (
    <>
      <div className="dateline">往期归档 · {eds.length} 期</div>
      {eds.length === 0 ? <p className="empty">暂无归档</p> : (
        <ul className="issues">
          {eds.map((e, i) => (
            <li key={e.date}>
              <Link className="issue-row" href={`/edition/${e.date}`}>
                <span className="d">{e.date} · {e.weekday}</span>
                <div className="h">{e.headline || "AI 全栈每日情报"}</div>
                <div className="o">{e.overview}</div>
                <div className="m">No.{String(eds.length - i).padStart(3, "0")} · 日报 {e.daily || e.group} · 精选 {e.group} · 候选 {e.candidates} · {(e.layers || []).map(layerName).join(" / ")}</div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
