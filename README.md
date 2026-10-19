# 塔科夫信息检索系统（Tarkov Info）

塔科夫（Escape from Tarkov）**物资 / 价格 / 任务查询** 信息检索项目。

后端定时抓取社区数据源，存入本地 SQLite，前端提供搜索界面。

## 功能

- 🔍 物资搜索：中文名 / 英文原名（normalizedName）双向搜索，支持前缀/子串匹配
- 💰 价格查询：跳蚤 24h 均价、最低/最高价、48h 涨跌幅、商人收购/出售价
- 📦 物品详情：格子尺寸、重量、分类、跳蚤等级、跳蚤链接、Wiki 链接
- 🎯 用途查询：物品的任务需求 / 兑换 / 合成 / 藏身处升级（中文）
- 📋 任务查询：503 个任务，含目标/奖励/商人/地图，中英文模糊搜索
- ⏱️ 定时同步：物品价格 + 任务按间隔自动刷新（可配置、防重入）

## 技术栈

- **后端**：Node.js 24 + Express
- **存储**：`node:sqlite`（Node 内置 SQLite，无需原生编译）
- **前端**：原生 HTML/CSS/JS（无构建步骤）
- **数据源**：[json.tarkov.dev](https://json.tarkov.dev)（社区维护，免 API Key）

## 目录结构

```
tarkov-info/
├── src/
│   ├── server.js        # Express 入口
│   ├── config.js        # 配置（端口、DB 路径、数据源 URL）
│   ├── db.js            # SQLite 连接与表结构
│   ├── fetcher.js       # tarkov.dev 抓取
│   ├── queries.js       # 搜索/详情/用途查询
│   ├── routes/
│   │   └── api.js       # REST API 路由
│   └── jobs/
│       ├── sync.js      # tarkov.dev 全量同步任务
│       └── import_zh.js # 中文数据集导入（中文名 + 用途）
├── public/              # 前端静态资源
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/                # 运行时数据
│   ├── seed/            # 种子数据（纳入版本控制）
│   │   └── items_zh.json # 中文名 + 用途数据集
│   └── tarkov.db        # SQLite 数据库（运行时生成，已 gitignore）
├── package.json
└── .env.example
```

## 快速开始

```bash
# 1. 安装依赖
pnpm install

# 2. 启动（首次自动同步物品+任务，之后按间隔定时刷新）
pnpm dev

# 3. 导入中文名 + 用途数据（若首次未自动导入）
node src/jobs/import_zh.js data/seed/items_zh.json

# 4. 打开浏览器
# http://127.0.0.1:3000
```

## 配置（环境变量，可写入 .env）

| 变量 | 默认 | 说明 |
|------|------|------|
| `PORT` | 3000 | 服务端口 |
| `SYNC_INTERVAL_SECONDS` | 600 | 自动同步间隔（秒） |
| `DISABLE_AUTO_SYNC` | 0 | 设 1 禁用定时同步 |
| `DB_PATH` | ./data/tarkov.db | 数据库路径 |

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（物品数、任务数、同步状态） |
| GET | `/api/items/search?q=<关键词>` | 搜索物品（中/英文名） |
| GET | `/api/items/:id` | 物品详情（含用途） |
| GET | `/api/usage/search?q=<任务名>` | 反查用途（按任务名找相关物品） |
| GET | `/api/tasks?q=<关键词>&trader=<id>` | 任务列表 / 搜索 / 按商人筛选 |
| GET | `/api/tasks/traders` | 任务商人统计 |
| GET | `/api/tasks/:id` | 任务详情 |
| GET | `/api/sync/status` | 同步状态（进行中/上次结果/间隔） |
| POST | `/api/sync` | 手动触发全量同步 |
| POST | `/api/sync/tasks` | 手动触发任务同步 |

## 数据源说明

- **物品/价格**：`https://json.tarkov.dev/regular/items`（免鉴权 JSON 快照，约 17MB）
- **任务**：`https://json.tarkov.dev/regular/tasks`（503 个任务结构化数据）
- **中文名/用途**：社区中文数据集（`data/seed/items_zh.json`，来源 astrbot_plugin_tarkov_market），
  覆盖 4235 件物品的中文名与 11856 条用途记录（任务需求/兑换/合成/藏身处升级）

## 已知限制

- 本机 `hosts` 被 Watt Toolkit / Steam++ 劫持，`github.com` 等域名指向 `127.0.0.1`；
  后端使用 Node 原生 `fetch`，可正常访问 `json.tarkov.dev`（不依赖被劫持域名）。
- pnpm 需使用 `nodeLinker: hoisted`（扁平化），否则 Windows 沙箱下符号链接失效。
