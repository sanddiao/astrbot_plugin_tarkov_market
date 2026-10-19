const input = document.getElementById('search-input');
const resultsEl = document.getElementById('results');
const detailEl = document.getElementById('detail');
const statusEl = document.getElementById('status');

let debounceTimer = null;

function fmt(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('zh-CN');
}

function chgClass(v) {
  if (v == null) return '';
  return v >= 0 ? 'up' : 'down';
}

async function loadHealth() {
  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    if (d.ok) {
      const t = d.lastSyncAt ? new Date(d.lastSyncAt).toLocaleString('zh-CN') : '未同步';
      statusEl.textContent = `已载入 ${d.itemCount} 件物品 · 同步于 ${t}`;
    }
  } catch {
    statusEl.textContent = '后端未连接';
  }
}

function renderItemRow(item) {
  const div = document.createElement('div');
  div.className = 'item-row';
  const mainName = item.nameZh || item.nameEn;
  const subName = item.nameZh ? item.nameEn : '';
  div.innerHTML = `
    ${item.iconLink ? `<img src="${item.iconLink}" loading="lazy" onerror="this.style.visibility='hidden'">` : ''}
    <div class="meta">
      <div class="name">${mainName}<span class="zh">${subName}</span></div>
      <div class="types">${(item.types || []).slice(0, 4).join(' · ')}</div>
    </div>
    <div class="price">
      <div class="val">₽ ${fmt(item.avg24h)}</div>
      <div class="chg ${chgClass(item.change48hPct)}">${item.change48hPct != null ? (item.change48hPct >= 0 ? '▲' : '▼') + Math.abs(item.change48hPct).toFixed(1) + '%' : ''}</div>
    </div>
  `;
  div.addEventListener('click', () => showDetail(item));
  return div;
}

async function showDetail(item) {
  // 先展示基本信息，同时异步拉取详情（含用途）
  renderDetail(item);
  try {
    const r = await fetch(`/api/items/${item.id}`);
    if (r.ok) {
      const full = await r.json();
      renderDetail(full);
    }
  } catch {
    // 忽略，保持基本信息
  }
}

function renderDetail(item) {
  const rows = [
    ['英文原名', item.nameEn],
    ['跳蚤 24h 均价', `₽ ${fmt(item.avg24h)}`],
    ['24h 最低 / 最高', `${fmt(item.low24h)} / ${fmt(item.high24h)}`],
    ['48h 涨跌', item.change48hPct != null ? `${item.change48hPct >= 0 ? '+' : ''}${item.change48hPct.toFixed(2)}%` : '—'],
    ['基础价', `₽ ${fmt(item.basePrice)}`],
    ['商人收购价', item.traderBuy != null ? `₽ ${fmt(item.traderBuy)}` : '—'],
    ['商人出售价', item.traderSell != null ? `₽ ${fmt(item.traderSell)}` : '—'],
    ['格子尺寸', item.width && item.height ? `${item.width}×${item.height}` : '—'],
    ['重量', item.weight != null ? `${item.weight} kg` : '—'],
    ['跳蚤等级', item.fleaMinLevel != null ? `Lv.${item.fleaMinLevel}` : '—'],
    ['分类', (item.categories || []).slice(0, 6).join(' · ') || '—'],
  ];
  if (item.link) rows.push(['来源', `<a href="${item.link}" target="_blank" rel="noopener">tarkov.dev</a>`]);
  if (item.wikiLink) rows.push(['Wiki', `<a href="${item.wikiLink}" target="_blank" rel="noopener">Fandom Wiki</a>`]);

  // 用途区块
  let usageHtml = '';
  const usage = item.usage || {};
  const usageLabels = {
    '任务需求': '任务需求',
    '兑换材料': '兑换材料',
    '兑换产出': '兑换产出',
    '合成材料': '合成材料',
    '合成产出': '合成产出',
    '藏身处升级': '藏身处升级',
  };
  const usageKeys = Object.keys(usage);
  if (usageKeys.length > 0) {
    usageHtml = `<div class="usage">
      <h3>用途</h3>
      ${usageKeys.map((k) => `
        <div class="usage-group">
          <div class="usage-type">${usageLabels[k] || k}（${usage[k].length}）</div>
          <ul>${usage[k].map((d) => `<li>${d}</li>`).join('')}</ul>
        </div>`).join('')}
    </div>`;
  }

  detailEl.innerHTML = `
    <div class="head">
      ${item.iconLink ? `<img src="${item.iconLink}" onerror="this.style.visibility='hidden'">` : ''}
      <div>
        <h2>${item.nameZh || item.nameEn}</h2>
        <div class="zh-name">${item.nameEn}</div>
      </div>
    </div>
    <table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>
    ${usageHtml}
  `;
}

async function doSearch(q) {
  if (!q) {
    resultsEl.innerHTML = '';
    detailEl.innerHTML = '';
    return;
  }
  try {
    const r = await fetch(`/api/items/search?q=${encodeURIComponent(q)}`);
    const d = await r.json();
    if (d.items.length === 0) {
      resultsEl.innerHTML = '<div class="empty">未找到相关物品</div>';
      return;
    }
    resultsEl.innerHTML = '';
    d.items.forEach((it) => resultsEl.appendChild(renderItemRow(it)));
  } catch {
    resultsEl.innerHTML = '<div class="empty">查询失败</div>';
  }
}

input.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => doSearch(input.value.trim()), 200);
});

loadHealth();
