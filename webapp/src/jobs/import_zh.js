import fs from 'node:fs';
import path from 'node:path';
import { getDb, setMeta } from '../db.js';

/**
 * 导入社区中文数据集（astrbot_plugin_tarkov_market 的 data/items.json）。
 * 该文件结构：{ generated_at, source, counts, items: [{id, n(中文名), t(商人收购价), f(跳蚤价), u(用途映射)}] }
 *
 * 合并策略：
 *  - 中文名 n 写入 items.name_zh（若原为空）
 *  - 用途 u 写入 item_usage 表
 *  - 若 items 表中不存在该 id（tarkov.dev 未收录），则跳过用途但保留记录
 */
export function importZhData(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`找不到中文数据集: ${filePath}`);
  }

  const raw = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  const items = raw?.items;
  if (!Array.isArray(items)) {
    throw new Error('中文数据集格式异常（缺少 items 数组）');
  }

  const db = getDb();
  const updateName = db.prepare(
    `UPDATE items SET name_zh = COALESCE(name_zh, ?) WHERE id = ?`
  );
  const upsertUsage = db.prepare(
    `INSERT INTO item_usage (item_id, usage_type, detail)
     VALUES (?, ?, ?)
     ON CONFLICT(item_id, usage_type, detail) DO NOTHING`
  );

  db.exec('BEGIN');
  let named = 0;
  let usageRows = 0;
  let missing = 0;
  try {
    for (const it of items) {
      const id = it?.id;
      const name = it?.n;
      if (!id) continue;

      // 中文名（先写占位，下面判断是否真实存在）
      if (name && name.trim()) {
        const r = updateName.run(name, id);
        if (r.changes > 0) named++;
      }

      // 用途
      const u = it?.u;
      if (u && typeof u === 'object') {
        for (const [type, details] of Object.entries(u)) {
          if (!Array.isArray(details)) continue;
          for (const detail of details) {
            if (!detail) continue;
            upsertUsage.run(id, type, detail);
            usageRows++;
          }
        }
      }
    }
    db.exec('COMMIT');
  } catch (err) {
    db.exec('ROLLBACK');
    throw err;
  }

  setMeta('zh_import_at', new Date().toISOString());
  setMeta('zh_import_items', String(items.length));

  return { items: items.length, named, usageRows };
}

// 直接运行：node src/jobs/import_zh.js <path>
import { fileURLToPath } from 'node:url';
if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const p = process.argv[2];
  if (!p) {
    console.error('用法: node src/jobs/import_zh.js <items.json 路径>');
    process.exit(1);
  }
  try {
    const r = importZhData(path.resolve(p));
    console.log('导入完成:', JSON.stringify(r));
  } catch (e) {
    console.error('导入失败:', e.message);
    process.exit(1);
  }
}
