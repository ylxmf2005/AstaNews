# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "trafilatura"]
# ///
"""asta-news 解析（正文抽取）——给"摘要过薄"的候选补一段干净正文，零 LLM。

很多 html 源/转述源只给一句标题或空摘要，下游评分/改写会缺料。本脚本对这类候选
抓原文、用 trafilatura（规则法，无模型）抽正文，剥掉导航/广告/页脚，回填更好的
`summary` 并存 `clean_text`。摘要本就够长的候选直接跳过，不浪费抓取。
失败开放：单条抓不到/抽不出就保持原样，绝不阻塞。被墙域名走 ASTA_PROXY。

用法:
  extract.py --in fresh.jsonl --out enriched.jsonl [--min-summary 120] [--max 40]
  extract.py --self-test
"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests
import trafilatura

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137 Safari/537.36"
S = requests.Session()
S.trust_env = False
BLOCKED = ("huggingface.co", "x.com", "twitter.com", "anthropic.com", "ai.meta.com", "mistral.ai", "googleblog.com")


def fetch(url: str) -> str | None:
    host = urlsplit(url).netloc.lower()
    proxy = os.environ.get("ASTA_PROXY")
    attempts = [{"http": proxy, "https": proxy}] if (proxy and any(b in host for b in BLOCKED)) else [None]
    if proxy and attempts == [None]:
        attempts.append({"http": proxy, "https": proxy})  # 直连失败再试代理
    for px in attempts:
        try:
            r = S.get(url, timeout=15, proxies=px, headers={"User-Agent": UA})
            if r.ok and r.text:
                return r.text
        except requests.RequestException:
            continue
    return None


def extract_text(html: str) -> str | None:
    """纯函数：从 HTML 抽干净正文（剥导航/评论/表格）。抽不出 → None。"""
    if not html:
        return None
    txt = trafilatura.extract(html, favor_precision=True, include_comments=False,
                              include_tables=False, no_fallback=False)
    txt = (txt or "").strip()
    return txt or None


def enrich(cands: list[dict], min_summary: int, max_fetch: int, fetcher=None) -> int:
    fetcher = fetcher or fetch  # 可注入抓取器（自测用 stub，免网络）
    done = 0
    for c in cands:
        if done >= max_fetch:
            break
        summary = (c.get("summary") or "").strip()
        if len(summary) >= min_summary:
            continue  # 已够料
        url = c.get("url") or (c.get("links") or {}).get("primary", "")
        if not url:
            continue
        html = fetcher(url)
        if not html:
            continue
        text = extract_text(html)
        if not text:
            continue
        c["clean_text"] = text[:2000]
        if len(summary) < min_summary:
            c["summary"] = text[:400]  # 升级过薄摘要
        done += 1
        print(f"  ✓ {c.get('title','')[:46]}  +{len(text)} 字正文", file=sys.stderr)
    return done


SAMPLE_HTML = """<html><head><title>X</title></head><body>
<nav>首页 关于 登录 订阅 搜索</nav><header>站点横幅广告位</header><aside>相关推荐 热门标签</aside>
<article><h1>某实验室发布开源模型</h1>
<p>某实验室今日发布了一个 200B 参数的开源模型，在 MMLU 基准上达到 88.5 分，超过此前所有开源模型。
该模型采用 MoE 架构，激活参数 22B，已在 Hugging Face 上线，附完整评测报告与推理示例代码，社区反响热烈。</p></article>
<footer>版权所有 联系我们 隐私政策 备案号</footer></body></html>"""


def cmd_self_test() -> int:
    # 1) 抽取纯函数：留正文、剥边栏页脚
    txt = extract_text(SAMPLE_HTML)
    print(f"  抽出 {len(txt or '')} 字：{(txt or '')[:60]}…")
    assert txt and "200B" in txt and "MMLU" in txt, "正文未抽到"
    assert "登录" not in txt and "版权" not in txt, "导航/页脚未剥干净"
    # 2) enrich：薄摘要被升级、够料的不动、无 url 跳过
    cands = [
        {"id": "thin", "title": "薄摘要", "summary": "一句话", "url": "data:noop"},  # 抓不到→保持原样（验证失败开放）
        {"id": "rich", "title": "够料", "summary": "x" * 200, "url": "http://example.com"},
    ]
    # 注入 stub 抓取器把 thin 的抓取短路成 SAMPLE_HTML，验证回填逻辑（免网络）
    stub = lambda u: SAMPLE_HTML if u == "data:noop" else None  # noqa: E731
    n = enrich(cands, min_summary=120, max_fetch=10, fetcher=stub)
    assert n == 1, f"应只升级 1 条薄摘要，实际 {n}"
    assert "200B" in cands[0]["summary"] and "clean_text" in cands[0], "薄摘要未被升级"
    assert cands[1]["summary"] == "x" * 200, "够料的不应被改"
    print("self-test: 解析抽取 + 薄摘要升级 + 够料跳过 PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out")
    ap.add_argument("--min-summary", type=int, default=120, help="摘要短于此长度才去抓正文")
    ap.add_argument("--max", type=int, default=40, help="最多抓取条数（控成本）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return cmd_self_test()
    if not args.inp:
        ap.error("需要 --in 或 --self-test")
    cands = [json.loads(l) for l in Path(args.inp).read_text().splitlines() if l.strip()]
    n = enrich(cands, args.min_summary, args.max)
    out = Path(args.out or args.inp)
    out.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cands) + "\n")
    print(f"解析：{n} 条补了正文 → {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
