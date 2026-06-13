import Link from "next/link";

export const metadata = { title: "未找到 · AstaNews" };

export default function NotFound() {
  return (
    <div style={{ textAlign: "center", padding: "60px 0" }}>
      <div style={{ fontFamily: "var(--disp)", fontWeight: 900, fontSize: 72, color: "var(--seal)", lineHeight: 1 }}>404</div>
      <p className="deck" style={{ marginTop: 18 }}>这一页不在情报站里。可能是过期归档被精简，或链接有误。</p>
      <div className="links" style={{ justifyContent: "center", display: "flex", gap: 22, marginTop: 16 }}>
        <Link href="/">回今日日报</Link>
        <Link href="/archive">往期</Link>
        <Link href="/search">搜索</Link>
      </div>
    </div>
  );
}
