# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""asta-news 配图：给 edition 的 group/daily 条目找一张代表图（借鉴橘鸦"用图说话"）。

抓取顺序（每条按其 links.primary）：
  1. github.com/owner/repo  → opengraph.githubassets.com 社交预览（必有）
  2. huggingface.co/...      → og:image（论文/模型卡页有）
  3. 其它页面               → og:image / twitter:image（meta 抓取）
  4. 抓不到                  → 不配（前端用 layer 主题色兜底）
版权：记 source 域名到 image.credit。被墙域名走 ASTA_PROXY。

用法:
  enrich_images.py --edition site/data/2026-06-12.json [--tiers group,daily] [--max 24]
原地写回 image 字段。失败开放：单条失败跳过，不阻塞。
"""
import argparse
import json
import os
import re
import sys
from urllib.parse import urlsplit

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137 Safari/537.36"
S = requests.Session()
S.trust_env = False
BLOCKED = ("huggingface.co", "x.com", "twitter.com", "anthropic.com", "ai.meta.com", "mistral.ai")


def fetch(url: str) -> str | None:
    host = urlsplit(url).netloc.lower()
    proxy = os.environ.get("ASTA_PROXY")
    attempts = [{"http": proxy, "https": proxy}] if (proxy and any(b in host for b in BLOCKED)) else [None]
    if proxy and not attempts[0]:
        attempts.append({"http": proxy, "https": proxy})
    for px in attempts:
        try:
            r = S.get(url, timeout=15, proxies=px, headers={"User-Agent": UA})
            if r.ok:
                return r.text
        except Exception:
            continue
    return None


def meta_image(html: str) -> str | None:
    for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']'):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1)
    return None


def find_image(url: str) -> dict | None:
    if not url:
        return None
    host = urlsplit(url).netloc.lower().removeprefix("www.")
    # GitHub 社交预览：确定性存在
    m = re.match(r"https?://github\.com/([^/]+)/([^/?#]+)", url)
    if m:
        return {"url": f"https://opengraph.githubassets.com/1/{m.group(1)}/{m.group(2)}", "credit": "github.com", "source": url}
    html = fetch(url)
    if not html:
        return None
    img = meta_image(html)
    if img and img.startswith("//"):
        img = "https:" + img
    if img and img.startswith("http"):
        if re.search(r"(?i)(logo|favicon|default[-_]?(og|share)|placeholder)", img):
            return None  # 跳过 logo/占位类 og:image（信息量低、常防盗链）
        return {"url": img, "credit": host, "source": url}
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edition", required=True)
    ap.add_argument("--tiers", default="group,daily")
    ap.add_argument("--max", type=int, default=24)
    args = ap.parse_args()

    d = json.loads(open(args.edition).read())
    tiers = d.get("tiers", {})
    want = args.tiers.split(",")
    seen, done, n = {}, 0, 0
    for tier in want:
        for it in tiers.get(tier, []):
            if n >= args.max:
                break
            if it.get("image"):
                continue
            url = (it.get("links") or {}).get("primary", "")
            if not url:
                continue
            if url in seen:
                it["image"] = seen[url]
                continue
            img = find_image(url)
            n += 1
            if img:
                it["image"] = img
                seen[url] = img
                done += 1
                print(f"  ✓ {it.get('title','')[:46]}  ←  {img['url'][:60]}", file=sys.stderr)
    # group 与 daily 里同 id 的条目同步图
    gimg = {i.get("id") or i.get("title"): i.get("image") for i in tiers.get("group", []) if i.get("image")}
    for it in tiers.get("daily", []):
        k = it.get("id") or it.get("title")
        if not it.get("image") and gimg.get(k):
            it["image"] = gimg[k]
    if "group" in tiers:
        d["selected"] = tiers["group"]
    open(args.edition, "w").write(json.dumps(d, ensure_ascii=False, indent=1))
    print(f"配图完成：{done}/{n} 条找到图 → {args.edition}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
