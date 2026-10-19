import { config } from './config.js';
import { getDb, setMeta } from './db.js';
import { syncItems } from './jobs/sync.js';
import { syncTasks } from './jobs/sync_tasks.js';

/**
 * 定时同步调度器。
 * - 首次启动：若物品/任务表为空则立即同步
 * - 之后按 config.syncIntervalSeconds 间隔，循环刷新物品价格 + 任务
 * - 防重入：一轮同步未完成前不启动下一轮
 * - 同步失败不影响服务，记录状态到 meta
 */

let running = false;
let timer = null;
let lastResult = null;

export function isSyncing() {
  return running;
}

export function lastSyncResult() {
  return lastResult;
}

async function runOnce(reason) {
  if (running) {
    console.log('[scheduler] 上一轮同步仍在进行，跳过本轮');
    return;
  }
  running = true;
  const startedAt = new Date().toISOString();
  console.log(`[scheduler] 开始同步 (${reason}) …`);

  const result = { startedAt, reason, items: null, tasks: null, ok: true, error: null };

  try {
    result.items = await syncItems();
  } catch (e) {
    result.ok = false;
    result.error = `物品同步失败: ${e.message}`;
    console.error('[scheduler] 物品同步失败:', e.message);
  }

  try {
    result.tasks = await syncTasks();
  } catch (e) {
    result.ok = false;
    result.error = (result.error ? result.error + '; ' : '') + `任务同步失败: ${e.message}`;
    console.error('[scheduler] 任务同步失败:', e.message);
  }

  result.finishedAt = new Date().toISOString();
  lastResult = result;

  try {
    setMeta('last_sync_result', JSON.stringify(result));
    setMeta('last_sync_started_at', startedAt);
    setMeta('last_sync_finished_at', result.finishedAt);
  } catch {}

  running = false;
  console.log('[scheduler] 同步结束:', JSON.stringify({ items: result.items, tasks: result.tasks, ok: result.ok }));
  return result;
}

/** 首次启动：空表立即同步。 */
export async function ensureInitialData() {
  const db = getDb();
  const itemCount = (() => {
    try { return db.prepare('SELECT COUNT(*) AS c FROM items').get().c; } catch { return 0; }
  })();
  const taskCount = (() => {
    try { return db.prepare('SELECT COUNT(*) AS c FROM tasks').get().c; } catch { return 0; }
  })();

  if (itemCount === 0 || taskCount === 0) {
    await runOnce('首次启动（空表）');
  }
}

/** 启动定时循环。 */
export function startScheduler() {
  if (timer) return;

  if (config.disableAutoSync) {
    console.log('[scheduler] 自动定时同步已禁用（DISABLE_AUTO_SYNC=1）');
    return;
  }

  const intervalMs = Math.max(60, config.syncIntervalSeconds) * 1000;
  console.log(`[scheduler] 定时同步已启动，间隔 ${config.syncIntervalSeconds}s`);

  timer = setInterval(() => {
    runOnce('定时刷新').catch((e) => console.error('[scheduler] 定时同步异常:', e.message));
  }, intervalMs);

  // 返回 timer 以便测试时清理
  return timer;
}

export function stopScheduler() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

/** 手动触发一次同步（供 API 调用，带防重入）。 */
export async function triggerSync(reason = '手动触发') {
  return runOnce(reason);
}
