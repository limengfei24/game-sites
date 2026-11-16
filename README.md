# 游戏新词自动建站

照着「新词新站」的思路全自动跑：每 4 小时从 Google Trends 找刚开始飙升的游戏词 → AI 判断是不是具体的新游戏 → 检查词龄和竞争 → 汇总 Steam / Roblox / 维基百科 / YouTube 资料让 AI 写页面 → 生成 `<游戏>.many.pw` 子域名站 → 部署到 Vercel → 通知搜索引擎。

子域名靠 Vercel 的通配符域名 `*.many.pw` 自动生效，不需要逐个配置解析。

## 流程

| 步骤 | 代码 | 说明 |
| --- | --- | --- |
| 找词 | `pipeline/trends.py` | 每日热搜 RSS + 「游戏」分类下种子词的飙升相关搜索 |
| 判断 | `pipeline/classify.py` | AI 过滤掉体育、明星、泛词，只留具体游戏 |
| 筛选 | `pipeline/main.py` | 词火了超过 30 天放弃；谷歌前 10 已有 ≥3 个专门站放弃（需 Serper） |
| 写内容 | `pipeline/sources.py`、`content.py` | 只基于找到的资料写，找不到资料就跳过 |
| 建站 | `pipeline/builder.py`、`templates/` | 静态页 + sitemap + robots + 结构化数据，按 Host 路由到各游戏目录 |
| 上线 | `pipeline/vercel_api.py`、Actions | 首次运行把 `many.pw`、`www`、`*.many.pw` 绑定到 Vercel 项目 |

所有关键词的状态记录在 `data/state.json`，生成的游戏数据在 `data/games/`，由 Actions 自动提交回仓库。

## 一次性配置

1. **Vercel**：新建一个空项目（Framework 选 Other），拿到 Project ID、Team/账号 ID，并创建 Token。项目里开启 Web Analytics 即可看访问量。
2. **域名 DNS**：在域名注册商（阿里云）把 `many.pw` 的 DNS 服务器改为 `ns1.vercel-dns.com`、`ns2.vercel-dns.com`。只改这一次。
3. **AI**：DeepSeek 开放平台创建 API Key（也可以换任何 OpenAI 兼容接口，改 `LLM_BASE_URL` / `LLM_MODEL`）。
4. **GitHub**：把本目录推到一个仓库，在 Settings → Secrets and variables → Actions 里添加 `.env.example` 里列的变量。
5. Actions 页面手动点一次 `game-sites` → Run workflow 试跑。

可选：`SERPER_API_KEY`（竞争检查）、`INDEXNOW_KEY`（Bing 快速收录）、`YOUTUBE_COOKIES`（抓 YouTube 字幕）。
谷歌收录：在 Google Search Console 用「网域」方式验证 `many.pw` 一次（在 Vercel 的 DNS 里加 TXT），所有子域名都会包含在内。

## 本地运行

```powershell
pip install -r requirements.txt
copy .env.example .env   # 填好变量
python -m pipeline.main run --dry-run   # 不绑定 Vercel 域名
python -m pipeline.main build           # 只重新生成 dist/
python -m pipeline.main domains         # 只绑定域名
```
