// 构建期数据读取（server components / generateStaticParams）。从仓库 site/data 读。
import { readdirSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const DATA_DIR = join(process.cwd(), "..", "site", "data");
const isEdition = (f) => /^20\d\d-\d\d-\d\d\.json$/.test(f);

export function allDates() {
  if (!existsSync(DATA_DIR)) return [];
  return readdirSync(DATA_DIR).filter(isEdition).map((f) => f.replace(".json", "")).sort().reverse();
}

export function getEdition(date) {
  const p = join(DATA_DIR, `${date}.json`);
  if (!existsSync(p)) return null;
  return JSON.parse(readFileSync(p, "utf8"));
}

export function latestEdition() {
  const dates = allDates();
  return dates.length ? getEdition(dates[0]) : null;
}

export function editionIndex() {
  return allDates().map((date) => {
    const d = getEdition(date);
    return {
      date, weekday: d.weekday || "", headline: d.headline || "", overview: d.overview || "",
      layers: d.stats?.layers_covered || [],
      group: (d.tiers?.group || d.selected || []).length,
      daily: (d.tiers?.daily || []).length,
      candidates: d.stats?.candidates ?? (d.all_candidates || []).length,
    };
  });
}

// 规范化为统一 tiers 视图（兼容 v1：无 tiers 时用 selected/all_candidates 回填）
export function normalizeTiers(d) {
  if (d.tiers) return d.tiers;
  return {
    group: d.selected || [],
    daily: d.selected || [],
    full: d.all_candidates || [],
  };
}
