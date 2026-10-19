import { Router } from 'express';
import {
  searchItems,
  getItemById,
  getItemUsage,
  searchByUsage,
  itemCount,
} from '../queries.js';
import {
  searchTasks,
  getTaskById,
  taskCount,
  taskTraderStats,
} from '../task_queries.js';
import { getMeta } from '../db.js';
import { syncItems } from '../jobs/sync.js';
import { syncTasks } from '../jobs/sync_tasks.js';

const router = Router();

// 健康检查
router.get('/health', (req, res) => {
  res.json({
    ok: true,
    itemCount: itemCount(),
    taskCount: taskCount(),
    lastSyncAt: getMeta('last_sync_at') ?? null,
    zhImportAt: getMeta('zh_import_at') ?? null,
    tasksSyncedAt: getMeta('tasks_synced_at') ?? null,
  });
});

// 搜索
router.get('/items/search', (req, res) => {
  const q = String(req.query.q ?? '');
  const limit = Math.min(Number(req.query.limit) || 20, 100);
  const items = searchItems(q, { limit });
  res.json({ query: q, count: items.length, items });
});

// 反查用途（按任务名/用途关键词找物品）
router.get('/usage/search', (req, res) => {
  const q = String(req.query.q ?? '');
  const limit = Math.min(Number(req.query.limit) || 50, 200);
  const items = searchByUsage(q, { limit });
  res.json({ query: q, count: items.length, items });
});

// 详情
router.get('/items/:id', (req, res) => {
  const item = getItemById(req.params.id);
  if (!item) {
    return res.status(404).json({ error: 'not found' });
  }
  item.usage = getItemUsage(req.params.id);
  res.json(item);
});

// 手动触发同步
router.post('/sync', async (req, res) => {
  try {
    const result = await syncItems();
    res.json({ ok: true, ...result });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err?.message ?? err) });
  }
});

// 任务：列表 / 搜索
router.get('/tasks', (req, res) => {
  const q = String(req.query.q ?? '');
  const trader = req.query.trader ? String(req.query.trader) : null;
  const limit = Math.min(Number(req.query.limit) || 50, 200);
  const tasks = searchTasks(q, { trader, limit });
  res.json({ query: q, trader, count: tasks.length, tasks });
});

// 任务：商人统计
router.get('/tasks/traders', (req, res) => {
  res.json({ traders: taskTraderStats() });
});

// 任务：详情
router.get('/tasks/:id', (req, res) => {
  const task = getTaskById(req.params.id);
  if (!task) {
    return res.status(404).json({ error: 'not found' });
  }
  res.json(task);
});

// 手动触发任务同步
router.post('/sync/tasks', async (req, res) => {
  try {
    const result = await syncTasks();
    res.json({ ok: true, ...result });
  } catch (err) {
    res.status(500).json({ ok: false, error: String(err?.message ?? err) });
  }
});

export default router;
