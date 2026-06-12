import "./globals.css";
import Link from "next/link";
import Nav from "../components/Nav";
import { SITE } from "../lib/config";

export const metadata = {
  title: "AstaNews · AI 全栈每日情报",
  description: "Asta Lab 的 AI 全栈每日情报：论文、模型发布、评测、infra、agent、具身、安全、产品商业、devtool。",
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>
        <div id="app">
          <div className="wrap">
            <header className="masthead">
              <div className="tele">
                <span>{SITE.lab} · 全栈情报站</span>
                <span className="seal-txt">AI FULL-STACK INTELLIGENCE</span>
                <span>每日 · 多级 · 多视角</span>
              </div>
              <div className="nameplate">
                <svg className="emblem" viewBox="0 0 64 64" fill="none" stroke="#b23a23" strokeWidth="2">
                  <ellipse cx="32" cy="32" rx="29" ry="12" transform="rotate(-28 32 32)" />
                  <circle cx="32" cy="32" r="7" fill="#b23a23" stroke="none" />
                  <circle cx="54" cy="18" r="2.5" fill="#b23a23" stroke="none" />
                </svg>
                <h1 className="wordmark"><Link href="/">Asta<span className="o">News</span></Link></h1>
                <span className="sub">{SITE.tagline}</span>
              </div>
              <Nav />
              <div className="masthead-rule" />
            </header>
            <main className="main">{children}</main>
            <footer className="colophon">
              <span>AstaNews</span>
              <span>抓取与去重确定 · 筛选与撰写由 agent 按编辑准则裁决</span>
              <a href={`https://github.com/${SITE.repo}`} target="_blank" rel="noopener">开放贡献</a>
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
