# /// script
# requires-python = ">=3.10"
# dependencies = ["fastembed", "numpy", "pyyaml"]
# ///
"""asta-news 分类（layer 标签）——embedding 零样本 + 源先验，零 LLM。

把贵 agent 的"逐条分层"下放成脚本：复用本地 fastembed（与语义检索同一模型，
离线 CPU、hf-mirror），给 13 个 stack layer 各一句中英原型描述、嵌成锚向量；
候选嵌入后对锚算余弦，融合候选自带的源声明 `layers[]`（免费先验）定最终层。

输入/输出：jsonl，每行一个候选（含 title/summary，候选若带 layers[] 即源先验）。
每条加：
  layer            最终单层（argmax）
  layers_ranked    [[layer, score], …] top-3
  layer_conf       top1−top2 边际（低=拿不准）
  cross_stack      次层也够强 → 牵动 2+ 层
  layer_uncertain  layer_conf < 阈值 → 供 LLM 兜底或 agent 复核

退化：fastembed 不可用 → 用源声明的首个 layer（仍可跑）。

用法:
  classify.py --in fresh.jsonl --out classified.jsonl
  classify.py --self-test
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

# 13 层规范 key（对齐 rules.yaml）→ 中英混合原型描述（关键词密集，零样本判别力来源）
PROTOTYPES = {
    "model": "基础模型发布 预训练大模型 新模型权重开源 foundation model release pretrained LLM new open weights base model GPT Llama Qwen DeepSeek Gemini Claude Mistral",
    "post-training": "后训练 对齐 指令微调 强化学习对齐 偏好优化 post-training alignment RLHF DPO fine-tuning instruction tuning reward model preference optimization distillation",
    "eval": "评测 基准测试 榜单 排行榜 测试集 benchmark evaluation leaderboard SWE-bench MMLU GPQA accuracy score pass@k test set arena",
    "data": "数据集 训练语料 数据合成 数据清洗 标注 dataset training corpus synthetic data data curation tokens pretraining data filtering",
    "infra": "训练基建 GPU 集群 分布式训练 并行 算力 infrastructure GPU cluster distributed training CUDA kernel parallelism training stack H100 interconnect",
    "serving": "推理服务 吞吐优化 部署 量化 推理框架 inference serving throughput latency vLLM SGLang TensorRT KV cache quantization batching deployment",
    "maas": "模型即服务 API 定价 云端模型接口 托管推理 model as a service API pricing hosted model endpoint cloud inference API token cost platform",
    "agent": "智能体 工具调用 自主规划 多智能体 工作流 AI agent tool use function calling autonomous planning multi-agent agentic workflow orchestration",
    "embodied": "具身智能 机器人 人形机器人 操作 视觉语言动作 embodied AI robot humanoid manipulation locomotion vision-language-action VLA teleoperation",
    "safety": "AI 安全 对齐风险 越狱 红队 护栏 可解释性 误用 safety alignment risk jailbreak red team guardrail interpretability misuse adversarial",
    "product": "AI 产品 应用发布 消费级功能 面向用户 product launch app feature consumer AI user-facing assistant ChatGPT app rollout UX",
    "business": "融资 商业 估值 战略 收购 营收 市场 funding valuation business acquisition revenue market strategy partnership IPO investment",
    "devtool": "开发者工具 框架 SDK 库 IDE 编程助手 developer tool framework library SDK coding assistant API client plugin extension CLI",
}
LAYERS = list(PROTOTYPES)
SRC_PRIOR = 0.12        # 源声明命中该层时的加成（加在余弦上）
CROSS_ABS = 0.30        # 次层绝对相似度 ≥ 此值 → 视为跨层
UNCERTAIN_MARGIN = 0.04  # top1−top2 边际 < 此值 → 拿不准

_protos = None


def proto_vectors():
    global _protos
    if _protos is None:
        import embed
        _protos = embed.embed([PROTOTYPES[k] for k in LAYERS])  # 已 L2 归一
    return _protos


def text_of(c: dict) -> str:
    return f"{c.get('title', '')}. {c.get('summary', '') or c.get('text', '')}".strip()[:512]


def classify(cands: list[dict]) -> list[dict]:
    """原地给每条候选加分类字段，返回同一列表。"""
    if not cands:
        return cands
    try:
        import embed
        protos = proto_vectors()
        vecs = embed.embed([text_of(c) for c in cands])
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            sims = vecs @ protos.T  # (n, 13) 余弦（errstate 抑制 Apple BLAS 伪警告）
    except Exception as e:  # fastembed 不可用 → 源先验退化
        print(f"  classify: embedding 不可用，退化为源先验：{e}", file=sys.stderr)
        for c in cands:
            src = [l for l in (c.get("layers") or []) if l in PROTOTYPES]
            c["layer"] = src[0] if src else "model"
            c["layers_ranked"] = [[c["layer"], 0.0]]
            c["layer_conf"] = 0.0
            c["cross_stack"] = len(src) >= 2
            c["layer_uncertain"] = True
        return cands
    for c, sim in zip(cands, sims):
        src = set(l for l in (c.get("layers") or []) if l in PROTOTYPES)
        boosted = sim.copy()
        for i, lay in enumerate(LAYERS):
            if lay in src:
                boosted[i] += SRC_PRIOR
        order = np.argsort(-boosted)
        ranked = [[LAYERS[i], round(float(boosted[i]), 3)] for i in order[:3]]
        top1, top2 = order[0], order[1]
        c["layer"] = LAYERS[top1]
        c["layers_ranked"] = ranked
        c["layer_conf"] = round(float(boosted[top1] - boosted[top2]), 3)
        c["cross_stack"] = bool(sim[top2] >= CROSS_ABS)
        c["layer_uncertain"] = bool(c["layer_conf"] < UNCERTAIN_MARGIN)
    return cands


def cmd_self_test() -> int:
    samples = [
        ({"title": "Meta releases Llama 4 405B with open weights", "summary": "new foundation model, pretrained on 15T tokens", "layers": ["model"]}, "model"),
        ({"title": "vLLM 0.7 adds FP8 KV cache for 2x serving throughput", "summary": "inference engine optimization", "layers": ["serving"]}, "serving"),
        ({"title": "DPO-style preference optimization improves alignment", "summary": "post-training method, reward-free RLHF alternative", "layers": ["post-training"]}, "post-training"),
        ({"title": "SWE-bench Verified leaderboard updated with new agents", "summary": "coding benchmark results, pass rate", "layers": ["eval"]}, "eval"),
        ({"title": "Figure 02 humanoid robot autonomous manipulation demo", "summary": "embodied vision-language-action", "layers": ["embodied"]}, "embodied"),
        ({"title": "Anthropic raises $4B at $60B valuation", "summary": "funding round led by investors", "layers": ["business"]}, "business"),
    ]
    cands = [dict(s[0]) for s in samples]
    classify(cands)
    ok = 0
    for c, (_, want) in zip(cands, samples):
        hit = c["layer"] == want
        ok += hit
        print(f"  {'✓' if hit else '✗'} 期望 {want:14s} 得 {c['layer']:14s} conf={c['layer_conf']:+.3f} cross={c['cross_stack']}  «{c['title'][:42]}»")
    print(f"self-test: 分类 {ok}/{len(samples)} 正确")
    assert ok >= len(samples) - 1, "零样本分类正确率过低（容许 1 错）"
    print("PASS")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", help="候选 jsonl")
    ap.add_argument("--out", help="输出 jsonl（默认覆盖 --in）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return cmd_self_test()
    if not args.inp:
        ap.error("需要 --in 或 --self-test")
    cands = [json.loads(l) for l in Path(args.inp).read_text().splitlines() if l.strip()]
    classify(cands)
    out = Path(args.out or args.inp)
    out.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cands) + "\n")
    uncertain = sum(1 for c in cands if c.get("layer_uncertain"))
    print(f"分类 {len(cands)} 条 → {out}（{uncertain} 条拿不准待复核）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
