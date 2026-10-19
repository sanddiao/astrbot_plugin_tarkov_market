# -*- coding: utf-8 -*-
"""
塔科夫信息检索 · 数据层（纯 Python 标准库实现）

数据来源：
  1. 离线库 data/items.json —— 中文名 + 用途（任务/兑换/合成/藏身处），由社区数据集生成
  2. 在线 json.tarkov.dev —— 实时价格（items）+ 任务结构化数据（tasks + tasks_zh 中文名）

本模块只依赖标准库（urllib / json / gzip / threading / time），
所有网络与文件 I/O 均为同步函数，调用方应放入线程执行。
"""

from __future__ import annotations

import gzip
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
# 只读静态资源目录（插件捆绑目录，随插件分发）
DATA_DIR = os.path.join(HERE, "data")
ITEMS_JSON = os.path.join(DATA_DIR, "items.json")

UA = "AstrBot-Tarkov-Info/1.0 (research tool)"

ITEMS_URL = "https://json.tarkov.dev/regular/items"
TASKS_URL = "https://json.tarkov.dev/regular/tasks"
TASKS_ZH_URL = "https://json.tarkov.dev/regular/tasks_zh"

LIVE_TTL = 24 * 3600  # 在线数据缓存 24 小时

PLUGIN_NAME = "astrbot_plugin_tarkov_info"


def _resolve_cache_dir() -> str:
    """获取运行时缓存目录（AstrBot 规范的 plugin_data 目录）。

    优先使用 StarTools.get_data_dir(plugin_name)（即 data/plugin_data/<plugin_name>），
    失败时回退到系统临时目录，保证脱离 AstrBot 环境（测试）也能运行。
    """
    try:
        from astrbot.api.star import StarTools  # type: ignore
        d = StarTools.get_data_dir(PLUGIN_NAME)
        if d:
            return str(d)
    except Exception:
        pass
    # 回退：系统临时目录下的独立子目录
    fallback = os.path.join(tempfile.gettempdir(), "astrbot_plugin_tarkov_info")
    os.makedirs(fallback, exist_ok=True)
    return fallback

# 商人 id → 中文名
TRADER_ZH = {
    "54cb57776803fa99248b456e": "医生",
    "54cb50c76803fa8b248b4571": "普拉波尔",
    "58330581ace78e27b8b10cee": "斯基尔",
    "5a7c2eca46aef81a7ca2145d": "和平使者",
    "5935c25fb3acc3127c3d8cd9": "机械师",
    "5c0647fdd443bc2504c2d371": "拉格曼",
    "6617beeaa9cfa777ca915b7c": "裁判官",
    "579dc571d53a0658a154fbec": "围栏",
    "5ac3b934156ae10c4430e83c": "枪匠",
    "638f541a29ffd1183d187f57": "灯塔守卫",
    "656f0f98d80a697f855d34b1": "BTR司机",
}

# 地图 id → 中文名
MAP_ZH = {
    "5704e554d2720bac5b8b456e": "海关",
    "5704e4dad2720bb55b8b4567": "海岸线",
    "56f40101d2720b2a4d8b45d6": "工厂",
    "55f2d3fd4bdc2d5f408b4567": "森林",
    "59fc81d786f774390775787e": "实验室",
    "653e6760052c01c1c805532f": "曙光街区",
    "65b8d6f5cdde2479cb2a3125": "曙光街区",
    "5d0278b086f77478e1264b0e": "储备站",
    "5704e5fad2720bc05b8b4567": "灯塔",
    "5714dc692459777137212e12": "立交桥",
    "5714dbc124597777137212e0": "立交桥",
    "5704e3c2d2720bac5b8b4567": "曙光街区",
    "5714dbc024597771384a510d": "立交桥",
    "5b0fc42d86f7744a585f9105": "实验室",
    "56db0b3bd2720bb0678b4567": "中心区",
    "638c6bb37c29d34a4d7f1e02": "街区",
}

# 目标类型 → 中文
OBJ_TYPE_ZH = {
    "visit": "访问", "giveItem": "上交", "findItem": "找到",
    "findQuestItem": "找到任务物品", "giveQuestItem": "上交任务物品",
    "extract": "撤离", "shoot": "击杀", "plantItem": "安放",
    "mark": "标记", "buildWeapon": "改装", "useItem": "使用",
    "sellItem": "出售", "traderLevel": "商人等级", "skill": "技能",
    "collectItem": "收集", "placeItem": "放置", "eliminate": "消灭",
}

# 用途类型展示顺序
USAGE_ORDER = ["任务需求", "兑换材料", "兑换产出", "合成材料", "合成产出", "藏身处升级"]


def rub(n: Optional[int]) -> str:
    """数字格式化为 ₽1,234。"""
    if n is None:
        return "—"
    return f"₽{int(n):,}"


def _norm(s: str) -> str:
    """归一化：去空白、转小写、去空格。"""
    return (s or "").strip().lower().replace(" ", "")


class Dataset:
    """持有全部塔科夫数据，提供检索 / 格式化 / 在线刷新。"""

    def __init__(self, data_dir: str = DATA_DIR, cache_dir: Optional[str] = None):
        # data_dir：只读静态资源（items.json），随插件捆绑分发
        self.data_dir = data_dir
        # cache_dir：运行时缓存（live_items.json / tasks.json），写入 plugin_data 目录
        self.cache_dir = cache_dir or _resolve_cache_dir()
        self.items: List[dict] = []
        self.by_id: Dict[str, dict] = {}
        self.by_name: Dict[str, List[dict]] = {}
        self._index: List[Tuple[str, str, dict]] = []  # (norm_name, norm_id, item)
        self.tasks: Dict[str, dict] = {}
        self._loaded = False

    # ---------------- 加载 ----------------
    def load(self) -> None:
        """加载离线数据（中文名 + 用途）与在线缓存（价格 + 任务）。"""
        if self._loaded:
            return
        path = os.path.join(self.data_dir, "items.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"缺少数据文件 {path}，请检查插件 data/ 目录")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.items = data.get("items") or []
        for it in self.items:
            name = it.get("n") or ""
            iid = it.get("id") or ""
            self.by_id.setdefault(iid, it)
            self.by_name.setdefault(name, []).append(it)
            self._index.append((_norm(name), _norm(iid), it))
        self._load_live_cache()
        self._load_tasks_cache()
        self._loaded = True

    def _load_live_cache(self) -> dict:
        """读取在线价格缓存（可能不存在，返回 {}）。"""
        path = os.path.join(self.cache_dir, "live_items.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if time.time() - (data.get("updated_at") or 0) > LIVE_TTL:
                return {}
            return data
        except Exception:
            return {}

    def _load_tasks_cache(self) -> None:
        path = os.path.join(self.cache_dir, "tasks.json")
        if not os.path.exists(path):
            self.tasks = {}
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.tasks = data.get("tasks") or {}
        except Exception:
            self.tasks = {}

    def live_for(self, iid: str) -> dict:
        """取某物品的在线价格（无则空 dict）。"""
        live = self._load_live_cache()
        return (live.get("prices") or {}).get(iid) or {}

    # ---------------- 网络 ----------------
    @staticmethod
    def _http_get(url: str, timeout: int = 90) -> Tuple[int, str, str]:
        """带 UA 的 GET，返回 (status, text, etag)。"""
        headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip",
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass
                return 200, raw.decode("utf-8", "ignore"), resp.headers.get("ETag") or ""
        except urllib.error.HTTPError as e:
            return e.code, "", e.headers.get("ETag") or ""
        except Exception:
            return 0, "", ""

    @staticmethod
    def _http_json(url: str, timeout: int = 90) -> Optional[dict]:
        status, text, _ = Dataset._http_get(url, timeout)
        if status != 200:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

    # ---------------- 在线刷新 ----------------
    def refresh_online(self, force: bool = False) -> dict:
        """拉取最新物品价格 + 任务，写入本地缓存。"""
        items_json = self._http_json(ITEMS_URL)
        if not items_json:
            return {"ok": False, "msg": "items 拉取失败"}

        items_root = (items_json.get("data") or {}).get("items") or {}
        prices = {}
        names_en = {}
        newest = ""
        for iid, it in items_root.items():
            if not isinstance(it, dict):
                continue
            up = it.get("updated") or ""
            if isinstance(up, str) and up > newest:
                newest = up
            rec = {}
            if it.get("avg24hPrice") is not None:
                rec["f"] = it["avg24hPrice"]
            if it.get("lastLowPrice") is not None:
                rec["lo"] = it["lastLowPrice"]
            if it.get("low24hPrice") is not None:
                rec["low"] = it["low24hPrice"]
            if it.get("high24hPrice") is not None:
                rec["hi"] = it["high24hPrice"]
            if it.get("basePrice") is not None:
                rec["base"] = it["basePrice"]
            if it.get("changeLast48hPercent") is not None:
                rec["chg"] = it["changeLast48hPercent"]
            # 商人最高收购价 / 最低出售价
            best_sell = None
            for s in it.get("sellToTrader") or []:
                p = s.get("priceRUB") or s.get("price") or 0
                if p and (best_sell is None or p > best_sell):
                    best_sell = p
            if best_sell is not None:
                rec["sell"] = best_sell
            best_buy = None
            for b in it.get("buyFromTrader") or []:
                p = b.get("priceRUB") or b.get("price") or 0
                if p and (best_buy is None or p < best_buy):
                    best_buy = p
            if best_buy is not None:
                rec["buy"] = best_buy
            if it.get("width") and it.get("height"):
                rec["slot"] = f"{it['width']}×{it['height']}"
            en = it.get("normalizedName") or ""
            if en:
                names_en[iid] = en
            if rec:
                prices[iid] = rec

        live = {
            "updated_at": time.time(),
            "data_updated": newest,
            "source": "json.tarkov.dev",
            "prices": prices,
            "names_en": names_en,
        }
        os.makedirs(self.cache_dir, exist_ok=True)
        live_path = os.path.join(self.cache_dir, "live_items.json")
        with open(live_path, "w", encoding="utf-8") as f:
            json.dump(live, f, ensure_ascii=False, separators=(",", ":"))

        # 任务 + 中文名
        task_count = self._refresh_tasks()

        return {"ok": True, "items": len(prices), "tasks": task_count}

    def _refresh_tasks(self) -> int:
        """拉取任务数据 + 中文名，写入 tasks.json。"""
        tasks_json = self._http_json(TASKS_URL)
        zh_json = self._http_json(TASKS_ZH_URL)
        if not tasks_json:
            return 0

        tasks_root = (tasks_json.get("data") or {}).get("tasks") or {}
        zh_map = {}
        if zh_json:
            for k, v in (zh_json.get("data") or {}).items():
                m = k.split(" name")
                if len(m) == 2 and m[0] and m[0][0].isalnum() and len(m[0]) == 24:
                    if isinstance(v, str) and v.strip():
                        zh_map[m[0]] = v

        normalized = {}
        for tid, t in tasks_root.items():
            if not isinstance(t, dict):
                continue
            objectives = []
            for o in t.get("objectives") or []:
                item_ids = o.get("items") or []
                items = [{"id": i, "name": self._item_name(i)} for i in item_ids]
                maps = [MAP_ZH.get(m, m) for m in (o.get("maps") or [])]
                objectives.append({
                    "type": o.get("type"),
                    "typeZh": OBJ_TYPE_ZH.get(o.get("type"), o.get("type")),
                    "count": o.get("count"),
                    "optional": o.get("optional", False),
                    "items": items,
                    "maps": list(dict.fromkeys(maps)),
                })
            fin = t.get("finishRewards") or {}
            fin_items = [
                {"id": r.get("item"), "name": self._item_name(r.get("item")), "count": r.get("count")}
                for r in (fin.get("items") or [])
            ]
            normalized[tid] = {
                "id": tid,
                "name_en": t.get("normalizedName") or t.get("name") or tid,
                "name_zh": zh_map.get(tid),
                "trader_id": t.get("trader"),
                "trader_zh": TRADER_ZH.get(t.get("trader"), t.get("trader")),
                "min_level": t.get("minPlayerLevel"),
                "map": MAP_ZH.get(t.get("map"), t.get("map")),
                "experience": t.get("experience"),
                "objectives": objectives,
                "finish_items": fin_items,
                "task_requirements": [
                    {"task": r.get("task"), "status": r.get("status") or []}
                    for r in (t.get("taskRequirements") or [])
                ],
            }

        os.makedirs(self.cache_dir, exist_ok=True)
        tasks_path = os.path.join(self.cache_dir, "tasks.json")
        with open(tasks_path, "w", encoding="utf-8") as f:
            json.dump({"updated_at": time.time(), "tasks": normalized}, f, ensure_ascii=False, separators=(",", ":"))

        self.tasks = normalized
        return len(normalized)

    def _item_name(self, iid: Optional[str]) -> str:
        """物品 id → 中文名（优先），否则英文名，否则 id。"""
        if not iid:
            return ""
        it = self.by_id.get(iid)
        if it and it.get("n"):
            return it["n"]
        live = self._load_live_cache()
        en = (live.get("names_en") or {}).get(iid)
        return en or iid

    # ---------------- 检索 ----------------
    def search(self, query: str, limit: int = 12) -> List[dict]:
        """物品搜索：中文名 / 英文名 模糊匹配，返回候选项。"""
        self.load()
        q = _norm(query)
        if not q:
            return []

        scored: Dict[str, Tuple[int, int, str]] = {}

        def consider(name: str, level: int) -> None:
            key = name
            n = _norm(name)
            if key not in scored or level < scored[key][0]:
                scored[key] = (level, len(n), name)

        live = self._load_live_cache()
        en_map = live.get("names_en") or {}

        for nname, nid, it in self._index:
            name = it.get("n") or ""
            if it.get("id") and nid == q:
                consider(name, 0)
            elif nname == q:
                consider(name, 0)
            elif name.startswith(query.strip()):
                consider(name, 1)
            elif nname.startswith(q):
                consider(name, 1)
            elif q and q in nname:
                consider(name, 2)

        # 英文名匹配（normalizedName）
        if en_map:
            qe = q.replace("-", "").replace("_", "")
            for _nname, _nid, it in self._index:
                en = _norm((en_map.get(it.get("id") or "") or "").replace("-", "").replace("_", ""))
                if not en:
                    continue
                name = it.get("n") or ""
                if en == qe:
                    consider(name, 0)
                elif en.startswith(qe):
                    consider(name, 1)
                elif len(qe) >= 3 and qe in en:
                    consider(name, 2)

        ordered = sorted(scored.values(), key=lambda x: (x[0], x[1], x[2]))[:limit]
        out = []
        for _level, _ln, name in ordered:
            variants = self.by_name.get(name) or []
            if not variants:
                continue
            priced = [v for v in variants if v.get("f") is not None or v.get("t") is not None]
            pool = priced or variants
            best = max(pool, key=lambda v: ((v.get("f") or 0), (v.get("t") or 0)))
            fs = [v.get("f") for v in pool if v.get("f") is not None]
            out.append({
                "name": name,
                "item": best,
                "variants": len(variants),
                "priced": len(priced),
                "lo": min(fs) if fs else None,
                "hi": max(fs) if fs else None,
                "all": variants,
            })
        return out

    def search_tasks(self, query: str, limit: int = 20) -> List[dict]:
        """任务搜索：中文名 / 英文名 / 目标物品 / 商人 模糊匹配。"""
        self.load()
        q = _norm(query)
        if not self.tasks:
            return []
        if not q:
            return sorted(self.tasks.values(), key=lambda t: (t.get("min_level") or 0, t.get("name_en") or ""))[:limit]

        out = []
        for t in self.tasks.values():
            name_en = _norm(t.get("name_en") or "")
            name_zh = _norm(t.get("name_zh") or "")
            trader = _norm(t.get("trader_zh") or "")
            objectives = _norm(json.dumps(t.get("objectives") or [], ensure_ascii=False))
            if q in name_en or q in name_zh or q in trader or q in objectives:
                out.append(t)
        return sorted(out, key=lambda t: (t.get("min_level") or 0, t.get("name_en") or ""))[:limit]

    # ---------------- 报告 ----------------
    def item_report(self, hit: dict, qty: int = 1) -> str:
        """单物品物价报告。"""
        item = hit["item"]
        name = hit["name"]
        variants = hit.get("variants", 1)
        iid = item.get("id") or ""
        lv = self.live_for(iid)

        lines = [f"【{name}】"]
        if variants > 1:
            extra = ""
            if hit.get("lo") is not None and hit.get("hi") is not None and hit["lo"] != hit["hi"]:
                extra = f"，变体区间 {rub(hit['lo'])}~{rub(hit['hi'])}"
            lines[0] += f" 共 {variants} 种变体（取有价最高{extra}）"

        flea = lv.get("f", item.get("f"))
        trader = lv.get("sell", item.get("t"))
        chg = lv.get("chg")
        low = lv.get("lo") or lv.get("low")
        base = lv.get("base")
        slot = lv.get("slot")

        if qty > 1:
            lines.append(f"数量：×{qty}")
        flea_total = f"（合计 {rub(flea * qty)}）" if (flea is not None and qty > 1) else ""
        lines.append(f"跳蚤市场：{rub(flea)} {flea_total}".rstrip())
        if trader is not None:
            trader_total = f"（合计 {rub(trader * qty)}）" if qty > 1 else ""
            lines.append(f"商人收购：{rub(trader)} {trader_total}".rstrip())
        else:
            lines.append("商人收购：不可出售")

        if flea and trader:
            gap = flea - trader
            better = "跳蚤市场" if gap > 0 else "商人"
            hint = "注意跳蚤需缴手续费" if gap > 0 else ""
            lines.append(f"建议：卖给{better}更划算，差价 {rub(abs(gap))} {hint}".rstrip())
        elif flea:
            lines.append("建议：仅可在跳蚤市场出售")
        elif trader:
            lines.append("建议：无跳蚤报价，只能卖给商人")
        else:
            lines.append("提示：该物品暂无报价（多为任务专用/不可交易物品）")

        extra = []
        if low is not None:
            extra.append(f"近期最低 {rub(low)}")
        if base is not None:
            extra.append(f"基准价 {rub(base)}")
        if chg is not None:
            arrow = "↑" if chg >= 0 else "↓"
            extra.append(f"48h {arrow}{abs(chg):.1f}%")
        if slot:
            extra.append(f"占格 {slot}")
        if extra:
            lines.append("参考：" + " · ".join(extra))

        src = "在线实时价（json.tarkov.dev）" if lv else "本地离线库"
        lines.append(f"数据来源：{src}")
        return "\n".join(lines)

    def usage_report(self, hit: dict, per_type: int = 6) -> str:
        """单物品用途明细报告。"""
        item = hit["item"]
        name = hit["name"]
        u = item.get("u") or {}
        if not u:
            return f"【{name}】暂无记录的用途。"

        lines = [f"【{name}】用途明细"]
        for k in USAGE_ORDER:
            lst = u.get(k) or []
            if not lst:
                continue
            lines.append(f"—— {k}（{len(lst)} 条）")
            for s in lst[:per_type]:
                lines.append(f"  · {s}")
            if len(lst) > per_type:
                lines.append(f"  …还有 {len(lst) - per_type} 条")
        for k in u:
            if k in USAGE_ORDER:
                continue
            lst = u.get(k) or []
            if lst:
                lines.append(f"—— {k}（{len(lst)} 条）")
                for s in lst[:per_type]:
                    lines.append(f"  · {s}")
        return "\n".join(lines)

    def task_report(self, task: dict) -> str:
        """单任务详情报告。"""
        name = task.get("name_zh") or task.get("name_en")
        lines = [f"【任务】{name}"]
        if task.get("name_zh") and task.get("name_en"):
            lines.append(f"英文名：{task['name_en']}")
        if task.get("trader_zh"):
            lines.append(f"发布商人：{task['trader_zh']}")
        if task.get("min_level") is not None:
            lines.append(f"最低等级：Lv.{task['min_level']}")
        if task.get("map"):
            lines.append(f"主要地图：{task['map']}")
        if task.get("experience") is not None:
            lines.append(f"经验奖励：{task['experience']:,}")

        objectives = task.get("objectives") or []
        if objectives:
            lines.append("—— 目标")
            for o in objectives:
                tzh = o.get("typeZh") or o.get("type")
                cnt = f" ×{o['count']}" if o.get("count") else ""
                items = "：" + "、".join(i["name"] for i in o.get("items") or []) if o.get("items") else ""
                maps = f" [{('/'.join(o['maps']))}]" if o.get("maps") else ""
                opt = "（可选）" if o.get("optional") else ""
                lines.append(f"  · {tzh}{cnt}{items}{maps}{opt}")

        fin_items = task.get("finish_items") or []
        if fin_items:
            lines.append("—— 完成奖励")
            for it in fin_items[:8]:
                lines.append(f"  · {it['name']} ×{it['count']}")

        reqs = task.get("task_requirements") or []
        if reqs:
            lines.append("—— 前置任务")
            for r in reqs:
                lines.append(f"  · {r['task']}（{','.join(r['status'])}）")
        return "\n".join(lines)

    def rank_report(self, n: int = 10) -> str:
        """物价排行。"""
        self.load()
        live = self._load_live_cache()
        live_p = live.get("prices") or {}
        rows = []
        for it in self.items:
            lv = live_p.get(it.get("id") or "", {})
            price = lv.get("f") or it.get("f")
            if not price:
                continue
            rows.append((price, it.get("n") or "?"))
        rows.sort(key=lambda x: -x[0])
        rows = rows[: max(1, min(n, 30))]
        if not rows:
            return "暂无可用于排行的物价数据。"
        src = "在线（tarkov.dev）" if live else "本地离线库"
        lines = [f"塔科夫物价排行 Top{len(rows)}  [{src}]"]
        for i, (p, nm) in enumerate(rows, 1):
            lines.append(f"{i:>2}. {nm}  {rub(p)}")
        return "\n".join(lines)

    def stats_report(self) -> str:
        """数据集概况。"""
        self.load()
        live = self._load_live_cache()
        if live:
            m = int((time.time() - live.get("updated_at", 0)) / 60)
            live_age = f"在线物价 {m} 分钟前更新"
        else:
            live_age = "在线物价 未刷新/已过期"
        n_price = sum(1 for i in self.items if i.get("f") or i.get("t"))
        return (
            "塔科夫信息检索\n"
            f"离线物品库：{len(self.items)} 件（有价 {n_price} 件）\n"
            f"任务库：{len(self.tasks)} 个\n"
            f"{live_age}\n"
            "用法：/塔科夫 <物品名> [数量]"
        )
