import express from 'express';
import cors from 'cors';
import path from 'node:path';
import fs from 'node:fs';
import { config, ROOT } from './config.js';
import apiRouter from './routes/api.js';
import { getDb } from './db.js';
import { ensureInitialData, startScheduler } from './scheduler.js';

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

// 首次启动：空表立即同步，然后启动定时刷新
ensureInitialData()
  .then(() => startScheduler())
  .catch((e) => {
    console.error('[tarkov-info] 初始化同步失败:', e.message);
    startScheduler(); // 即使首次失败也启动定时器，后续会重试
  });

export default app;
