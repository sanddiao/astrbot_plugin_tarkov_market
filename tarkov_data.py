# -*- coding: utf-8 -*-
"""
塔科夫物价插件 · 数据层

职责：
  1. 载入离线数据集 data/items.json（由 tools/build_dataset.py 从 item_usage.xlsx 生成）
  2. 提供「精确 → 前缀 → 子串 → 顺次匹配」四级模糊搜索
  3. 格式化单物品的价格报告（跳蚤价 vs 商人收购价，给出卖出建议）
  4. 可选的在线刷新：从 json.tarkov.dev 静态包拉取最新价，写入 data/live_prices.json

设计原则：
  - 离线优先：任何情况下查价都不依赖网络，网络只是"锦上添花"
  - 纯标准库：不引入 requests / openpyxl，服务器零安装成本
  - 本文件里的所有函数都是「同步阻塞」的，禁止在 async 指令处理器里直接调用，
    必须由 main.py 用 asyncio.to_thread 包一层（否则会阻塞 AstrBot 事件循环）

关于「每次查询前自动取最新价」：
  tarkov.dev 只提供整包数据（16.5MB，无单物品接口），但支持两件事让实时查询变便宜：
    1. gzip 压缩：传输只要 1.8MB（9 倍压缩比）
    2. ETag 协商：带 If-None-Match 请求，数据未变时返回 304，零字节
  所以 ensure_fresh() 每次查询前花约 1 秒问一句"变了吗"，没变就直接用缓存，
  变了才真正下载。语义上等价于"每次都拿最新价"，但代价极低。
"""

from __future__ import annotations

import gzip
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
ITEMS_JSON = os.path.join(DATA_DIR, "items.json")
LIVE_JSON = os.path.join(DATA_DIR, "live_prices.json")

# 在线数据源（tarkov.dev 前端自己用的静态包，无需 API Key）
JSON_ITEMS_URL = "https://json.tarkov.dev/regular/items"
JSON_ITEMS_ZH_URL = "https://json.tarkov.dev/regular/items_zh"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AstrBot-Tarkov-Market/1.0"

# 实时价的保鲜期（秒）。超过这么久都没能成功连上源，才认为缓存不可信、退回离线库。
# 正常情况下 ensure_fresh() 会在每次查询时续期，不会真的等到过期。
LIVE_TTL = 24 * 3600

# 每次查询前是否自动确认一次"线上有没有变价"（推荐开启）
AUTO_REFRESH = True

# 两次线上检查之间的最小间隔（秒）。tarkov.dev 的数据是小时级更新的，
# 60 秒内的重复检查没有意义，设成 0 就变成"每条消息都真的发一次请求"。
REFRESH_MIN_INTERVAL = 60

# 并发保护：多个查询同时进来时只允许一个真正去下载，其余直接复用结果
_REFRESH_LOCK = threading.Lock()

# 商人社区习惯译名（官方语言包只给简介，名字需自己补）
TRADER_ZH = {
    "prapor": "普罗波尔", "therapist": "治疗师", "fence": "围墙商人",
    "skier": "滑雪者", "peacekeeper": "维和者", "mechanic": "机械师",
    "ragman": "拾荒商人", "jaeger": "猎人", "lightkeeper": "灯塔人",
    "ref": "Ref", "btr-driver": "BTR司机",
}

# 用途类型 → 展示顺序 & 简称
USAGE_ORDER = ["任务需求", "兑换材料", "合成材料", "兑换产出", "合成产出", "藏身处升级"]


def rub(n: Optional[int]) -> str:
    """把卢布数额格式化成 ₽1,234。"""
    if n is None:
        return "—"
    return f"₽{int(n):,}"


def _norm(s: str) -> str:
    """归一化：去空格、转小写，便于中文之外还能匹配英文/数字型号。"""
    return (s or "").strip().lower().replace(" ", "")


def _is_subseq(needle: str, hay: str) -> bool:
    """判断 needle 是否为 hay 的顺次子序列（用于容错输入，如 'm4a1' 匹配 'M4A1 5.56'）。"""
    i = 0
    for ch in hay:
        if ch == needle[i]:
            i += 1
            if i == len(needle):
                return True
    return False


class Dataset:
    """持有全部物品数据，并提供检索 / 格式化 / 在线刷新。"""

    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.items: List[dict] = []
        self.by_id: Dict[str, dict] = {}
        self.by_name: Dict[str, List[dict]] = {}
        self.meta: dict = {}
        self._loaded = False
        # 索引项：(norm_name, norm_id, item)
        self._index: List[Tuple[str, str, dict]] = []

    # ------------------------------------------------------------------ 载入
    def load(self) -> None:
        """载入离线数据集并建立索引。可重复调用，只有首次真正读盘。"""
        if self._loaded:
            return
        path = os.path.join(self.data_dir, "items.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"缺少数据文件 {path}。请先运行：python tools/build_dataset.py <item_usage.xlsx>"
            )
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.meta = {k: v for k, v in data.items() if k != "items"}
        self.items = data.get("items") or []
        for it in self.items:
            name = it.get("n") or ""
            iid = it.get("id") or ""
            self.by_id.setdefault(iid, it)
            self.by_name.setdefault(name, []).append(it)
            self._index.append((_norm(name), _norm(iid), it))
        self._loaded = True

    # ------------------------------------------------------------------ 搜索
    def search(self, query: str, limit: int = 12) -> List[dict]:
        """模糊搜索，返回按「名字」分组后的候选列表。

        匹配优先级（同级按名称长度升序，短名更可能是用户想要的）：
          0 完全同名 / 完全同 ID
          1 名称以关键词开头
          2 名称包含关键词
          3 关键词字符按顺次出现在名称中（快照式容错）

        重名（如『已密封的武器箱』有 50 个变体）会被折叠成一条，
        variants 保留变体总数，并按价格取最有代表性的那个。
        """
        self.load()
        q = _norm(query)
        if not q:
            return []

        scored: Dict[str, Tuple[int, int, str]] = {}  # name -> (score, len, name)

        def consider(name: str, level: int) -> None:
            n = _norm(name)
            key = name
            if key not in scored or level < scored[key][0]:
                scored[key] = (level, len(n), name)

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
            elif len(q) >= 3 and _is_subseq(q, nname):
                consider(name, 3)

        # 英文别名：实时库里的 normalizedName（如 keycard / propital）
        # 让用户可以用英文原名查东西，弥补中文译名里拉丁词不全的问题
        en_map = self.live_prices().get("names_en") or {}
        if isinstance(en_map, dict) and en_map:
            for _nname, _nid, it in self._index:
                # 官方英文名是连字符式（graphics-card / m4a1），去掉标点再比对，
                # 否则用户敲 "graphics card" 这种带空格的写法匹配不上
                en = _norm((en_map.get(it.get("id") or "") or "").replace("-", "").replace("_", ""))
                if not en:
                    continue
                qe = q.replace("-", "").replace("_", "")
                name = it.get("n") or ""
                if en == qe:
                    consider(name, 0)
                elif en.startswith(qe):
                    consider(name, 1)
                elif len(qe) >= 3 and qe in en:
                    consider(name, 2)

        ordered = sorted(scored.values(), key=lambda x: (x[0], x[1], x[2]))[:limit]

        out: List[dict] = []
        for _level, _ln, name in ordered:
            variants = self.by_name.get(name) or []
            if not variants:
                continue
            # 代表选择：优先在「有价格」的变体里挑，避免挑中恰好无报价的那个
            priced = [v for v in variants if (v.get("f") is not None or v.get("t") is not None)]
            pool = priced or variants
            best = max(pool, key=lambda v: ((v.get("f") or 0), (v.get("t") or 0)))
            fs = [v.get("f") for v in pool if v.get("f") is not None]
            rng = (min(fs), max(fs)) if fs else (None, None)
            out.append({
                "name": name,
                "item": best,
                "variants": len(variants),
                "priced": len(priced),
                "lo": rng[0],
                "hi": rng[1],
                "all": variants,
            })
        return out

    # ------------------------------------------------------- 实时价（在线刷新）
    def live_prices(self) -> dict:
        """返回未过期的实时价数据；过期或不存在返回 {}。"""
        if not os.path.exists(LIVE_JSON):
            return {}
        try:
            with open(LIVE_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return {}
        ts = data.get("updated_at", 0)
        if not isinstance(ts, (int, float)):
            return {}
        if time.time() - ts > LIVE_TTL:
            return {}
        return data

    def live_for(self, iid: str) -> dict:
        live = self.live_prices()
        return (live.get("prices") or {}).get(iid) or {}

    def has_live_cache(self) -> bool:
        """手上是否已经有一份可用的实时价（用于决定要不要提示用户"首次拉取较慢"）。"""
        return bool(self.live_prices().get("prices"))

    @staticmethod
    def _http_get(url: str, timeout: int = 90,
                  extra_headers: Optional[dict] = None) -> Tuple[int, str, str]:
        """带一次重定向跟随的 GET，自动请求 gzip。

        返回 (status, text, etag)：
          status == 200 → 有数据；304 → 线上未变更（text 为空）；0 → 失败
        注意：urllib 默认不跟随 308，这里手动补上。
        """
        headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                   "Accept-Encoding": "gzip", "Referer": "https://tarkov.dev/"}
        if extra_headers:
            headers.update(extra_headers)
        for _ in range(2):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
                        try:
                            raw = gzip.decompress(raw)
                        except Exception:  # noqa: BLE001
                            pass
                    return 200, raw.decode("utf-8", "ignore"), resp.headers.get("ETag") or ""
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    return 304, "", e.headers.get("ETag") or ""
                loc = e.headers.get("Location")
                if e.code in (301, 302, 303, 307, 308) and loc:
                    url = urllib.parse.urljoin(url, loc)
                    continue
                return 0, "", ""
            except Exception:  # noqa: BLE001
                return 0, "", ""
        return 0, "", ""

    def _http_json(self, url: str, timeout: int = 90) -> Optional[dict]:
        """简单的 JSON GET（无 ETag 协商）。"""
        status, text, _etag = self._http_get(url, timeout=timeout)
        if status != 200:
            return None
        try:
            return json.loads(text)
        except Exception:  # noqa: BLE001
            return None

    def _load_live_raw(self) -> dict:
        """读取实时价缓存，不做 TTL 判断（续期等场景需要看原始数据）。"""
        try:
            with open(LIVE_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _touch_live(self, etag: str = "") -> dict:
        """线上确认"未变更"后给缓存续期（刷新 checked_at / updated_at）。"""
        data = self._load_live_raw()
        if not data.get("prices"):
            return {}
        now = time.time()
        data["checked_at"] = now
        data["updated_at"] = now
        if etag:
            data["etag"] = etag
        try:
            os.makedirs(os.path.dirname(LIVE_JSON), exist_ok=True)
            with open(LIVE_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        except Exception:  # noqa: BLE001
            pass
        return data

    def ensure_fresh(self, min_interval: int = REFRESH_MIN_INTERVAL) -> dict:
        """每次查询前调用：确认手上的价是不是最新的。

        流程：
          没有缓存      → 全量拉一次（首次，约 6 秒）
          有缓存且刚查过 → 直接跳过（min_interval 内不发请求）
          有缓存        → 带 ETag 问一句（约 1 秒，未变更时零字节）
                          304 → 说明线上没变，缓存就是最新的，续期即可
                          200 → 数据变了，整包更新
        任何失败都静默降级，绝不影响本次查询（离线库照常可用）。
        """
        if not AUTO_REFRESH:
            return {"ok": False, "skipped": True, "items": 0}
        with _REFRESH_LOCK:
            cur = self._load_live_raw()
            has_cache = bool(cur.get("prices"))
            if has_cache:
                last_check = cur.get("checked_at") or cur.get("updated_at") or 0
                try:
                    last_check = float(last_check)
                except (TypeError, ValueError):
                    last_check = 0.0
                if min_interval > 0 and time.time() - last_check < min_interval:
                    return {"ok": True, "skipped": True, "items": len(cur["prices"])}
            try:
                res = self.refresh_online()
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "skipped": False, "items": 0,
                        "msg": f"{type(e).__name__}: {e}"}
            res["skipped"] = False
            return res

    def refresh_online(self, timeout: int = 90, force: bool = False) -> dict:
        """拉取最新物价，写入 data/live_prices.json。

        默认走 ETag 协商：线上没变就返回 unchanged 并给缓存续期，不重复下载。
        force=True 时忽略 ETag 强制全量重拉。

        返回 {"ok": bool, "items": int, "msg": str, "unchanged": bool}。
        失败时保留旧片（哪怕过期），保证离线库始终是兜底。
        """
        etag = ""
        if not force:
            etag = str(self._load_live_raw().get("etag") or "")
        extra = {"If-None-Match": etag} if etag else None

        t0 = time.time()
        status, text, new_etag = self._http_get(JSON_ITEMS_URL, timeout=timeout,
                                                extra_headers=extra)
        if status == 304:
            data = self._touch_live(new_etag or etag)
            return {"ok": True, "unchanged": True, "items": len(data.get("prices") or {}),
                    "msg": f"线上无变化（{time.time() - t0:.1f}s，零流量）"}
        if status != 200:
            return {"ok": False, "unchanged": False, "items": 0, "msg": "主数据源请求失败"}

        try:
            raw = json.loads(text)
        except Exception:  # noqa: BLE001
            return {"ok": False, "unchanged": False, "items": 0, "msg": "响应不是合法 JSON"}
        items_root = (raw.get("data") or {}).get("items") or {}
        if not isinstance(items_root, dict) or not items_root:
            return {"ok": False, "unchanged": False, "items": 0, "msg": "数据源结构异常"}

        prices: Dict[str, dict] = {}
        names: Dict[str, str] = {}
        newest = ""  # 数据包内记录的快照时间（各物品 updated 字段的最大值）
        for iid, it in items_root.items():
            if not isinstance(it, dict):
                continue
            up = it.get("updated")
            if isinstance(up, str) and up > newest:
                newest = up
            flea = it.get("avg24hPrice")
            low = it.get("lastLowPrice")
            # 最高收购价
            best_sell = None
            for s in (it.get("sellToTrader") or []):
                p = s.get("priceRUB") or 0
                if p and (best_sell is None or p > best_sell[0]):
                    best_sell = (p, s.get("trader") or "")
            # 最低商人售价（用于判断"买商人还是买跳蚤划算"）
            best_buy = None
            for b in (it.get("buyFromTrader") or []):
                p = b.get("priceRUB") or 0
                if p and (best_buy is None or p < best_buy[0]):
                    best_buy = (p, b.get("trader") or "")

            rec = {}
            if flea is not None:
                rec["f"] = flea
            if low is not None:
                rec["lo"] = low
            if it.get("high24hPrice") is not None:
                rec["hi"] = it.get("high24hPrice")
            if it.get("basePrice") is not None:
                rec["base"] = it.get("basePrice")
            if it.get("changeLast48hPercent") is not None:
                rec["chg"] = it.get("changeLast48hPercent")
            if best_sell:
                rec["sell"] = best_sell[0]
            if best_buy:
                rec["buy"] = best_buy[0]
            if it.get("width"):
                rec["slot"] = f"{it.get('width')}×{it.get('height')}"
            if rec:
                prices[iid] = rec

            en = it.get("normalizedName") or ""
            if en:
                names[iid] = en

        payload = {
            "updated_at": time.time(),
            "checked_at": time.time(),
            "etag": new_etag or etag,
            "source": "json.tarkov.dev",
            "data_updated": newest or None,
            "prices": prices,
            "names_en": names,
        }
        os.makedirs(os.path.dirname(LIVE_JSON), exist_ok=True)
        with open(LIVE_JSON, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        return {"ok": True, "unchanged": False, "items": len(prices),
                "data_updated": newest or "", "msg": "已更新"}

    # ------------------------------------------------------------------ 报告
    def usage_summary(self, item: dict) -> List[str]:
        """把用途字典压成一到两行摘要。"""
        u = item.get("u") or {}
        parts = []
        for k in USAGE_ORDER:
            lst = u.get(k) or []
            if lst:
                parts.append(f"{k} {len(lst)}")
        for k in u:
            if k not in USAGE_ORDER and u.get(k):
                parts.append(f"{k} {len(u[k])}")
        return parts

    def item_report(self, hit: dict, qty: int = 1, with_usage: bool = True) -> str:
        """生成单个物品的物价报告（纯文本）。

        hit 是 search() 返回的候选字典（含可能的多变体）。
        """
        item = hit["item"]
        name = hit["name"]
        variants = hit.get("variants", 1)
        iid = item.get("id") or ""

        lines: List[str] = []
        head = f"【{name}】"
        if variants > 1:
            extra = ""
            if hit.get("lo") is not None and hit.get("hi") is not None and hit["lo"] != hit["hi"]:
                extra = f"，变体区间 {rub(hit['lo'])}~{rub(hit['hi'])}"
            head += f"  共 {variants} 种变体（下列取有价最高者{extra}）"
        lines.append(head)

        # 实时价优先，其次本地离线库
        lv = self.live_for(iid)
        flea = lv.get("f", item.get("f"))
        low = lv.get("lo")
        trader = lv.get("sell", item.get("t"))
        chg = lv.get("chg")
        base = lv.get("base")

        if qty > 1:
            lines.append(f"数量：×{qty}")

        flea_total = f"（合计 {rub(flea * qty)}）" if (flea is not None and qty > 1) else ""
        lines.append(f"跳蚤市场：{rub(flea)} {flea_total}".rstrip())

        trader_total = f"（合计 {rub(trader * qty)}）" if (trader is not None and qty > 1) else ""
        if trader is not None:
            lines.append(f"商人收购：{rub(trader)} {trader_total}".rstrip())
        else:
            lines.append("商人收购：不可出售")

        # 卖出建议
        if flea and trader:
            gap = flea - trader
            better = "跳蚤市场" if gap > 0 else "商人"
            hint = "注意跳蚤需扣手续费" if gap > 0 else ""
            lines.append(f"建议：卖给{better}更划算，差价 {rub(abs(gap))} {hint}".rstrip())
        elif flea:
            lines.append("建议：仅可在跳蚤市场出售")
        elif trader:
            lines.append("建议：无跳蚤报价，只能卖给商人")
        else:
            lines.append("备注：该物品暂未记录报价（多为任务专用/不可交易道具）")

        extra = []
        if low is not None:
            extra.append(f"近期最低 {rub(low)}")
        if base is not None:
            extra.append(f"基础价 {rub(base)}")
        if chg is not None:
            arrow = "↑" if chg >= 0 else "↓"
            extra.append(f"48h {arrow}{abs(chg):.1f}%")
        slot = lv.get("slot")
        if slot:
            extra.append(f"占格 {slot}")
        if extra:
            lines.append("参考：" + " · ".join(extra))

        if with_usage:
            us = self.usage_summary(item)
            if us:
                lines.append("用途：" + " · ".join(us))
            tasks = (item.get("u") or {}).get("任务需求") or []
            if tasks:
                show = tasks[:3]
                tail = f" 等 {len(tasks)} 条" if len(tasks) > 3 else ""
                lines.append("任务：" + "；".join(show) + tail)

        # 用了实时价就照实标注，别把实时数据说成离线快照
        src = "在线实时价（json.tarkov.dev）" if lv else "本地离线库（tarkov.dev 快照）"
        lines.append(f"数据来源：{src}")
        return "\n".join(lines)

    def usage_report(self, hit: dict, per_type: int = 6) -> str:
        """生成物品的用途明细报告。"""
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
            lines.append(f"── {k}（{len(lst)} 条）")
            for s in lst[:per_type]:
                lines.append(f"  · {s}")
            if len(lst) > per_type:
                lines.append(f"  …还有 {len(lst) - per_type} 条")
        for k in u:
            if k in USAGE_ORDER:
                continue
            lst = u.get(k) or []
            if lst:
                lines.append(f"── {k}（{len(lst)} 条）")
                for s in lst[:per_type]:
                    lines.append(f"  · {s}")
        return "\n".join(lines)

    def rank_report(self, n: int = 10) -> str:
        """跳蚤价排行榜。"""
        self.load()
        live = self.live_prices()
        live_p = live.get("prices") or {}

        rows = []
        for it in self.items:
            lv = live_p.get(it.get("id") or "", {})
            price = lv.get("f") or it.get("f")
            if not price:
                continue
            rows.append((price, it.get("n") or "?"))
        rows.sort(key=lambda x: -x[0])
        rows = rows[:max(1, min(n, 30))]

        if not rows:
            return "暂无可用于排行的价格数据。"

        src = "实时（tarkov.dev）" if live else "本地离线库"
        lines = [f"塔科夫物价排行 Top{len(rows)}  [{src}]"]
        for i, (p, nm) in enumerate(rows, 1):
            lines.append(f"{i:>2}. {nm}  {rub(p)}")
        return "\n".join(lines)

    def stats_report(self) -> str:
        """数据集概况。"""
        self.load()
        live = self.live_prices()
        live_age = ""
        if live:
            m = (time.time() - live.get("updated_at", 0)) / 60
            live_age = f"实时库 {int(m)} 分钟前更新"
        else:
            live_age = "实时库 未启用/已过期"
        gen = (self.meta.get("generated_at") or "")[:19].replace("T", " ")
        n_price = sum(1 for i in self.items if i.get("f") or i.get("t"))
        return (
            "塔科夫物价插件\n"
            f"离线物品库：{len(self.items)} 件（有价 {n_price} 件）\n"
            f"离线库生成：{gen or '未知'}\n"
            f"{live_age}\n"
            "用法：/塔科夫 <物品名> [数量]"
        )
