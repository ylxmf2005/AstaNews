// 前端用配置（镜像 asta-news/config/*.yaml；以 yaml 为准，改 yaml 时同步这里）。
export const SITE = {
  name: "AstaNews", tagline: "AI 全栈每日情报", lab: "Asta Lab",
  repo: "ylxmf2005/AstaNews",
};

export const LAYERS = {
  model: { name: "模型", emoji: "🧠", color: "#b23a23" },
  "post-training": { name: "后训练", emoji: "🎛️", color: "#9a7b32" },
  eval: { name: "评测", emoji: "📊", color: "#5b7a4a" },
  data: { name: "数据", emoji: "🗂️", color: "#7a6a4a" },
  infra: { name: "基建", emoji: "🏗️", color: "#4a6a7a" },
  serving: { name: "推理", emoji: "⚡", color: "#7a4a6a" },
  maas: { name: "MaaS", emoji: "☁️", color: "#4a7a7a" },
  agent: { name: "智能体", emoji: "🤖", color: "#8a5a2a" },
  embodied: { name: "具身", emoji: "🦾", color: "#5a5a8a" },
  safety: { name: "安全", emoji: "🛡️", color: "#8a3a3a" },
  product: { name: "产品", emoji: "📦", color: "#6a6a3a" },
  business: { name: "商业", emoji: "💰", color: "#a07820" },
  devtool: { name: "工具", emoji: "🔧", color: "#3a6a5a" },
};
export const lz = (l) => (Array.isArray(l) ? l[0] : l) || "";
export const layerName = (l) => LAYERS[lz(l)]?.name || lz(l);
export const layerEmoji = (l) => LAYERS[lz(l)]?.emoji || "";
export const layerColor = (l) => LAYERS[lz(l)]?.color || "#6a6150";

export const TIERS = [
  { key: "daily", label: "日报", desc: "约 20 条，全栈覆盖" },
  { key: "group", label: "精选", desc: "5-8 条，最严" },
  { key: "full", label: "全部", desc: "当天全部候选" },
];

export const PERSPECTIVES = [
  { key: "all", label: "全栈", boost: {} },
  { key: "technical", label: "技术", boost: { model: 1.5, "post-training": 1.5, infra: 1.2, serving: 1.2, eval: 1.0 } },
  { key: "product", label: "产品", boost: { product: 1.5, agent: 1.4, devtool: 1.3, maas: 1.2, model: 0.6 } },
  { key: "business", label: "商业", boost: { business: 1.8, product: 1.0, maas: 0.8, model: 0.5 } },
  { key: "research", label: "研究", boost: { eval: 1.4, model: 1.2, "post-training": 1.2, safety: 1.1, data: 1.1 } },
  { key: "embodied", label: "具身", boost: { embodied: 2.0, model: 0.6 } },
];

export const BASE = process.env.NEXT_PUBLIC_BASE_PATH || "";
export const asset = (p) => `${BASE}${p}`;

// URL → 稳定短 slug（Node 构建期与浏览器端结果一致，用于 item 详情页路由）
export function slug(url) {
  let h = 0;
  const s = url || "";
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h.toString(36);
}
