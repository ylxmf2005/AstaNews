# AstaNews 控制台后端（services/）

网站即一切入口的后端。静态 Pages 模式只读（前端直读 `site/data` + 浏览器内检索）；本地跑这个服务则解锁**服务端语义检索 + 配置编辑 + 触发运行**。

```bash
uv run services/app.py          # http://127.0.0.1:8799 ，访问 /docs 看 OpenAPI
```
零安装（PEP 723 内联依赖：fastapi/uvicorn/fastembed/numpy/pyyaml）。

## 端点

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 健康 + 期数 |
| GET | `/api/editions` | 列期（index） |
| GET | `/api/editions/{date}` | 取某期完整 JSON |
| GET | `/api/search?q=&top=` | **服务端语义检索**（fastembed 同款模型 + 向量索引 + 关键词融合，跨语言；解决静态站浏览器加载模型的问题） |
| GET | `/api/sources` | 源注册表概览（112 源） |
| GET | `/api/config` | 读全部模块化配置（tiers/perspectives/sharpness/site/search/rules） |
| PUT | `/api/config/{name}` | 写配置（yaml 校验）— 网站控制台编辑入口 |
| POST | `/api/run/fetch` | 触发抓取（确定性部分，安全可从网站点）；完整 digest=claude headless / 5am cron |

## 账号/鉴权（预留）

`require_auth` 钩子已埋好：设 `ASTA_API_TOKEN` 则写操作需 `Authorization: Bearer <token>`；未设=本地放行。
将来网站控制台接入账号体系时，把它换成真实校验即可，端点不用改。

## 模式

- **静态/公开**（GitHub Pages）：前端只读，不依赖本服务。
- **本地/全功能**：`web/` 配 `NEXT_PUBLIC_API` 指向本服务，搜索/配置/触发走后端。
（web 控制台 UI 见 ROADMAP P3-WEBCTRL，迭代中。）
