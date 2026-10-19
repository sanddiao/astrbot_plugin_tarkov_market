// ===== 通用工具 =====
function fmt(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('zh-CN');
}
function chgClass(v) {
  if (v == null) return '';
  return v >= 0 ? 'up' : 'down';
}
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

// ===== 标签切换 =====
const tabs = document.querySelectorAll('.tab');
const views = {
  items: document.getElementById('view-items'),
  tasks: document.getElementById('view-tasks'),
};
tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    tabs.forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    Object.values(views).forEach((v) => v.classList.remove('active'));
    views[tab.dataset.tab].classList.add('active');
    if (tab.dataset.tab === 'tasks') loadTaskTraders();
  });
});

// ===== 状态栏 =====
const statusEl = document.getElementById('status');
async function loadHealth() {
  try {
    const d = await getJSON('/api/health');
    if (d.ok) {
      const t = d.lastSyncAt ? new Date(d.lastSyncAt).toLocaleString('zh-CN') : '未同步';
      statusEl.textContent = `物品 ${d.itemCount} · 任务 ${d.taskCount ?? 0} · 同步于 ${t}`;
    }
  } catch {
    statusEl.textContent = '后端未连接';
  }
}

// ================= 物资查询 =================
const input = document.getElementById('search-input');
const resultsEl = document.getElementById('results');
const detailEl = document.getElementById('detail');
let debounceTimer = null;

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
  div.addEventListener('click', () => showItemDetail(item));
  return div;
}

async function showItemDetail(item) {
  renderItemDetail(item);
  try {
    const full = await getJSON(`/api/items/${item.id}`);
    renderItemDetail(full);
  } catch {}
}

function renderItemDetail(item) {
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

  const usage = item.usage || {};
  const usageLabels = {
    '任务需求': '任务需求', '兑换材料': '兑换材料', '兑换产出': '兑换产出',
    '合成材料': '合成材料', '合成产出': '合成产出', '藏身处升级': '藏身处升级',
  };
  const usageKeys = Object.keys(usage);
  let usageHtml = '';
  if (usageKeys.length > 0) {
    usageHtml = `<div class="usage"><h3>用途</h3>${usageKeys.map((k) => `
      <div class="usage-group">
        <div class="usage-type">${usageLabels[k] || k}（${usage[k].length}）</div>
        <ul>${usage[k].map((d) => `<li>${d}</li>`).join('')}</ul>
      </div>`).join('')}</div>`;
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
    ${usageHtml}`;
}

async function doItemSearch(q) {
  if (!q) { resultsEl.innerHTML = ''; detailEl.innerHTML = ''; return; }
  try {
    const d = await getJSON(`/api/items/search?q=${encodeURIComponent(q)}`);
    if (d.items.length === 0) { resultsEl.innerHTML = '<div class="empty">未找到相关物品</div>'; return; }
    resultsEl.innerHTML = '';
    d.items.forEach((it) => resultsEl.appendChild(renderItemRow(it)));
  } catch {
    resultsEl.innerHTML = '<div class="empty">查询失败</div>';
  }
}

input.addEventListener('input', () => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => doItemSearch(input.value.trim()), 200);
});

// ================= 任务查询 =================
const taskInput = document.getElementById('task-search-input');
const taskResultsEl = document.getElementById('task-results');
const taskDetailEl = document.getElementById('task-detail');
const taskFiltersEl = document.getElementById('task-filters');
let taskDebounce = null;
let activeTrader = null;

const OBJ_COLORS = {
  visit: 'visit', giveItem: 'give', findItem: 'find', findQuestItem: 'find',
  giveQuestItem: 'give', extract: 'extract', shoot: 'kill', plantItem: 'plant',
  mark: 'mark', buildWeapon: 'build',
};

async function loadTaskTraders() {
  try {
    const d = await getJSON('/api/tasks/traders');
    taskFiltersEl.innerHTML = '';
    const allBtn = document.createElement('button');
    allBtn.className = 'filter-btn' + (activeTrader === null ? ' active' : '');
    allBtn.textContent = '全部';
    allBtn.addEventListener('click', () => { activeTrader = null; loadTaskTraders(); doTaskSearch(); });
    taskFiltersEl.appendChild(allBtn);
    for (const t of d.traders) {
      const b = document.createElement('button');
      b.className = 'filter-btn' + (activeTrader === t.trader_id ? ' active' : '');
      b.textContent = `${t.trader_zh} (${t.c})`;
      b.addEventListener('click', () => { activeTrader = t.trader_id; loadTaskTraders(); doTaskSearch(); });
      taskFiltersEl.appendChild(b);
    }
  } catch {}
}

function renderTaskRow(task) {
  const div = document.createElement('div');
  div.className = 'item-row task-row';
  const objSummary = task.objectives.slice(0, 3).map((o) => o.typeZh).join(' / ');
  div.innerHTML = `
    ${task.imageLink ? `<img src="${task.imageLink}" loading="lazy" onerror="this.style.visibility='hidden'">` : ''}
    <div class="meta">
      <div class="name">${task.nameZh || task.nameEn}</div>
      <div class="types">${task.traderZh || ''}${task.minLevel ? ` · Lv.${task.minLevel}` : ''}</div>
      <div class="types">${objSummary}</div>
    </div>
    <div class="price">
      <div class="val">${task.experience ? 'EXP ' + fmt(task.experience) : ''}</div>
    </div>
  `;
  div.addEventListener('click', () => showTaskDetail(task));
  return div;
}

function renderTaskDetail(task) {
  const rewardHtml = (label, rw) => {
    if (!rw) return '';
    const items = (rw.items || []).map((i) => `${i.name}×${i.count}`).join('、');
    const standing = (rw.traderStanding || []).map((s) => `${s.trader} 声望+${s.standing}`).join('、');
    const parts = [items, standing].filter(Boolean);
    if (!parts.length) return '';
    return `<tr><td>${label}</td><td>${parts.join('；')}</td></tr>`;
  };

  const rows = [
    ['任务（英）', task.nameEn],
    ['发布商人', task.traderZh || '—'],
    ['最低等级', task.minLevel != null ? `Lv.${task.minLevel}` : '—'],
    ['经验奖励', task.experience != null ? fmt(task.experience) : '—'],
  ];
  if (task.wikiLink) rows.push(['Wiki', `<a href="${task.wikiLink}" target="_blank" rel="noopener">Fandom Wiki</a>`]);
  rows.push(rewardHtml('接取奖励', task.startRewards));
  rows.push(rewardHtml('完成奖励', task.finishRewards));

  // 前置任务
  if (task.taskRequirements.length > 0) {
    const reqs = task.taskRequirements.map((r) => `<span class="req-task" data-id="${r.task}">${r.task}</span> (${r.status.join(',')})`).join('、');
    rows.push(['前置任务', reqs]);
  }

  // 所需钥匙
  if (task.neededKeys.length > 0) {
    const keys = task.neededKeys.map((k) => `${k.map}: ${k.keys.join(', ')}`).join('；');
    rows.push(['所需钥匙', keys]);
  }

  // 目标列表
  const objectivesHtml = task.objectives.map((o, i) => {
    const cls = OBJ_COLORS[o.type] || '';
    const opt = o.optional ? '（可选）' : '';
    const count = o.count != null ? ` ×${o.count}` : '';
    const items = o.items.length ? `：${o.items.slice(0, 5).map((x) => x.name).join('、')}${o.items.length > 5 ? ' 等' : ''}` : '';
    const maps = o.maps.length ? ` [${o.maps.join('/')}]` : '';
    return `<li class="obj ${cls}"><span class="obj-type">${o.typeZh}${count}</span>${items}${maps}${opt}</li>`;
  }).join('');

  taskDetailEl.innerHTML = `
    <div class="head">
      ${task.imageLink ? `<img src="${task.imageLink}" onerror="this.style.visibility='hidden'">` : ''}
      <div>
        <h2>${task.nameZh || task.nameEn}</h2>
        <div class="zh-name">${task.traderZh || ''}</div>
      </div>
    </div>
    <table>${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>
    <div class="usage"><h3>任务目标</h3><ul class="obj-list">${objectivesHtml}</ul></div>`;
}

async function showTaskDetail(task) {
  renderTaskDetail(task);
  try {
    const full = await getJSON(`/api/tasks/${task.id}`);
    renderTaskDetail(full);
  } catch {}
}

async function doTaskSearch() {
  const q = taskInput.value.trim();
  let url = '/api/tasks?limit=100';
  if (q) url += `&q=${encodeURIComponent(q)}`;
  if (activeTrader) url += `&trader=${encodeURIComponent(activeTrader)}`;
  try {
    const d = await getJSON(url);
    if (d.tasks.length === 0) { taskResultsEl.innerHTML = '<div class="empty">未找到相关任务</div>'; return; }
    taskResultsEl.innerHTML = '';
    d.tasks.forEach((t) => taskResultsEl.appendChild(renderTaskRow(t)));
  } catch {
    taskResultsEl.innerHTML = '<div class="empty">查询失败</div>';
  }
}

taskInput.addEventListener('input', () => {
  clearTimeout(taskDebounce);
  taskDebounce = setTimeout(doTaskSearch, 200);
});

// ===== 初始化 =====
loadHealth();
doItemSearch('');
doTaskSearch();
