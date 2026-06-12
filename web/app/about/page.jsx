import { SITE } from "../../lib/config";

export const metadata = { title: "关于 · AstaNews" };

export default function About() {
  return (
    <div style={{ maxWidth: 720 }}>
      <div className="dateline">关于 AstaNews</div>
      <p className="deck">AI 全栈每日情报：从论文、模型发布、评测、infra/serving、MaaS、agent、具身、安全、产品商业、devtool 共 13 个 stack layer，层层筛选，多视角呈现。</p>
      <div className="story" style={{ gridTemplateColumns: "1fr" }}>
        <div className="body">
{`三级筛选：完整级（当天全部候选）→ 日报级（约 20 条，全栈覆盖）→ 群聊级（5-8 条精选，微信群发）。

多视角：同一批新闻，按受众重排——全栈 / 技术 / 产品 / 商业 / 研究 / 具身。

抓取与去重由确定性脚本完成；筛选、评分与撰写由 agent 按编辑准则裁决；本地 embedding 支持语义检索，不强依赖闭源 API。

数据源开放贡献，每天由 GitHub Actions 自动产出、提交、部署。`}
        </div>
        <div className="links" style={{ gridColumn: 1 }}>
          <a href={`https://github.com/${SITE.repo}`} target="_blank" rel="noopener">GitHub 仓库</a>
        </div>
      </div>
    </div>
  );
}
