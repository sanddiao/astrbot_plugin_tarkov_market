import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(__dirname, '..');

export const config = {
  port: Number(process.env.PORT ?? 3000),
  dbPath: path.resolve(ROOT, process.env.DB_PATH ?? './data/tarkov.db'),
  itemsUrl: process.env.TARKOV_ITEMS_URL ?? 'https://json.tarkov.dev/regular/items',
  itemsZhUrl: process.env.TARKOV_ITEMS_ZH_URL ?? 'https://json.tarkov.dev/regular/items_zh',
  syncIntervalSeconds: Number(process.env.SYNC_INTERVAL_SECONDS ?? 600),
};
