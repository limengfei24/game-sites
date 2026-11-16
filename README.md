# 游戏新词自动建站

照着「新词新站」的思路全自动跑：每 4 小时从 Google Trends 找刚开始飙升的游戏词 → AI 判断是不是具体的新游戏 → 检查词龄和竞争 → 汇总 Steam / Roblox / 维基百科 / YouTube 资料让 AI 写页面 → 生成 `<游戏>.<你的域名>` 子域名站 → 自动加阿里云 DNS 解析、绑定 Vercel → 部署 → 通知搜索引擎。

## 流程

| 步骤 | 代码 | 说明 |
| --- | --- | --- |
| 找词 | `pipeline/trends.py` | 每日热搜 RSS + 「游戏」分类下种子词的飙升相关搜索 |
| 判断 | `pipeline/classify.py` | AI 过滤掉体育、明星、泛词，只留具体游戏 |
| 筛选 | `pipeline/main.py` | 词火了超过 30 天放弃；谷歌前 10 已有 ≥3 个专门站放弃（需 Serper） |
| 写内容 | `pipeline/sources.py`、`content.py` | 只基于找到的资料写，找不到资料就跳过 |
| 建站 | `pipeline/builder.py`、`templates/` | 静态页 + sitemap + robots + 结构化数据 |
| 上线 | `aliyun_dns.py`、`vercel_api.py` | 阿里云加 CNAME，Vercel 绑定子域名 |

所有关键词的状态记录在 `data/state.json`，生成的游戏数据在 `data/games/`，由 Actions 自动提交回仓库。

## 一次性配置

1. **选主域名**：在 `config.yaml` 填 `base_domain`（阿里云账号里的闲置域名）。
2. **阿里云 AccessKey**：RAM 控制台新建子用户，只授权 `AliyunDNSFullAccess`，创建 AccessKey。
3. **AI**：阿里云百炼（DashScope）创建 API Key，默认模型 `qwen-plus`；也可以换任何 OpenAI 兼容接口。
4. **Vercel**：新建一个空项目（Framework 选 Other），在 Settings 里拿 Project ID，Account Settings → Tokens 建 Token；Team ID / 个人账号 ID 填到 `VERCEL_ORG_ID`。项目里开启 Web Analytics 即可看访问量。
5. **GitHub**：把本目录推到一个仓库，在 Settings → Secrets and variables → Actions 里添加 `.env.example` 里列的变量。
6. Actions 页面手动点一次 `game-sites` → Run workflow 试跑。

可选：`SERPER_API_KEY`（竞争检查）、`INDEXNOW_KEY`（Bing 快速收录）、`YOUTUBE_COOKIES`（抓 YouTube 字幕）。
谷歌收录：在 Google Search Console 用「网域」方式验证主域名一次，所有子域名都会包含在内。

## 本地运行

```powershell
pip install -r requirements.txt
copy .env.example .env   # 填好变量
python -m pipeline.main run --dry-run   # 不改 DNS、不绑定 Vercel
python -m pipeline.main build           # 只重新生成 dist/
```
