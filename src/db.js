import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';
import { config } from './config.js';

let db = null;

/**
 * 打开（或创建）SQLite 数据库并确保表结构存在。
 */
export function getDb() {
  if (db) return db;

  fs.mkdirSync(path.dirname(config.dbPath), { recursive: true });
  db = new DatabaseSync(config.dbPath);

  db.exec(`
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;

    CREATE TABLE IF NOT EXISTS items (
      id          TEXT PRIMARY KEY,
      name_en     TEXT NOT NULL,          -- normalizedName（英文原名，可搜索）
      short_name  TEXT,                   -- shortName
      name_zh     TEXT,                   -- 中文名（来自 items_zh，可为空）
      description TEXT,
      types       TEXT,                   -- JSON 数组
      categories  TEXT,                   -- JSON 数组
      icon_link   TEXT,
      grid_link   TEXT,
      image_link  TEXT,
      wiki_link   TEXT,
      link        TEXT,
      width       INTEGER,
      height      INTEGER,
      weight      REAL,
      base_price  INTEGER,
      avg24h      INTEGER,                -- 24h 均价（跳蚤）
      low24h      INTEGER,
      high24h     INTEGER,
      last_low    INTEGER,
      change48h_pct REAL,                 -- 48h 涨跌幅 %
      trader_buy  INTEGER,                -- 商人最高收购价（RUB）
      trader_sell INTEGER,                -- 商人最低出售价（RUB）
      flea_min_level INTEGER,
      stack_max   INTEGER,
      properties  TEXT,                   -- JSON（武器/弹药等属性）
      updated_at  TEXT,                   -- tarkov.dev 数据更新时间
      synced_at   TEXT                    -- 本地入库时间
    );

    CREATE INDEX IF NOT EXISTS idx_items_name_en ON items(name_en);
    CREATE INDEX IF NOT EXISTS idx_items_name_zh ON items(name_zh);
    CREATE INDEX IF NOT EXISTS idx_items_avg24h ON items(avg24h);

    CREATE TABLE IF NOT EXISTS meta (
      key   TEXT PRIMARY KEY,
      value TEXT
    );

    -- 物品用途数据（来自社区中文数据集：任务需求/兑换/合成/藏身处升级等）
    CREATE TABLE IF NOT EXISTS item_usage (
      id        INTEGER PRIMARY KEY AUTOINCREMENT,
      item_id   TEXT NOT NULL,
      usage_type TEXT NOT NULL,             -- 任务需求/兑换材料/兑换产出/合成材料/合成产出/藏身处升级
      detail    TEXT NOT NULL,              -- 明细文本（如 "兽医也是医(上交物品5需带标记)"）
      UNIQUE(item_id, usage_type, detail)
    );
    CREATE INDEX IF NOT EXISTS idx_usage_item ON item_usage(item_id);
    CREATE INDEX IF NOT EXISTS idx_usage_type ON item_usage(usage_type);
  `);

  return db;
}

export function setMeta(key, value) {
  const d = getDb();
  d.prepare(
    'INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value'
  ).run(key, String(value));
}

export function getMeta(key) {
  const d = getDb();
  const row = d.prepare('SELECT value FROM meta WHERE key = ?').get(key);
  return row ? row.value : null;
}
