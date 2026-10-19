# 塔科夫信息检索系统（Tarkov Info）

逃离塔科夫（Escape from Tarkov）**物资 / 价格 / 任务查询** 信息检索项目。

> 本仓库由早期的 `astrbot_plugin_tarkov_market`（AstroBot 物价查询插件）演进而来，现已扩展为：
> 一个 **Node.js Web 服务**（带前端界面）+ 一个 **AstroBot 插件**（带 Web Dashboard），共享同一套 tarkov.dev 数据源。

## 组成

| 模块 | 目录 | 说明 |
|------|------|------|
| **Node.js Web 服务** | `src/` + `public/` | Express + SQLite 后端，前端搜索界面 |
| **AstroBot 插件** | `astrbot_plugin_tarkov_info/` | 机器人指令 + Web Dashboard 面板 |

## 功能

- 🔍 物资搜索：中文名 / 英文原名双向搜索，支持前缀/子串匹配
- 💰 价格查询：跳蚤 24h 均价、最低/最高价、48h 涨跌幅、商人收购/出售价
- 📦 物品详情：格子尺寸、重量、分类、跳蚤等级、跳蚤链接、Wiki 链接
- 🎯 用途查询：物品的任务需求 / 兑换 / 合成 / 藏身处升级（中文）
- 📋 任务查询：503 个任务（目标/奖励/前置/商人），中英文模糊搜索
- ⏱️ 定时同步：物品价格 + 任务按间隔自动刷新

## 数据源

- **物品/价格**：`https://json.tarkov.dev/regular/items`（免鉴权 JSON 快照，约 17MB）
- **任务**：`https://json.tarkov.dev/regular/tasks`（503 个任务结构化数据）
- **任务中文名**：`https://json.tarkov.dev/regular/tasks_zh`
- **中文名/用途**：社区中文数据集（`data/seed/items_zh.json`，4235 件物品 + 11856 条用途）

---

## 一、Node.js Web 服务

### 技术栈

- 后端：Node.js 24 + Express
- 存储：`node:sqlite`（Node 内置 SQLite，无需原生编译）
- 前端：原生 HTML/CSS/JS（无构建步骤）

### 快速开始

```bash
pnpm install
pnpm dev        # 首次自动同步全量数据
# 导入中文名 + 用途
node src/jobs/import_zh.js data/seed/items_zh.json
# 打开 http://127.0.0.1:3000
```

### 配置（环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `PORT` | 3000 | 服务端口 |
| `SYNC_INTERVAL_SECONDS` | 600 | 自动同步间隔（秒） |
| `DISABLE_AUTO_SYNC` | 0 | 设 1 禁用定时同步 |

### API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/items/search?q=` | 物品搜索 |
| GET | `/api/items/:id` | 物品详情（含用途） |
| GET | `/api/usage/search?q=` | 反查用途 |
| GET | `/api/tasks?q=&trader=` | 任务搜索 |
| GET | `/api/tasks/:id` | 任务详情 |
| GET | `/api/sync/status` | 同步状态 |
| POST | `/api/sync` | 手动触发同步 |

---

## 二、AstroBot 插件

见 [`astrbot_plugin_tarkov_info/README.md`](astrbot_plugin_tarkov_info/README.md)。

### 机器人指令

| 指令 | 别名 | 功能 |
|------|------|------|
| `/塔科夫 <物品名> [数量]` | `/tk` | 物价查询 |
| `/塔科夫用途 <物品名>` | `/tk用途` | 用途明细 |
| `/塔科夫任务 <关键词>` | `/tk任务` | 任务查询 |
| `/塔科夫榜 [n]` | `/tk榜` | 物价排行 |
| `/塔科夫刷新` | `/tk刷新` | 在线刷新 |
| `/塔科夫信息` | `/tk信息` | 数据概况 |

### 安装

将 `astrbot_plugin_tarkov_info` 目录复制到 AstroBot 的 `data/plugins/`，重启即可。Web Dashboard 需要 AstroBot `>= 4.24`。

---

## 已知限制

- 塔科夫没有官方公开 API，价格来自社区聚合（tarkov.dev 汇总的玩家上报价），跳蚤价会实时波动。
- 部分新物品（竞技场/赛季/Boss 专属）的中文名可能缺失，回退显示英文原名。
