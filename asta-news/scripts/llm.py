# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "pyyaml"]
# ///
"""asta-news 小模型 client（OpenAI 兼容接口）——分类/初筛的可选薄层。

DeepSeek / 通义 / 智谱 / ollama 全是 `/v1/chat/completions`，脚本只对这一个接口
编程，base_url+model+api_key 全进 `config/llm.yaml` 与 .env：
  生产默认 → 国产便宜云 API；  自测 → 本机 ollama（http://localhost:11434/v1，无需 key）

设计铁律：**不可用即优雅退化**。enabled=false / 无 key / 连不上 / 返回非 JSON →
`chat_json` 一律返回 None，调用方据此走纯确定性路径，pipeline 永不硬依赖 LLM。

库优先用法：
  import llm
  if llm.available(): llm.chat_json("你是分类器", "...")  # -> dict | None
命令行：
  llm.py --self-test          # 配置解析 + 优雅退化（无服务也 PASS）
  llm.py --ping "你好"        # 真打一次（需配好 base_url/key 或本地 ollama）
环境覆盖：ASTA_LLM_BASE_URL / ASTA_LLM_MODEL / ASTA_LLM_KEY
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config" / "llm.yaml"
_cfg = None


def config() -> dict:
    """读 config/llm.yaml，环境变量覆盖三要素。失败/缺文件 → 安全默认（disabled）。"""
    global _cfg
    if _cfg is not None:
        return _cfg
    try:
        c = yaml.safe_load(CONFIG.read_text()) or {}
    except OSError:
        c = {}
    c["base_url"] = os.environ.get("ASTA_LLM_BASE_URL", c.get("base_url", "")).rstrip("/")
    c["model"] = os.environ.get("ASTA_LLM_MODEL", c.get("model", ""))
    c.setdefault("api_key_env", "ASTA_LLM_KEY")
    c.setdefault("enabled", False)
    c.setdefault("temperature", 0)
    c.setdefault("timeout", 30)
    c.setdefault("max_tokens", 1024)
    _cfg = c
    return c


def api_key() -> str:
    c = config()
    # 显式 ASTA_LLM_KEY 优先；否则取 config 指定的 env 名。ollama 等本地服务无需 key。
    return os.environ.get("ASTA_LLM_KEY") or os.environ.get(c["api_key_env"], "")


def available() -> bool:
    """是否配置可用（enabled 且有 base_url；云端还需 key，localhost 放行）。"""
    c = config()
    if not c.get("enabled") or not c.get("base_url"):
        return False
    is_local = "localhost" in c["base_url"] or "127.0.0.1" in c["base_url"]
    return bool(is_local or api_key())


def _extract_json(text: str):
    """从模型回复里抠出 JSON：先剥 ```json 围栏，再退化到首个 {…}/[…] 片段。"""
    if not text:
        return None
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", t, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                return None
    return None


def chat_json(system: str, user: str, retries: int = 2):
    """调一次 chat completion 要 JSON，解析成 dict/list。任何失败 → None（不抛）。"""
    if not available():
        return None
    c = config()
    url = c["base_url"] + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    key = api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": c["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": c["temperature"],
        "max_tokens": c["max_tokens"],
        "response_format": {"type": "json_object"},
    }
    for attempt in range(retries):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=c["timeout"])
            if r.status_code == 400 and "response_format" in payload:
                payload.pop("response_format")  # 某些供应商不支持 → 去掉重试，靠文本抠 JSON
                continue
            if not r.ok:
                if attempt == retries - 1:
                    print(f"  llm: HTTP {r.status_code} {r.text[:120]}", file=sys.stderr)
                continue
            content = r.json()["choices"][0]["message"]["content"]
            return _extract_json(content)
        except (requests.RequestException, KeyError, ValueError) as e:
            if attempt == retries - 1:
                print(f"  llm: 调用失败（退化为纯确定性）：{e}", file=sys.stderr)
    return None


def cmd_self_test() -> int:
    # 1) 配置可解析、三要素就位
    c = config()
    assert "base_url" in c and "model" in c, "配置缺字段"
    print(f"  配置：enabled={c['enabled']} base_url={c['base_url'] or '(空)'} model={c['model'] or '(空)'} available={available()}")
    # 2) JSON 抠取（围栏 / 裸 JSON / 噪声包裹）
    assert _extract_json('```json\n{"layer":"model"}\n```') == {"layer": "model"}
    assert _extract_json('{"a":1}') == {"a": 1}
    assert _extract_json('好的，结果是 [{"id":"x"}] 完毕') == [{"id": "x"}]
    assert _extract_json("不是 json") is None
    print("  JSON 抠取：围栏/裸/噪声/非法 4 例 PASS")
    # 3) 优雅退化：临时指向不可达端点 → chat_json 必返 None，不抛
    global _cfg
    _cfg = {**c, "enabled": True, "base_url": "http://127.0.0.1:59999/v1", "model": "x",
            "api_key_env": "ASTA_LLM_KEY", "temperature": 0, "timeout": 2, "max_tokens": 8}
    os.environ["ASTA_LLM_KEY"] = "dummy"
    assert chat_json("sys", "user") is None, "不可达端点应优雅返回 None"
    print("  优雅退化：不可达端点返回 None（不抛）PASS")
    _cfg = None
    print("self-test: llm client PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--self-test", action="store_true")
    g.add_argument("--ping", metavar="MSG", help="真打一次，要求返回 {\"echo\": <原话>}")
    args = ap.parse_args()
    if args.self_test:
        return cmd_self_test()
    if args.ping:
        if not available():
            print("LLM 不可用（检查 config/llm.yaml 的 enabled/base_url 与 .env 的 key；本地可用 ollama）", file=sys.stderr)
            return 1
        out = chat_json('只返回 JSON：{"echo": <把用户原话原样填这>}', args.ping)
        print(json.dumps(out, ensure_ascii=False))
        return 0 if out else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
