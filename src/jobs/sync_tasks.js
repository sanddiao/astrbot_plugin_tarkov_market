import { getDb, setMeta } from '../db.js';
import { fetchJson, fetchTasksZh } from '../fetcher.js';
import { traderName, mapName } from '../constants.js';
import { config } from '../config.js';

// 目标类型 → 中文动词
const OBJ_TYPE_ZH = {
  visit: '访问',
  giveItem: '上交',
  findItem: '找到',
  findQuestItem: '找到任务物品',
  giveQuestItem: '上交任务物品',
  extract: '撤离',
  shoot: '击杀',
  plantItem: '安放',
  placeItem: '放置',
  markItem: '标记',
  eliminate: '消灭',
  collectItem: '收集',
  pickUpItem: '拾取',
  traderLevel: '商人等级达到',
  skill: '技能达到',
  standing: '声望达到',
  build: '建造',
};

function objTypeZh(type) {
  return OBJ_TYPE_ZH[type] ?? type;
}

// 将 tarkov.dev 的 task 数据压缩为可存储的结构
function normalizeTask(task, nameZhMap, itemZhMap) {
  const objectives = (task.objectives ?? []).map((o) => {
    const itemIds = o.items ?? [];
    const items = itemIds.map((iid) => ({
      id: iid,
      name: itemZhMap.get(iid) ?? iid,
    }));
    const maps = (o.maps ?? []).map(mapName);
    return {
      type: o.type,
      typeZh: objTypeZh(o.type),
      count: o.count ?? null,
      optional: o.optional ?? false,
      items,
      maps: [...new Set(maps)],
      questItem: o.questItem ?? null,
      exitName: o.exitName ?? null,
      level: o.level ?? null,
      targetNames: o.targetNames ?? null,
    };
  });

  const rewardItems = (rewards) =>
    (rewards?.items ?? []).map((r) => ({
      id: r.item,
      name: itemZhMap.get(r.item) ?? r.item,
      count: r.count,
    }));

  const finishRewards = task.finishRewards ?? {};
  const startRewards = task.startRewards ?? {};

  return {
    id: task.id,
    name_en: task.normalizedName ?? task.name ?? task.id,
    name_zh: nameZhMap.get(task.id) ?? null,
    trader_id: task.trader ?? null,
    trader_zh: task.trader ? traderName(task.trader) : null,
    min_level: task.minPlayerLevel ?? null,
    map_id: task.map ?? null,
    wiki_link: task.wikiLink ?? null,
    image_link: task.taskImageLink ?? null,
    experience: task.experience ?? null,
    objectives: JSON.stringify(objectives),
    start_rewards: JSON.stringify({
      items: rewardItems(startRewards),
      traderStanding: (startRewards.traderStanding ?? []).map((s) => ({
        trader: traderName(s.trader),
        standing: s.standing,
      })),
    }),
    finish_rewards: JSON.stringify({
      items: rewardItems(finishRewards),
      traderStanding: (finishRewards.traderStanding ?? []).map((s) => ({
        trader: traderName(s.trader),
        standing: s.standing,
      })),
    }),
    task_requirements: JSON.stringify(
      (task.taskRequirements ?? []).map((r) => ({ task: r.task, status: r.status ?? [] }))
    ),
    needed_keys: JSON.stringify(
      (task.neededKeys ?? []).map((k) => ({ map: mapName(k.map), keys: k.keys ?? [] }))
    ),
    synced_at: new Date().toISOString(),
  };
}

/**
 * 同步任务数据：拉取 tarkov.dev tasks，匹配中文任务名与物品名。
 */
export async function syncTasks() {
  const db = getDb();
  const [json, zhMap] = await Promise.all([
    fetchJson(config.tasksUrl),
    fetchTasksZh(),
  ]);
  const tasks = json?.data?.tasks;
  if (!tasks || typeof tasks !== 'object') {
    throw new Error('tasks 数据格式异常');
  }

  // 中文任务名映射（tasks_zh 返回 { taskId: 中文名 }）
  const nameZhMap = new Map(Object.entries(zhMap));

  // 构建物品中文名映射（用于目标展示）
  const itemZhMap = new Map();
  const itemRows = db.prepare('SELECT id, name_zh FROM items WHERE name_zh IS NOT NULL').all();
  for (const r of itemRows) itemZhMap.set(r.id, r.name_zh);

  const upsert = db.prepare(`
    INSERT INTO tasks (
      id, name_en, name_zh, trader_id, trader_zh, min_level, map_id,
      wiki_link, image_link, experience, objectives, start_rewards,
      finish_rewards, task_requirements, needed_keys, synced_at
    ) VALUES (
      @id, @name_en, @name_zh, @trader_id, @trader_zh, @min_level, @map_id,
      @wiki_link, @image_link, @experience, @objectives, @start_rewards,
      @finish_rewards, @task_requirements, @needed_keys, @synced_at
    )
    ON CONFLICT(id) DO UPDATE SET
      name_en = excluded.name_en,
      name_zh = COALESCE(excluded.name_zh, tasks.name_zh),
      trader_id = excluded.trader_id,
      trader_zh = excluded.trader_zh,
      min_level = excluded.min_level,
      map_id = excluded.map_id,
      wiki_link = excluded.wiki_link,
      image_link = excluded.image_link,
      experience = excluded.experience,
      objectives = excluded.objectives,
      start_rewards = excluded.start_rewards,
      finish_rewards = excluded.finish_rewards,
      task_requirements = excluded.task_requirements,
      needed_keys = excluded.needed_keys,
      synced_at = excluded.synced_at
  `);

  db.exec('BEGIN');
  let count = 0;
  let zhCount = 0;
  try {
    for (const [id, task] of Object.entries(tasks)) {
      if (!task || typeof task !== 'object') continue;
      if (nameZhMap.has(id)) zhCount++;
      upsert.run(normalizeTask(task, nameZhMap, itemZhMap));
      count++;
    }
    db.exec('COMMIT');
  } catch (err) {
    db.exec('ROLLBACK');
    throw err;
  }

  setMeta('tasks_synced_at', new Date().toISOString());
  setMeta('task_count', String(count));
  return { tasks: count, zh: zhCount };
}
