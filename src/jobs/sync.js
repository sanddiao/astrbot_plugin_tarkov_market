import { getDb, setMeta, getMeta } from '../db.js';
import { fetchItems, fetchItemsZh } from '../fetcher.js';

/**
 * 从 tarkov.dev 拉取并全量写入 SQLite。
 * 返回统计信息。
 */
export async function syncItems() {
  const db = getDb();
  const [enItems, zhItems] = await Promise.all([fetchItems(), fetchItemsZh()]);

  const upsert = db.prepare(`
    INSERT INTO items (
      id, name_en, short_name, name_zh, description, types, categories,
      icon_link, grid_link, image_link, wiki_link, link,
      width, height, weight, base_price, avg24h, low24h, high24h, last_low,
      change48h_pct, trader_buy, trader_sell, flea_min_level, stack_max,
      properties, updated_at, synced_at
    ) VALUES (
      @id, @name_en, @short_name, @name_zh, @description, @types, @categories,
      @icon_link, @grid_link, @image_link, @wiki_link, @link,
      @width, @height, @weight, @base_price, @avg24h, @low24h, @high24h, @last_low,
      @change48h_pct, @trader_buy, @trader_sell, @flea_min_level, @stack_max,
      @properties, @updated_at, @synced_at
    )
    ON CONFLICT(id) DO UPDATE SET
      name_en = excluded.name_en,
      short_name = excluded.short_name,
      name_zh = excluded.name_zh,
      description = excluded.description,
      types = excluded.types,
      categories = excluded.categories,
      icon_link = excluded.icon_link,
      grid_link = excluded.grid_link,
      image_link = excluded.image_link,
      wiki_link = excluded.wiki_link,
      link = excluded.link,
      width = excluded.width,
      height = excluded.height,
      weight = excluded.weight,
      base_price = excluded.base_price,
      avg24h = excluded.avg24h,
      low24h = excluded.low24h,
      high24h = excluded.high24h,
      last_low = excluded.last_low,
      change48h_pct = excluded.change48h_pct,
      trader_buy = excluded.trader_buy,
      trader_sell = excluded.trader_sell,
      flea_min_level = excluded.flea_min_level,
      stack_max = excluded.stack_max,
      properties = excluded.properties,
      updated_at = excluded.updated_at,
      synced_at = excluded.synced_at
  `);

  const now = new Date().toISOString();

  // 求商人最高收购价 / 最低出售价（RUB）
  function bestSellToTrader(item) {
    let best = null;
    for (const s of item.sellToTrader ?? []) {
      const p = s.priceRUB ?? s.price ?? 0;
      if (p && (best === null || p > best)) best = p;
    }
    return best;
  }
  function bestBuyFromTrader(item) {
    let best = null;
    for (const b of item.buyFromTrader ?? []) {
      const p = b.priceRUB ?? b.price ?? 0;
      if (p && (best === null || p < best)) best = p;
    }
    return best;
  }

  // node:sqlite 没有 transaction() 方法，用显式 BEGIN/COMMIT 包裹提升批量写入性能
  db.exec('BEGIN');
  let count = 0;
  try {
    for (const [id, item] of Object.entries(enItems)) {
      if (!item || typeof item !== 'object') continue;
      const zh = zhItems[id] ?? {};

      upsert.run({
        id,
        name_en: item.normalizedName ?? item.name ?? id,
        short_name: item.shortName ?? null,
        name_zh: zh.name ?? null,
        description: item.description ?? null,
        types: JSON.stringify(item.types ?? []),
        categories: JSON.stringify(item.categories ?? []),
        icon_link: item.iconLink ?? null,
        grid_link: item.gridImageLink ?? null,
        image_link: item.image512pxLink ?? item.baseImageLink ?? null,
        wiki_link: item.wikiLink ?? null,
        link: item.link ?? null,
        width: item.width ?? null,
        height: item.height ?? null,
        weight: item.weight ?? null,
        base_price: item.basePrice ?? null,
        avg24h: item.avg24hPrice ?? null,
        low24h: item.low24hPrice ?? null,
        high24h: item.high24hPrice ?? null,
        last_low: item.lastLowPrice ?? null,
        change48h_pct: item.changeLast48hPercent ?? null,
        trader_buy: bestSellToTrader(item),
        trader_sell: bestBuyFromTrader(item),
        flea_min_level: item.minLevelForFlea ?? null,
        stack_max: item.stackMaxSize ?? null,
        properties: item.properties ? JSON.stringify(item.properties) : null,
        updated_at: item.updated ?? null,
        synced_at: now,
      });
      count++;
    }
    db.exec('COMMIT');
  } catch (err) {
    db.exec('ROLLBACK');
    throw err;
  }
  setMeta('last_sync_at', now);
  setMeta('item_count', String(count));

  return { items: count, zh: Object.keys(zhItems).length };
}
