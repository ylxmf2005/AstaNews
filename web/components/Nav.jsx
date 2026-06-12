"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { label: "今日日报", path: "/" },
  { label: "往期", path: "/archive" },
  { label: "搜索", path: "/search" },
  { label: "关于", path: "/about" },
];

export default function Nav() {
  const p = usePathname() || "/";
  const norm = (x) => (x.length > 1 ? x.replace(/\/$/, "") : x);
  const cur = norm(p);
  return (
    <nav className="topnav">
      {ITEMS.map((it) => {
        const active = it.path === "/" ? cur === "/" : cur.startsWith(it.path);
        return (
          <Link key={it.path} href={it.path} className={active ? "active" : ""}>{it.label}</Link>
        );
      })}
    </nav>
  );
}
