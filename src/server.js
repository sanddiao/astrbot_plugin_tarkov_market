import express from 'express';
import cors from 'cors';
import path from 'node:path';
import fs from 'node:fs';
import { config, ROOT } from './config.js';
import apiRouter from './routes/api.js';
import { getDb } from './db.js';
import { syncItems } from './jobs/sync.js';

const app = express();
app.use(cors());
app.use(express.json());

// 初始化数据库（确保表存在）
getDb();

// API 路由
app.use('/api', apiRouter);

// 前端静态资源
const publicDir = path.join(ROOT, 'public');
if (fs.existsSync(publicDir)) {
  app.use(express.static(publicDir));
}

// 404
app.use((req, res) => {
  res.status(404).json({ error: 'not found' });
});

// 启动
app.listen(config.port, () => {
  console.log(`[tarkov-info] 服务已启动: http://127.0.0.1:${config.port}`);
  console.log(`[tarkov-info] 数据库: ${config.dbPath}`);
});

// 首次启动若无数据则自动同步
const c = (() => {
  try {
    return getDb().prepare('SELECT COUNT(*) AS c FROM items').get().c;
  } catch {
    return 0;
  }
})();
if (c === 0) {
  console.log('[tarkov-info] 数据库为空，开始首次同步…');
  syncItems()
    .then((r) => console.log('[tarkov-info] 首次同步完成:', JSON.stringify(r)))
    .catch((e) => console.error('[tarkov-info] 首次同步失败:', e.message));
}

export default app;
