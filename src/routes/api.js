import { Router } from 'express';
import {
  searchItems,
  getItemById,
  getItemUsage,
  searchByUsage,
  itemCount,
} from '../queries.js';
import { getMeta } from '../db.js';
import { syncItems } from '../jobs/sync.js';

const router = Router();

// 健康检查
router.get('/health', (req, res) => {
  res.json({
    ok: true,
    itemCount: itemCount(),
    lastSyncAt: getMeta('last_sync_at') ?? null,
    zhImportAt: getMeta('zh_import_at') ?? null,
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

export default router;
