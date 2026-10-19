# 塔科夫信息查询（AstroBot 插件 + Node Web 服务）

逃离塔科夫（Escape from Tarkov）**物资 / 价格 / 用途 / 任务** 信息检索项目。

本仓库的**根目录是一个完整的 AstroBot 插件**（可直接安装），同时附带一个独立的 **Node.js Web 服务**（`webapp/`）。两者共享同一套 tarkov.dev 数据源。

---

## 目录

- [项目总览](#项目总览)
- [功能特性](#功能特性)
- [数据源](#数据源)
- [一、AstroBot 插件（仓库根目录）](#一astrobot-插件仓库根目录)
- [二、Node.js Web 服务（webapp/）](#二nodejs-web-服务webapp)
- [已知限制](#已知限制)

---

## 项目总览

| 模块 | 位置 | 技术栈 | 用途 |
|------|------|--------|------|
| AstroBot 插件 | **仓库根目录** | Python 3（纯标准库） | QQ/频道机器人指令 + WebUI 可视化面板 |
| Node.js Web 服务 | `webapp/` | Node.js 24 + Express + `node:sqlite` | 独立 Web 应用，浏览器访问 |

### 完整目录结构

```
tarkov-info/（仓库根目录 = AstroBot 插件）
├── main.py                        # 插件入口：6 个机器人指令 + 4 个 Web API
├── tarkov_data.py                 # 数据层（纯标准库：抓取/搜索/格式化）
├── metadata.yaml                  # 插件元信息（AstrBot 识别插件必需）
├── requirements.txt               # 无第三方依赖
│
├── pages/                         # 插件可视化视图（AstrBot WebUI「打开插件UI界面」）
│   └── dashboard/
│       └── index.html             # 面板：数据概览/物品搜索/任务搜索/在线刷新
│
├── .astrbot-plugin/
│   └── i18n/
│       └── zh-CN.json             # 视图标题与描述元数据
│
├── data/
│   ├── items.json                 # 离线库：4235 件物品中文名 + 11856 条用途
│   └── seed/items_zh.json         # 中文名种子数据（供 Node 端导入）
│
├── webapp/                        # ── Node.js Web 服务（独立模块）──
│   ├── package.json / pnpm-lock.yaml / pnpm-workspace.yaml
│   ├── .env.example               # 环境变量模板
│   ├── src/                       # Express 后端
│   │   ├── server.js              # 入口 + 启动定时调度器
│   │   ├── config.js              # 配置（端口/DB路径/数据源URL）
│   │   ├── db.js                  # SQLite 表结构（items/item_usage/tasks/meta）
│   │   ├── fetcher.js             # tarkov.dev 抓取
│   │   ├── queries.js             # 物品搜索/详情/用途
│   │   ├── task_queries.js        # 任务搜索/详情/商人统计
│   │   ├── scheduler.js           # 定时同步（防重入/状态记录）
│   │   ├── constants.js           # 商人/地图中文名映射
│   │   ├── routes/api.js          # REST API 路由
│   │   └── jobs/                  # sync.js / sync_tasks.js / import_zh.js
│   └── public/                    # 前端（index.html / style.css / app.js）
│
├── PLUGIN_README.md               # 插件专属说明
└── README.md                      # 本文件
```

---

## 功能特性

### 物资查询

- 🔍 **中英文双向搜索**：中文名（如「金星软膏」）和英文原名（如 `ledx`、`golden-star-balm`）都能搜
- 四级匹配：完全一致 → 前缀匹配 → 子串匹配 → 顺次字符匹配（容错输入）
- 💰 **价格查询**：跳蚤 24h 均价、24h 最低/最高价、48h 涨跌幅、基准价、商人最高收购价/最低出售价
- 📦 **物品详情**：格子尺寸、重量、分类、跳蚤等级、跳蚤链接、Wiki 链接

### 用途查询（6 大类，全中文）

| 用途类型 | 记录数 |
|---------|--------|
| 任务需求 | 3902 |
| 兑换产出 | 779 |
| 兑换材料 | 260 |
| 合成材料 | 247 |
| 合成产出 | 203 |
| 藏身处升级 | 119 |

### 任务查询

- 📋 **503 个任务**（中文名 100% 覆盖，来自 tarkov.dev 官方 `tasks_zh`）
- 任务详情：目标（20 种类型，全中文）、接取/完成奖励、前置任务、所需钥匙、发布商人、最低等级、经验
- 按商人筛选（11 个商人）；中英文模糊搜索

### 自动同步（Node 端）

- 定时刷新物品价格 + 任务（默认 600 秒，可配置）
- 防重入、失败容错、状态可查

---

## 数据源

| 数据 | 来源 |
|------|------|
| 物品/价格 | `https://json.tarkov.dev/regular/items`（5480 件，约 17MB） |
| 任务 | `https://json.tarkov.dev/regular/tasks`（503 个） |
| 任务中文名 | `https://json.tarkov.dev/regular/tasks_zh` |
| 物品中文名/用途 | 社区中文数据集（`data/items.json`，4235 件 + 11856 条用途） |

> ⚠️ 塔科夫没有官方公开 API，价格来自社区聚合（tarkov.dev 汇总的玩家上报价），跳蚤价会实时波动。

---

## 一、AstroBot 插件（仓库根目录）

### 安装

1. 在 AstrBot 的插件市场搜索 `astrbot_plugin_tarkov_info`，或
2. 手动安装：将**整个仓库**克隆/下载后，把内容放入 AstrBot 的插件目录（如 `data/plugins/astrbot_plugin_tarkov_info/`）
3. 重启 AstrBot，日志出现 `[tarkov_info] 插件已加载` 即成功

### 机器人指令

| 指令 | 别名 | 功能 |
|------|------|------|
| `/塔科夫 <物品名> [数量]` | `/tk` `/tarkov` `/物价` | 查物价（`/塔科夫 吗啡 5` = 5 份总价） |
| `/塔科夫用途 <物品名>` | `/tk用途` `/tku` | 查用途明细（任务/兑换/合成/藏身处） |
| `/塔科夫任务 <关键词>` | `/tk任务` `/任务` | 查任务（中英文，如 `首秀`、`惩罚者`、`枪匠`、`debut`） |
| `/塔科夫榜 [n]` | `/tk榜` `/物价榜` | 物价排行（默认前 10，最多 30） |
| `/塔科夫刷新` | `/tk刷新` | 强制在线刷新实时价 + 任务（约 5~10 秒） |
| `/塔科夫信息` | `/tk信息` | 数据集概况 |

### 使用示例

```
/塔科夫 吗啡
/塔科夫 显卡 5          → 5 份总价
/tk ledx
/tk用途 金星软膏
/塔科夫任务 医疗隐私
/tk榜 15
```

### 输出示例

```
【吗啡注射器】
数量：×5
跳蚤市场：₽18,647 （合计 ₽93,235）
商人收购：₽10,324 （合计 ₽51,620）
建议：卖给跳蚤市场更划算，差价 ₽8,323 注意跳蚤需缴手续费
数据来源：在线实时价（json.tarkov.dev）
```

### Web 可视化面板（插件 UI）

在 AstrBot WebUI 的**插件详情页**点击「打开插件UI界面」，即可打开面板：

- **数据概览**：物品库 / 任务库数量、在线价格状态
- **物品查询**：中英文搜索，显示跳蚤价、商人价、48h 涨跌
- **任务查询**：中英文搜索，显示目标、奖励、商人、地图
- **在线刷新**：一键拉取最新数据

实现遵循 AstrBot 官方插件页面规范：

- 视图位于 `pages/dashboard/index.html`（受限 iframe 加载）
- 前端通过 `window.AstrBotPluginView` bridge 与后端通信（`ready()` → `apiGet()` → `apiPost()`）
- 后端 API 路由以插件名为前缀：`/astrbot_plugin_tarkov_info/overview|search|tasks|refresh`
- 自动适配 WebUI 亮/暗主题
- 视图标题等元数据位于 `.astrbot-plugin/i18n/zh-CN.json`

> **版本要求**：AstrBot `>= 4.24`（插件视图 `pages/` + `register_web_api` API）

### 依赖

纯 Python 标准库（urllib / json / gzip / threading），**零第三方依赖**。

---

## 二、Node.js Web 服务（webapp/）

### 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Node.js 24 + Express 4 |
| 存储 | `node:sqlite`（Node 内置 SQLite，**无需原生编译**） |
| 前端 | 原生 HTML/CSS/JS（无构建步骤） |
| 依赖 | 仅 `express` + `cors` |

### 快速开始

```bash
cd webapp
pnpm install

# 首次导入中文名 + 用途数据（执行一次）
node src/jobs/import_zh.js ../data/seed/items_zh.json

# 启动（首次自动同步全量物品 + 任务）
pnpm dev

# 打开 http://127.0.0.1:3000
```

### 配置（环境变量）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `3000` | 服务端口 |
| `DB_PATH` | `./data/tarkov.db` | SQLite 数据库路径 |
| `SYNC_INTERVAL_SECONDS` | `600` | 自动同步间隔（秒） |
| `DISABLE_AUTO_SYNC` | `0` | 设 `1` 禁用定时同步 |

### REST API

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| GET | `/api/health` | — | 健康检查（物品数/任务数/同步状态） |
| GET | `/api/sync/status` | — | 同步状态详情 |
| GET | `/api/items/search` | `q`, `limit` | 物品搜索 |
| GET | `/api/items/:id` | — | 物品详情（含用途） |
| GET | `/api/usage/search` | `q`, `limit` | 反查用途 |
| GET | `/api/tasks` | `q`, `trader`, `limit` | 任务搜索/筛选 |
| GET | `/api/tasks/traders` | — | 商人任务统计 |
| GET | `/api/tasks/:id` | — | 任务详情 |
| POST | `/api/sync` | — | 手动触发同步 |
| POST | `/api/sync/tasks` | — | 手动触发任务同步 |

### 数据库 Schema

4 张表：

- **`items`**（5480 件）：`id`、`name_en`、`name_zh`、价格字段（`avg24h`/`low24h`/`high24h`/`base_price`/`change48h_pct`）、商人价（`trader_buy`/`trader_sell`）、尺寸重量、链接
- **`item_usage`**（11856 条）：`item_id` + `usage_type` + `detail`
- **`tasks`**（503 个）：中英文名、商人、目标/奖励/前置/钥匙（JSON）
- **`meta`**：同步时间等元信息

---

## 已知限制

1. **价格非官方**：跳蚤价来自社区聚合，会实时波动；商人收购价来自游戏数据解包，基本稳定。
2. **物品中文名覆盖约 75%**（4130/5480）：竞技场/赛季/Boss 专属掉落等新物品可能缺中文名，回退英文原名。任务中文名 100% 覆盖。
3. **WebUI 面板**需要 AstrBot `>= 4.24`；旧版 AstrBot 仍可正常使用全部机器人指令。
