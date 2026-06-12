# /// script
# requires-python = ">=3.10"
# dependencies = ["fastapi", "uvicorn", "pyyaml", "fastembed", "numpy"]
# ///
"""AstaNews 控制台后端（本地/全功能模式）。

网站即一切入口的后端：列期/取期、服务端语义检索、读写配置、触发运行。
静态 Pages 模式只读（前端直读 site/data + 浏览器内检索）；本地连上本服务则解锁
真·服务端语义检索 + 配置编辑 + 触发。账号体系预留 require_auth 钩子（现为放行）。

跑：  uv run services/app.py            # http://127.0.0.1:8799 ，/docs 看 OpenAPI
环境：ASTA_API_TOKEN 设了则需 Authorization: Bearer <token>（未设=本地放行）
      ASTA_OUTPUT_DIR 默认仓库 site/
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "asta-news"
DATA = Path(os.environ.get("ASTA_OUTPUT_DIR", REPO / "site")) / "data"
CONFIG = PLUGIN / "config"
SCRIPTS = PLUGIN / "scripts"
sys.path.insert(0, str(SCRIPTS))

app = FastAPI(title="AstaNews Console API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---- 账号/鉴权（预留；ASTA_API_TOKEN 未设则放行，便于本地） ----
def require_auth(authorization: str = Header(default="")):
    token = os.environ.get("ASTA_API_TOKEN")
    if not token:
        return {"user": "local"}
    if authorization != f"Bearer {token}":
        raise HTTPException(401, "需要 Authorization: Bearer <ASTA_API_TOKEN>")
    return {"user": "token"}


# ---- 只读：列期 / 取期 ----
@app.get("/api/health")
def health():
    return {"ok": True, "data_dir": str(DATA), "editions": _dates().__len__()}


def _dates():
    return sorted((f.stem for f in DATA.glob("20*.json") if f.name != "index.json"), reverse=True)


@app.get("/api/editions")
def editions():
    idx = DATA / "index.json"
    if idx.exists():
        return json.loads(idx.read_text())
    return {"editions": [{"date": d} for d in _dates()]}


@app.get("/api/editions/{date}")
def edition(date: str):
    f = DATA / f"{date}.json"
    if not f.exists():
        raise HTTPException(404, f"无此期 {date}")
    return JSONResponse(json.loads(f.read_text()))


# ---- 服务端语义检索（解决静态站浏览器模型加载问题） ----
@app.get("/api/search")
def search(q: str = Query(..., min_length=1), top: int = 12):
    try:
        import embed
        idx = DATA / "vectors.npz"
        if not idx.exists():
            raise FileNotFoundError("vectors.npz 不存在，先 embed.py --build")
        sem = embed.search(q, idx, top * 2)
    except Exception as e:
        raise HTTPException(503, f"语义索引不可用：{e}")
    # 关键词加权融合
    ql = q.lower()
    for r in sem:
        r["score"] = r["score"] + (0.06 if ql in (r.get("title", "").lower()) else 0)
    sem.sort(key=lambda r: -r["score"])
    return {"query": q, "results": sem[:top]}


# ---- 配置：读 / 写（网站控制台编辑 tiers/perspectives/rules…） ----
@app.get("/api/config")
def list_config():
    out = {}
    for f in sorted(CONFIG.glob("*.yaml")):
        out[f.stem] = yaml.safe_load(f.read_text())
    out["rules"] = yaml.safe_load((PLUGIN / "rules.yaml").read_text())
    return out


@app.put("/api/config/{name}")
def write_config(name: str, body: dict, _=Depends(require_auth)):
    target = (PLUGIN / "rules.yaml") if name == "rules" else (CONFIG / f"{name}.yaml")
    if not target.exists():
        raise HTTPException(404, f"无此配置 {name}")
    try:
        yaml.safe_dump(body, sort_keys=False, allow_unicode=True)  # 校验可序列化
    except Exception as e:
        raise HTTPException(400, f"非法 yaml：{e}")
    target.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True))
    return {"ok": True, "wrote": str(target)}


# ---- 源注册表概览 ----
@app.get("/api/sources")
def sources():
    items = []
    for f in (PLUGIN / "sources").glob("*.yaml"):
        for s in (yaml.safe_load(f.read_text()) or {}).get("sources", []):
            items.append({"id": s["id"], "layers": s.get("layers"), "priority": s.get("priority"),
                          "enabled": s.get("enabled", True), "type": s.get("type")})
    return {"count": len(items), "enabled": sum(1 for i in items if i["enabled"]), "sources": items}


# ---- 触发：抓取（确定性部分，安全可从网站点）。完整 digest=claude headless，另文档 ----
@app.post("/api/run/fetch")
def run_fetch(_=Depends(require_auth)):
    p = subprocess.Popen(["uv", "run", str(SCRIPTS / "fetch_sources.py")],
                         cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "pid": p.pid, "note": "已后台启动抓取；完整 digest（评分/改写）由 claude headless 或 5am cron 跑"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("ASTA_API_PORT", 8799)))
