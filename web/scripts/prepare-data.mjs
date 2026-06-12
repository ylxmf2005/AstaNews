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

// 相关新闻（向量近邻）+ 浏览器语义搜索索引（vectors.bin/search.json）——若存在则带上
for (const f of ["related.json", "vectors.bin", "search.json"])
  if (existsSync(join(srcDir, f))) copyFileSync(join(srcDir, f), join(pubDir, f));

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

// Atom 订阅 feed：最近若干期的精选(group)，可在任意 RSS 阅读器订阅
const SITE = "https://ylxmf2005.github.io/AstaNews";
const esc = (s) => String(s || "").replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
const feedItems = [];
for (const f of files.slice(0, 14)) {
  const d = JSON.parse(readFileSync(join(srcDir, f), "utf8"));
  for (const it of (d.tiers?.group || d.selected || [])) {
    const body = (it.readable || it.take || "").split("\n\n")[0];
    feedItems.push(
      `  <entry>\n    <title>${esc(it.title)}</title>\n` +
      `    <link href="${esc(it.links?.primary || SITE)}"/>\n` +
      `    <id>${SITE}/edition/${d.date}#${esc((it.links?.primary || it.title).slice(0, 60))}</id>\n` +
      `    <updated>${d.date}T08:00:00Z</updated>\n` +
      `    <category term="${esc(Array.isArray(it.layer) ? it.layer[0] : it.layer)}"/>\n` +
      `    <summary>${esc(body)}</summary>\n  </entry>`);
  }
}
const feed =
  `<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">\n` +
  `  <title>AstaNews · AI 全栈每日情报</title>\n  <link href="${SITE}/"/>\n` +
  `  <link rel="self" href="${SITE}/feed.xml"/>\n  <id>${SITE}/</id>\n` +
  `  <updated>${(index[0]?.date || "2026-01-01")}T08:00:00Z</updated>\n` +
  `  <subtitle>每天精选 AI 全栈进展（Asta Lab）</subtitle>\n` +
  feedItems.join("\n") + `\n</feed>\n`;
writeFileSync(join(root, "public", "feed.xml"), feed);
console.log(`prepare-data: ${files.length} editions, ${corpus.length} corpus, ${feedItems.length} feed entries → public/`);
