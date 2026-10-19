import { getDb } from './db.js';

function rowToItem(row) {
  if (!row) return null;
  return {
    id: row.id,
    nameEn: row.name_en,
    nameZh: row.name_zh,
    shortName: row.short_name,
    description: row.description,
    types: row.types ? JSON.parse(row.types) : [],
    categories: row.categories ? JSON.parse(row.categories) : [],
    iconLink: row.icon_link,
    gridLink: row.grid_link,
    imageLink: row.image_link,
    wikiLink: row.wiki_link,
    link: row.link,
    width: row.width,
    height: row.height,
    weight: row.weight,
    basePrice: row.base_price,
    avg24h: row.avg24h,
    low24h: row.low24h,
    high24h: row.high24h,
    lastLow: row.last_low,
    change48hPct: row.change48h_pct,
    traderBuy: row.trader_buy,
    traderSell: row.trader_sell,
    fleaMinLevel: row.flea_min_level,
    stackMax: row.stack_max,
    properties: row.properties ? JSON.parse(row.properties) : null,
    updatedAt: row.updated_at,
    syncedAt: row.synced_at,
  };
}

/**
 * 模糊搜索物品。query 匹配英文名（子串/前缀）与中文名。
 * 排序优先级：英文名前缀 > 中文名前缀 > 英文名包含 > 中文名包含 > 价格降序。
 */
export function searchItems(query, { limit = 20 } = {}) {
  const db = getDb();
  const q = (query ?? '').trim();
  if (!q) return [];

  const like = `%${q}%`;
  const rows = db
    .prepare(
      `SELECT * FROM items
       WHERE name_en LIKE ? OR name_zh LIKE ?
       ORDER BY
         CASE
           WHEN name_en LIKE ? THEN 0
           WHEN name_zh LIKE ? THEN 1
           WHEN name_en LIKE ? THEN 2
           ELSE 3
         END,
         (avg24h IS NOT NULL) DESC,
         avg24h DESC
       LIMIT ?`
    )
    .all(like, like, `${q}%`, `${q}%`, like, limit);

  return rows.map(rowToItem);
}

/** 按 ID 精确取单件。 */
export function getItemById(id) {
  const db = getDb();
  return rowToItem(db.prepare('SELECT * FROM items WHERE id = ?').get(id));
}

/** 取某物品的用途列表，按类型分组。 */
export function getItemUsage(itemId) {
  const db = getDb();
  const rows = db
    .prepare('SELECT usage_type, detail FROM item_usage WHERE item_id = ? ORDER BY usage_type')
    .all(itemId);
  const grouped = {};
  for (const r of rows) {
    (grouped[r.usage_type] ??= []).push(r.detail);
  }
  return grouped;
}

/**
 * 反查用途：给定一个任务名/用途关键词，找出所有相关物品。
 * 例如查"兽医也是医"任务需要哪些物品。
 */
export function searchByUsage(keyword, { limit = 50 } = {}) {
  const db = getDb();
  const kw = (keyword ?? '').trim();
  if (!kw) return [];
  const like = `%${kw}%`;
  const rows = db
    .prepare(
      `SELECT DISTINCT i.*
       FROM item_usage u
       JOIN items i ON i.id = u.item_id
       WHERE u.detail LIKE ?
       ORDER BY i.avg24h DESC
       LIMIT ?`
    )
    .all(like, limit);
  return rows.map(rowToItem);
}

/** 物品总数。 */
export function itemCount() {
  const db = getDb();
  return db.prepare('SELECT COUNT(*) AS c FROM items').get().c;
}
