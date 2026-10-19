import { config } from './config.js';

const UA =
  'TarkovInfo/0.1 (research tool; contact: local)';

/**
 * 从 tarkov.dev 拉取 JSON（走 harness 侧网络时需要 Node 原生 fetch，
 * 这里用 Node 18+ 内置的全局 fetch）。
 * 返回解析后的对象；失败抛出异常。
 */
export async function fetchJson(url, { headers = {} } = {}) {
  const res = await fetch(url, {
    headers: {
      'User-Agent': UA,
      Accept: 'application/json, text/plain, */*',
      'Accept-Encoding': 'gzip',
      ...headers,
    },
    signal: AbortSignal.timeout(90_000),
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status} for ${url}`);
  }
  return res.json();
}

/**
 * 拉取全量物品数据（英文），返回 { id: item } 映射。
 */
export async function fetchItems() {
  const json = await fetchJson(config.itemsUrl);
  const items = json?.data?.items;
  if (!items || typeof items !== 'object') {
    throw new Error('items 数据格式异常');
  }
  return items;
}

/**
 * 拉取中文名映射（items_zh），返回 { id: { name, shortName } } 或空对象。
 */
export async function fetchItemsZh() {
  try {
    const json = await fetchJson(config.itemsZhUrl);
    const items = json?.data?.items;
    if (!items || typeof items !== 'object') return {};
    return items;
  } catch (err) {
    // 中文源不可用不阻断主流程
    console.warn('[fetch] items_zh 拉取失败（忽略）:', err.message);
    return {};
  }
}

/**
 * 拉取任务中文名映射（tasks_zh），返回 { taskId: 中文名 }。
 * tasks_zh 返回格式：{ data: { "<taskId> name": "中文名", ... } }
 */
export async function fetchTasksZh() {
  try {
    const json = await fetchJson(config.tasksZhUrl);
    const data = json?.data;
    if (!data || typeof data !== 'object') return {};
    const map = {};
    for (const [k, v] of Object.entries(data)) {
      const m = k.match(/^([0-9a-f]{24}) name$/);
      if (m && typeof v === 'string' && v.trim()) {
        map[m[1]] = v;
      }
    }
    return map;
  } catch (err) {
    console.warn('[fetch] tasks_zh 拉取失败（忽略）:', err.message);
    return {};
  }
}
