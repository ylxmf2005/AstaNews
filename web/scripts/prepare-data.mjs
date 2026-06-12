// 构建前数据准备：把仓库 site/data 的每日 JSON 拷进 web/public/data，
// 并生成 editions 索引 + 全站搜索语料（关键词搜索用）。Node 原生，无依赖。
import { readdirSync, readFileSync, mkdirSync, writeFileSync, copyFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = join(root, "..", "site", "data");
const pubDir = join(root, "public", "data");
mkdirSync(pubDir, { recursive: true });

const isEdition = (f) => /^20\d\d-\d\d-\d\d\.json$/.test(f);
const files = existsSync(srcDir) ? readdirSync(srcDir).filter(isEdition).sort().reverse() : [];

// 相关新闻（向量近邻，预计算）——若存在则带上
if (existsSync(join(srcDir, "related.json"))) copyFileSync(join(srcDir, "related.json"), join(pubDir, "related.json"));

const index = [];
const corpus = [];
for (const f of files) {
  const d = JSON.parse(readFileSync(join(srcDir, f), "utf8"));
  copyFileSync(join(srcDir, f), join(pubDir, f));
  const layers = d.stats?.layers_covered || [];
  index.push({
    date: d.date, weekday: d.weekday || "", headline: d.headline || "",
    overview: d.overview || "", layers,
    group: (d.tiers?.group || d.selected || []).length,
    daily: (d.tiers?.daily || []).length,
    candidates: d.stats?.candidates ?? (d.all_candidates || []).length,
  });
  // 搜索语料：精选 + 日报 + 全部候选（轻量）
  const seen = new Set();
  const push = (id, title, body, url, layer, tier) => {
    if (!id || seen.has(id)) return; seen.add(id);
    corpus.push({ id, date: d.date, title, body: (body || "").slice(0, 200), url, layer, tier });
  };
  for (const it of d.tiers?.group || d.selected || [])
    push(it.id, it.title, it.readable || (it.facts || []).join(" "), it.links?.primary, lz(it.layer), "group");
  for (const it of d.tiers?.daily || [])
    push(it.id, it.title, it.take || it.readable, it.links?.primary, lz(it.layer), "daily");
  for (const c of d.all_candidates || [])
    push(`${c.source}:${c.url}`, c.title, c.summary, c.url, lz(c.layer), "full");
}
function lz(l) { return Array.isArray(l) ? l[0] : l || ""; }

writeFileSync(join(pubDir, "index.json"), JSON.stringify({ editions: index }));
writeFileSync(join(pubDir, "corpus.json"), JSON.stringify({ items: corpus }));
console.log(`prepare-data: ${files.length} editions, ${corpus.length} corpus items → public/data`);
