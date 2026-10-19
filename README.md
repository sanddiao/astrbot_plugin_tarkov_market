# 塔科夫信息检索系统（Tarkov Info）

逃离塔科夫（Escape from Tarkov）**物资 / 价格 / 用途 / 任务** 信息检索项目。

> 本仓库由早期的 `astrbot_plugin_tarkov_market`（AstroBot 物价查询插件）演进而来，现已扩展为两个独立可用的模块：
>
> 1. **Node.js Web 服务**：`src/` + `public/`，Express + SQLite 后端 + 浏览器搜索界面
> 2. **AstroBot 机器人插件**：`astrbot_plugin_tarkov_info/`，机器人指令 + Web Dashboard 面板
>
> 两者共享同一套 tarkov.dev 数据源，可单独部署，也可同时使用。

---

## 目录

- [项目总览](#项目总览)
- [功能特性](#功能特性)
- [数据源](#数据源)
- [一、Node.js Web 服务](#一nodejs-web-服务)
- [二、AstroBot 插件](#二astrobot-插件)
- [部署指南](#部署指南)
- [已知限制](#已知限制)

---

## 项目总览

| 模块 | 目录 | 技术栈 | 用途 |
|------|------|--------|------|
| Node.js Web 服务 | `src/` `public/` | Node.js 24 + Express + `node:sqlite` | 独立 Web 应用，浏览器访问 |
| AstroBot 插件 | `astrbot_plugin_tarkov_info/` | Python 3（纯标准库） | 接入 QQ/频道机器人 + WebUI 面板 |

### 完整目录结构

```
tarkov-info/
├── README.md                      # 本文件
├── package.json                   # Node 依赖与脚本
├── pnpm-lock.yaml / pnpm-workspace.yaml
├── .env.example                   # 环境变量模板
├── .gitignore
│
├── src/                           # ── Node 后端 ──
│   ├── server.js                  # Express 入口 + 启动调度器
│   ├── config.js                  # 配置（端口/DB路径/数据源URL）
│   ├── db.js                      # SQLite 连接与表结构（items/item_usage/tasks/meta）
│   ├── fetcher.js                 # tarkov.dev 抓取（items/tasks/tasks_zh）
│   ├── queries.js                 # 物品搜索/详情/用途查询
│   ├── task_queries.js            # 任务搜索/详情/商人统计
│   ├── scheduler.js               # 定时同步调度器（防重入/状态记录）
│   ├── constants.js               # 商人/地图 id→中文名映射
│   ├── routes/
│   │   └── api.js                 # REST API 路由
│   └── jobs/
│       ├── sync.js                # 物品全量同步任务
│       ├── sync_tasks.js          # 任务同步任务
│       └── import_zh.js           # 中文名+用途导入
│
├── public/                        # ── 前端 ──
│   ├── index.html                 # 单页应用（物资/任务两个标签）
│   ├── style.css
│   └── app.js
│
├── data/                          # ── 数据（运行时生成，除 seed 外均 gitignore）──
│   ├── seed/items_zh.json         # 中文名+用途种子数据（4235 件物品）
│   └── tarkov.db                  # SQLite 数据库（运行时生成）
│
└── astrbot_plugin_tarkov_info/    # ── AstroBot 插件 ──
    ├── metadata.yaml              # 插件元信息 + pages 声明
    ├── main.py                    # 插件入口（6 指令 + 4 Web API）
    ├── tarkov_data.py             # 数据层（纯标准库）
    ├── requirements.txt           # 无第三方依赖
    ├── data/items.json            # 离线中文名+用途库
    └── pages/dashboard/index.html # Web Dashboard 面板
```

---

## 功能特性

### 物资查询

- 🔍 **中英文双向搜索**：中文名（如「金星软膏」）和英文原名（如 `golden-star-balm`、`ledx`）都能搜
- 四级匹配：完全一致 → 前缀匹配 → 子串匹配 → 顺次字符匹配（容错输入）
- 💰 **价格查询**：跳蚤 24h 均价、24h 最低/最高价、48h 涨跌幅、基准价、商人最高收购价/最低出售价
- 📦 **物品详情**：格子尺寸、重量、分类、跳蚤等级、跳蚤链接、Wiki 链接、图标

### 用途查询

物品的用途分 6 大类（全部中文）：

| 用途类型 | 说明 | 记录数 |
|---------|------|--------|
| 任务需求 | 哪些任务需要上交/出售此物品 | 3902 |
| 兑换产出 | 商人兑换可换到的物品 | 779 |
| 兑换材料 | 作为兑换材料的物品 | 260 |
| 合成材料 | 藏身处/工作台合成配方 | 247 |
| 合成产出 | 合成产出的物品 | 203 |
| 藏身处升级 | 藏身处升级所需材料 | 119 |

### 任务查询

- 📋 **503 个任务**（全部带中文名，100% 覆盖）
- 任务详情：目标（类型/数量/物品/地图/是否可选）、接取/完成奖励、前置任务、所需钥匙、发布商人、最低等级、经验
- 目标类型 20 种（访问/上交/找到/击杀/撤离/安放/标记/改装等，全中文标注）
- 按商人筛选（11 个商人）
- 中英文模糊搜索（任务名/商人/地图/目标物品都能命中）

### 自动同步

- ⏱️ 定时刷新物品价格 + 任务数据
- 间隔可配（默认 600 秒）
- 防重入（一轮未完成不启动下一轮）
- 失败容错（物品/任务独立 try-catch）
- 状态可查（`/api/sync/status`）

---

## 数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| 物品/价格 | `https://json.tarkov.dev/regular/items` | 免鉴权 JSON 快照，约 17MB，5480 件物品 |
| 任务 | `https://json.tarkov.dev/regular/tasks` | 503 个任务结构化数据 |
| 任务中文名 | `https://json.tarkov.dev/regular/tasks_zh` | tarkov.dev 官方中文翻译字典 |
| 中文名/用途 | `data/seed/items_zh.json` | 社区中文数据集（4235 件物品 + 11856 条用途） |

> ⚠️ 塔科夫没有官方公开 API，价格来自社区聚合（tarkov.dev 汇总的玩家上报价），跳蚤价会实时波动；商人收购价来自游戏数据解包，基本稳定。

---

## 一、Node.js Web 服务

### 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Node.js 24 + Express 4 |
| 存储 | `node:sqlite`（Node 内置 SQLite，**无需原生编译**） |
| 前端 | 原生 HTML/CSS/JS（无构建步骤） |
| 依赖 | 仅 `express` + `cors` |

### 快速开始

```bash
# 1. 安装依赖（需要 pnpm 或 npm）
pnpm install

# 2. 启动（首次自动同步全量物品 + 任务）
pnpm dev        # 或 node src/server.js

# 3. 导入中文名 + 用途数据（首次需手动执行一次）
node src/jobs/import_zh.js data/seed/items_zh.json

# 4. 打开浏览器
# http://127.0.0.1:3000
```

### 配置（环境变量，可写入 `.env`）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `3000` | 服务端口 |
| `DB_PATH` | `./data/tarkov.db` | SQLite 数据库路径 |
| `SYNC_INTERVAL_SECONDS` | `600` | 自动同步间隔（秒） |
| `DISABLE_AUTO_SYNC` | `0` | 设 `1` 禁用定时同步（仅保留首次空表同步 + 手动触发） |
| `TARKOV_ITEMS_URL` | `https://json.tarkov.dev/regular/items` | 物品数据源 |
| `TARKOV_TASKS_URL` | `https://json.tarkov.dev/regular/tasks` | 任务数据源 |
| `TARKOV_TASKS_ZH_URL` | `https://json.tarkov.dev/regular/tasks_zh` | 任务中文名数据源 |

### 数据库 Schema

SQLite 共 4 张表：

**`items`**（物品主表，5480 件）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | 物品 ID（24 位 hex） |
| `name_en` | TEXT | 英文原名（normalizedName） |
| `name_zh` | TEXT | 中文名 |
| `types` / `categories` | TEXT(JSON) | 物品类型 / 分类 |
| `avg24h` / `low24h` / `high24h` | INTEGER | 跳蚤 24h 均价/最低/最高 |
| `base_price` | INTEGER | 基准价 |
| `change48h_pct` | REAL | 48h 涨跌幅 % |
| `trader_buy` / `trader_sell` | INTEGER | 商人最高收购价/最低出售价 |
| `width` / `height` / `weight` | — | 格子尺寸 / 重量 |
| `icon_link` / `wiki_link` / `link` | TEXT | 图标 / Wiki / 跳蚤链接 |

**`item_usage`**（物品用途，11856 条）

| 字段 | 说明 |
|------|------|
| `item_id` | 物品 ID |
| `usage_type` | 用途类型（任务需求/兑换材料/…） |
| `detail` | 明细文本 |

**`tasks`**（任务，503 个）

| 字段 | 说明 |
|------|------|
| `name_en` / `name_zh` | 英文/中文任务名 |
| `trader_id` / `trader_zh` | 发布商人 |
| `objectives` | JSON 目标数组 |
| `start_rewards` / `finish_rewards` | JSON 接取/完成奖励 |
| `task_requirements` / `needed_keys` | JSON 前置任务/所需钥匙 |

**`meta`**（键值对元信息）：记录同步时间、物品数等。

### REST API 完整说明

#### 健康检查与状态

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查，返回物品数、任务数、同步时间、中文导入时间、`syncing` 状态 |
| GET | `/api/sync/status` | 同步状态：是否同步中、上次结果、起止时间、间隔 |

#### 物品

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| GET | `/api/items/search` | `q`（关键词）、`limit`（默认20，最大100） | 物品搜索（中/英文名） |
| GET | `/api/items/:id` | 路径参数 `id` | 物品详情（含 `usage` 用途字段） |
| GET | `/api/usage/search` | `q`（关键词）、`limit` | 反查用途（按任务名/用途关键词找物品） |

#### 任务

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| GET | `/api/tasks` | `q`（关键词）、`trader`（商人id）、`limit` | 任务列表/搜索/按商人筛选 |
| GET | `/api/tasks/traders` | — | 商人任务数量统计 |
| GET | `/api/tasks/:id` | 路径参数 `id` | 任务详情 |

#### 同步

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sync` | 手动触发全量同步（物品+任务，防重入，进行中返回 409） |
| POST | `/api/sync/tasks` | 手动触发任务同步 |

### 定时同步机制

```
启动 → ensureInitialData（空表立即同步）
     → startScheduler（按 SYNC_INTERVAL_SECONDS 间隔循环）
          每轮：syncItems() + syncTasks()
          防重入：running 标志
          失败：独立 try-catch，记录到 meta
          状态：可通过 /api/sync/status 查询
```

---

## 二、AstroBot 插件

> 详细文档见 [`astrbot_plugin_tarkov_info/README.md`](astrbot_plugin_tarkov_info/README.md)

### 功能

- 💰 物价查询（跳蚤/商人/卖出建议，支持数量倍数）
- 🎯 用途查询（任务/兑换/合成/藏身处）
- 📋 任务查询（503 任务，中英文搜索）
- 🏆 物价排行 / 数据集概况 / 在线刷新
- 🖥️ Web Dashboard 面板

### 机器人指令

| 指令 | 别名 | 功能 |
|------|------|------|
| `/塔科夫 <物品名> [数量]` | `/tk` `/tarkov` | 查物价 |
| `/塔科夫用途 <物品名>` | `/tk用途` | 查用途明细 |
| `/塔科夫任务 <关键词>` | `/tk任务` `/任务` | 查任务 |
| `/塔科夫榜 [n]` | `/tk榜` | 物价排行 |
| `/塔科夫刷新` | `/tk刷新` | 在线刷新 |
| `/塔科夫信息` | `/tk信息` | 数据概况 |

### 安装

1. 将 `astrbot_plugin_tarkov_info` 目录复制到 AstroBot 的 `data/plugins/`
2. 重启 AstroBot 或在插件管理面板启用

### Web Dashboard

- 通过 `metadata.yaml` 的 `pages` 字段声明
- 提供：数据概览、物品搜索、任务搜索、一键刷新
- 后端通过 `register_web_api` 注册 4 个 API：`overview` / `search` / `tasks` / `refresh`
- 要求 AstroBot `>= 4.24`

### 依赖

纯 Python 标准库（urllib / json / gzip / threading），**零第三方依赖**。

---

## 部署指南

### 场景一：只部署 Web 服务

```bash
git clone https://github.com/sanddiao/astrbot_plugin_tarkov_market.git
cd astrbot_plugin_tarkov_market
pnpm install
node src/jobs/import_zh.js data/seed/items_zh.json
pnpm dev
# 访问 http://127.0.0.1:3000
```

### 场景二：只部署 AstroBot 插件

把 `astrbot_plugin_tarkov_info/` 目录复制到 AstroBot 的 `data/plugins/` 即可。

### 场景三：两者都部署

各自独立运行，互不干扰（共享数据源，但各自有独立的数据存储）。

---

## 已知限制

1. **价格非官方**：塔科夫无公开 API，跳蚤价来自社区聚合，会波动。
2. **中文名覆盖**：物品中文名覆盖约 75%（4130/5480），任务中文名 100% 覆盖。部分新物品（竞技场/赛季/Boss 专属掉落）中文名缺失，回退英文原名。
3. **数据时效**：价格数据随定时同步刷新，间隔可配（默认 10 分钟）。
4. **AstroBot 版本**：Web Dashboard 需要 AstroBot `>= 4.24`。
