# 塔科夫信息检索系统（Tarkov Info）

塔科夫（Escape from Tarkov）**物资 / 价格查询** 信息检索项目。

后端定时抓取社区数据源，存入本地 SQLite，前端提供搜索界面。

## 功能

- 🔍 物资搜索：按英文原名（normalizedName）模糊搜索，支持前缀/子串匹配
- 💰 价格查询：跳蚤 24h 均价、最低/最高价、48h 涨跌幅、商人收购/出售价
- 📦 物品详情：格子尺寸、重量、分类、跳蚤等级、跳蚤链接、Wiki 链接

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
│   ├── queries.js       # 搜索/详情查询
│   ├── routes/
│   │   └── api.js       # REST API 路由
│   └── jobs/
│       └── sync.js      # 全量同步任务
├── public/              # 前端静态资源
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/                # SQLite 数据库（运行时生成，已 gitignore）
├── package.json
└── .env.example
```

## 快速开始

```bash
# 1. 安装依赖
pnpm install

# 2. 启动（首次会自动同步全量物品数据）
pnpm dev

# 3. 打开浏览器
# http://127.0.0.1:3000
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（物品数、同步时间） |
| GET | `/api/items/search?q=<关键词>` | 搜索物品 |
| GET | `/api/items/:id` | 物品详情 |
| POST | `/api/sync` | 手动触发全量同步 |

## 数据源说明

- 实时价格与物品数据来自 `https://json.tarkov.dev/regular/items`（免鉴权 JSON 快照，约 17MB）
- 中文名暂未接入（`items_zh` 端点当前为英文）；后续可接入 Tarkov Wiki 或社区中文数据表

## 已知限制

- 本机 `hosts` 被 Watt Toolkit / Steam++ 劫持，`github.com` 等域名指向 `127.0.0.1`；
  后端使用 Node 原生 `fetch`，可正常访问 `json.tarkov.dev`（不依赖被劫持域名）。
- pnpm 需使用 `nodeLinker: hoisted`（扁平化），否则 Windows 沙箱下符号链接失效。
