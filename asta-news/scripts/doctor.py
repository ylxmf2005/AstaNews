# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "feedparser", "pyyaml"]
# ///
"""asta-news 健康检查 / 初始化

检查：运行时依赖、数据目录、代理、注册表、P0 源抽样、RSSHub、去重库。
--fix：创建数据目录并从 plugin assets 拷贝模板（不覆盖已有文件），幂等。

用法:
  doctor.py [--fix] [--probe-n 3]
"""
import argparse
import os
import random
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_sources as F  # noqa: E402

ASSETS = F.PLUGIN_ROOT / "skills" / "setup" / "assets"
RESULTS: list[tuple[str, str, str]] = []  # (level, name, detail)


def check(name: str, ok: bool, detail: str, warn_only: bool = False):
    level = "OK" if ok else ("WARN" if warn_only else "FAIL")
    RESULTS.append((level, name, detail))


def detect_proxy_candidates() -> list[str]:
    """从 macOS 系统设置与常见端口找可能的代理"""
    candidates = []
    try:
        out = subprocess.run(["scutil", "--proxy"], capture_output=True, text=True, timeout=5).stdout
        host = port = None
        for line in out.splitlines():
            if "HTTPProxy" in line:
                host = line.split(":")[-1].strip()
            if "HTTPPort" in line:
                port = line.split(":")[-1].strip()
        if host and port:
            candidates.append(f"http://{host}:{port}")
    except Exception:
        pass
    candidates += [f"http://127.0.0.1:{p}" for p in (7890, 7897, 1087)]
    return list(dict.fromkeys(candidates))


def proxy_works(proxy: str) -> bool:
    try:
        r = requests.get("https://huggingface.co/api/daily_papers?limit=1",
                         proxies={"http": proxy, "https": proxy}, timeout=10,
                         headers={"User-Agent": F.UA})
        return r.status_code == 200
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true", help="创建数据目录、拷贝模板（不覆盖已有）")
    ap.add_argument("--probe-n", type=int, default=3, help="抽样验证的 P0 源数量")
    args = ap.parse_args()

    # 1. 依赖
    check("uv", shutil.which("uv") is not None, shutil.which("uv") or "未安装：https://docs.astral.sh/uv/")
    check("docker", shutil.which("docker") is not None,
          "可用（RSSHub 部署需要）" if shutil.which("docker") else "未安装——仅影响可选的 RSSHub 自部署", warn_only=True)

    # 2. 数据目录
    dd = F.data_dir()
    templates = {
        "profile.md": ASSETS / "profile.template.md",
        "rules.local.yaml": ASSETS / "rules.local.template.yaml",
    }
    if args.fix:
        for sub in ("runs/state", "archive"):
            (dd / sub).mkdir(parents=True, exist_ok=True)
        for dst_name, src in templates.items():
            dst = dd / dst_name
            if not dst.exists() and src.exists():
                shutil.copy(src, dst)
        if not (dd / "sources.local.yaml").exists():
            (dd / "sources.local.yaml").write_text("# 本地私有源，schema 见 plugin sources/_schema.md\nsources: []\n")
    check("数据目录", dd.exists(), f"{dd}" + ("" if dd.exists() else "（跑 --fix 创建）"))
    for fname in ("profile.md", "sources.local.yaml"):
        check(f"  {fname}", (dd / fname).exists(), str(dd / fname), warn_only=True)

    # 3. 去重库可写
    try:
        conn = sqlite3.connect(dd / "seen.db")
        conn.execute("CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY, url_norm TEXT, title TEXT, source TEXT, status TEXT, first_seen TEXT)")
        conn.close()
        check("seen.db", True, f"{dd/'seen.db'} 可写")
    except Exception as exc:
        check("seen.db", False, str(exc))

    # 4. 代理
    proxy = os.environ.get("ASTA_PROXY")
    if proxy:
        check("ASTA_PROXY", proxy_works(proxy), f"{proxy}" + ("" if proxy_works(proxy) else " 无法访问 huggingface.co"))
    else:
        found = next((c for c in detect_proxy_candidates() if proxy_works(c)), None)
        check("ASTA_PROXY", found is not None,
              f"未设置；探测到可用代理 {found}，建议 export ASTA_PROXY={found}" if found
              else "未设置且未探测到可用代理——needs_proxy 源（HF/Gemini/Mistral 等）将被跳过", warn_only=True)

    # 5. 注册表
    try:
        sources = F.load_registry(F.PLUGIN_ROOT / "sources")
        enabled = [s for s in sources if s.get("enabled", True)]
        check("注册表", len(sources) > 0, f"{len(sources)} 源（启用 {len(enabled)}）")
    except Exception as exc:
        check("注册表", False, str(exc))
        sources, enabled = [], []

    # 6. P0 源抽样（直连可达的优先，避免被代理问题污染抽样）
    pool = [s for s in enabled if s.get("priority") == "P0"
            and s["type"] != "html" and not s.get("needs_proxy") and s["type"] != "rsshub"]
    for s in random.sample(pool, min(args.probe_n, len(pool))):
        status, items, detail = F.fetch_source(s, datetime.now(timezone.utc) - timedelta(days=30))
        check(f"P0 抽样 {s['id']}", status == "ok" and len(items) > 0, detail)

    # 7. RSSHub
    base = os.environ.get("ASTA_RSSHUB", "http://127.0.0.1:1200")
    try:
        ok = requests.get(f"{base}/healthz", timeout=5).status_code == 200
        check("RSSHub", ok, f"{base} healthz")
    except Exception:
        check("RSSHub", False,
              f"{base} 不可达——rsshub 源（X/Anthropic/量子位）将不可用；部署见 asta-news:setup", warn_only=True)

    # 输出
    width = max(len(n) for _, n, _ in RESULTS)
    fails = 0
    for level, name, detail in RESULTS:
        icon = {"OK": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[level]
        print(f"{icon} {name:<{width}}  {detail}")
        fails += (level == "FAIL")
    print(f"\n{'全部通过' if fails == 0 else f'{fails} 项失败'}（⚠️ 为可选能力，不阻塞）")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
