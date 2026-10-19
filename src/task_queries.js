import { getDb } from './db.js';

function rowToTask(row) {
  if (!row) return null;
  return {
    id: row.id,
    nameEn: row.name_en,
    nameZh: row.name_zh,
    traderId: row.trader_id,
    traderZh: row.trader_zh,
    minLevel: row.min_level,
    mapId: row.map_id,
    wikiLink: row.wiki_link,
    imageLink: row.image_link,
    experience: row.experience,
    objectives: row.objectives ? JSON.parse(row.objectives) : [],
    startRewards: row.start_rewards ? JSON.parse(row.start_rewards) : null,
    finishRewards: row.finish_rewards ? JSON.parse(row.finish_rewards) : null,
    taskRequirements: row.task_requirements ? JSON.parse(row.task_requirements) : [],
    neededKeys: row.needed_keys ? JSON.parse(row.needed_keys) : [],
    syncedAt: row.synced_at,
  };
}

/**
 * 模糊搜索任务：匹配英文任务名、目标物品名、商人名、地图名。
 * 通过 tasks 表的 JSON 字段做 LIKE 匹配。
 */
export function searchTasks(query, { trader = null, limit = 50 } = {}) {
  const db = getDb();
  const q = (query ?? '').trim();
  const like = `%${q}%`;

  let sql = `SELECT * FROM tasks`;
  const params = [];
  const conds = [];

  if (q) {
    conds.push(`(name_en LIKE ? OR name_zh LIKE ? OR objectives LIKE ? OR trader_zh LIKE ?)`);
    params.push(like, like, like, like);
  }
  if (trader) {
    conds.push(`trader_id = ?`);
    params.push(trader);
  }
  if (conds.length) sql += ` WHERE ` + conds.join(' AND ');
  sql += ` ORDER BY min_level ASC, name_en ASC LIMIT ?`;
  params.push(limit);

  const rows = db.prepare(sql).all(...params);
  return rows.map(rowToTask);
}

/** 按 ID 取单个任务。 */
export function getTaskById(id) {
  const db = getDb();
  return rowToTask(db.prepare('SELECT * FROM tasks WHERE id = ?').get(id));
}

/** 任务总数。 */
export function taskCount() {
  const db = getDb();
  return db.prepare('SELECT COUNT(*) AS c FROM tasks').get().c;
}

/** 所有商人的任务数量统计。 */
export function taskTraderStats() {
  const db = getDb();
  return db
    .prepare(
      'SELECT trader_id, trader_zh, COUNT(*) AS c FROM tasks GROUP BY trader_id, trader_zh ORDER BY c DESC'
    )
    .all();
}
