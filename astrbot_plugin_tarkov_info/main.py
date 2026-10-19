# -*- coding: utf-8 -*-
"""
AstrBot 插件：逃离塔科夫（Escape from Tarkov）信息检索

核心能力：
  - 物品物价查询：跳蚤价 / 商人收购价 / 卖出建议，支持数量倍数
  - 物品用途查询：任务需求 / 兑换 / 合成 / 藏身处升级
  - 任务查询：503 个任务（目标 / 奖励 / 前置 / 商人），中英文搜索
  - 物价排行 / 数据集概况 / 在线刷新

数据来源：
  1. 离线库 data/items.json —— 中文名 + 用途
  2. 在线 json.tarkov.dev —— 实时价格 + 任务（tasks + tasks_zh 中文名）

指令：
  /塔科夫 <物品名> [数量]     查物价（别名 /tk /tarkov）
  /塔科夫用途 <物品名>        查用途明细（别名 /tk用途）
  /塔科夫任务 <关键词>        查任务（别名 /tk任务 /任务）
  /塔科夫榜 [n]               物价排行（别名 /tk榜）
  /塔科夫刷新                 在线更新实时价 + 任务（别名 /tk刷新）
  /塔科夫信息                 数据集概况（别名 /tk信息）
"""

from __future__ import annotations

import asyncio
from typing import Optional

try:
    from quart import jsonify, request
except ImportError:  # pragma: no cover - 无 quart 时（测试环境）降级为空实现
    jsonify = None
    request = None

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star

try:
    from astrbot.api.star import register
except ImportError:  # pragma: no cover
    def register(*args, **kwargs):
        def _deco(cls):
            return cls
        return _deco

from astrbot.api import logger

try:
    from .tarkov_data import Dataset, rub
except ImportError:  # pragma: no cover
    from tarkov_data import Dataset, rub

PLUGIN_NAME = "tarkov_info"

COMMAND_TOKENS = {
    "tk", "tarkov", "塔科夫", "塔科夫物价", "物价",
    "tkrank", "tk榜", "塔科夫榜", "物价榜", "排行榜",
    "tku", "tk用途", "塔科夫用途", "用途",
    "tktask", "tk任务", "塔科夫任务", "任务",
    "tkrefresh", "tk刷新", "塔科夫刷新", "刷新物价",
    "tkinfo", "tk信息", "塔科夫信息", "物价信息",
}

MAX_CANDIDATES = 12
MAX_TASKS = 10

_dataset = Dataset()


def cmd(name: str, aliases=()):
    """注册指令，兼容不支持 alias 参数的旧版 AstrBot。"""
    def _deco(func):
        try:
            return filter.command(name, alias=set(aliases))(func)
        except TypeError:
            wrapped = filter.command(name)(func)
            for a in aliases:
                wrapped = filter.command(a)(wrapped)
            return wrapped
    return _deco


async def _run_blocking(func, *args, **kwargs):
    """把同步阻塞函数放进线程执行。"""
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except AttributeError:  # pragma: no cover
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _strip_command(raw: str) -> str:
    """去掉开头的指令名与唤醒前缀。"""
    s = (raw or "").strip()
    if not s:
        return ""
    tokens = s.split()
    head = tokens[0].lstrip("/#").lower()
    if head in COMMAND_TOKENS or tokens[0].startswith(("/", "#")):
        tokens = tokens[1:]
    return " ".join(tokens).strip()


def _split_qty(text: str) -> tuple:
    """从查询串尾部剥离数量。"""
    qty = 1
    parts = text.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        try:
            q = int(parts[-1])
            if q >= 1:
                qty = min(q, 999999)
                parts = parts[:-1]
        except ValueError:
            pass
    return " ".join(parts).strip(), qty


def _has_price(hit: dict) -> bool:
    it = hit.get("item") or {}
    return it.get("f") is not None or it.get("t") is not None


def _pick_single(hits: list, text: str):
    if len(hits) == 1:
        return hits[0]
    exact = [h for h in hits if h["name"] == text]
    if len(exact) == 1:
        if _has_price(exact[0]) or not any(_has_price(h) for h in hits):
            return exact[0]
    return None


def _fmt_candidates(hits: list) -> str:
    lines = [f"找到 {len(hits)} 个匹配，请输入更完整的名称："]
    ds = _dataset
    for i, h in enumerate(hits[:MAX_CANDIDATES], 1):
        it = h["item"]
        lv = ds.live_for(it.get("id") or "")
        price = lv.get("f") or it.get("f")
        mark = ""
        if price is None:
            price = lv.get("sell") or it.get("t")
            if price is not None:
                mark = "（商人）"
        tail = f"（{h['variants']} 变体）" if h.get("variants", 1) > 1 else ""
        lines.append(f"{i:>2}. {h['name']}{tail}  {rub(price)}{mark}")
    if len(hits) > MAX_CANDIDATES:
        lines.append(f"…共 {len(hits)} 个")
    return "\n".join(lines)


def _do_query(text: str, qty: int) -> str:
    ds = _dataset
    ds.load()
    hits = ds.search(text, limit=MAX_CANDIDATES + 8)
    if not hits:
        return f"没找到与「{text}」相关的物品。试试关键词片段，例如：吗啡、狗牌、螺丝刀、显卡"
    single = None if len(hits) == 1 else _pick_single(hits, text)
    if len(hits) == 1:
        return ds.item_report(hits[0], qty=qty)
    if single is None:
        return _fmt_candidates(hits)
    return ds.item_report(single, qty=qty)


def _do_usage(text: str) -> str:
    ds = _dataset
    ds.load()
    hits = ds.search(text, limit=MAX_CANDIDATES + 8)
    if not hits:
        return f"没找到与「{text}」相关的物品。"
    single = None if len(hits) == 1 else _pick_single(hits, text)
    if len(hits) == 1:
        return ds.usage_report(hits[0])
    if single is None:
        return _fmt_candidates(hits)
    return ds.usage_report(single)


def _do_task(text: str) -> str:
    ds = _dataset
    ds.load()
    if not ds.tasks:
        return "任务库为空，请先 /塔科夫刷新 拉取任务数据。"
    tasks = ds.search_tasks(text, limit=MAX_TASKS)
    if not tasks:
        return f"没找到与「{text}」相关的任务。试试：首秀、惩罚者、枪匠、医疗隐私"
    if len(tasks) == 1:
        return ds.task_report(tasks[0])
    # 多个任务：先列清单
    lines = [f"找到 {len(tasks)} 个任务，请输入更精确的关键词查看详情："]
    for i, t in enumerate(tasks, 1):
        name = t.get("name_zh") or t.get("name_en")
        trader = t.get("trader_zh") or ""
        lines.append(f"{i:>2}. {name}  [{trader}]")
    return "\n".join(lines)


def _do_rank(arg: str) -> str:
    ds = _dataset
    ds.load()
    n = 10
    parts = arg.split()
    if parts and parts[-1].isdigit():
        try:
            n = max(1, min(30, int(parts[-1])))
        except ValueError:
            n = 10
    return ds.rank_report(n)


def _do_refresh() -> str:
    ds = _dataset
    ds.load()
    res = ds.refresh_online(force=True)
    if not res.get("ok"):
        return f"在线刷新失败：{res.get('msg', '未知错误')}\n离线物品库仍可正常查询。"
    return (
        f"已更新：{res.get('items', 0)} 件物品价格、{res.get('tasks', 0)} 个任务。\n"
        "来源：json.tarkov.dev"
    )


@register(
    PLUGIN_NAME,
    "sanddiao",
    "逃离塔科夫信息检索：物价/用途/任务查询，中英文搜索",
    "1.0.0",
    "",
)
class TarkovInfoPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._register_web_apis()
        logger.info(
            "[tarkov_info] 插件已加载，可用指令："
            "/塔科夫 /塔科夫用途 /塔科夫任务 /塔科夫榜 /塔科夫刷新 /塔科夫信息"
        )

    # ------------------------------------------------------------------ #
    #  Web API（供 dashboard 面板调用）
    # ------------------------------------------------------------------ #
    def _register_web_apis(self) -> None:
        """注册 dashboard 面板的数据 API。"""
        if not hasattr(self.context, "register_web_api"):
            logger.warning("[tarkov_info] 当前 AstrBot 版本不支持 register_web_api，跳过面板 API")
            return
        base = f"/{self.__class__.__name__}"
        self.context.register_web_api(
            f"{base}/overview", self._webapi_overview, ["GET"], "数据集概况"
        )
        self.context.register_web_api(
            f"{base}/search", self._webapi_search, ["GET"], "物品搜索"
        )
        self.context.register_web_api(
            f"{base}/tasks", self._webapi_tasks, ["GET"], "任务搜索"
        )
        self.context.register_web_api(
            f"{base}/refresh", self._webapi_refresh, ["POST"], "在线刷新"
        )
        logger.info(f"[tarkov_info] Web API 已注册，前缀={base}")

    async def _webapi_overview(self):
        try:
            stats = await _run_blocking(_dataset.stats_report)
            return jsonify({"status": "ok", "data": {"stats": stats}})
        except Exception as e:  # noqa: BLE001
            return jsonify({"status": "error", "message": str(e)}), 500

    async def _webapi_search(self):
        args = getattr(request, "args", {}) or {}
        q = str(args.get("q", "")).strip()
        if not q:
            return jsonify({"status": "error", "message": "缺少 q 参数"}), 400
        try:
            hits = await _run_blocking(_dataset.search, q, 20)
            items = []
            for h in hits:
                it = h["item"]
                lv = await _run_blocking(_dataset.live_for, it.get("id") or "")
                items.append({
                    "name": h["name"],
                    "name_en": None,
                    "flea": lv.get("f") or it.get("f"),
                    "trader": lv.get("sell") or it.get("t"),
                    "chg": lv.get("chg"),
                    "variants": h.get("variants", 1),
                    "id": it.get("id") or "",
                })
            return jsonify({"status": "ok", "data": {"items": items, "count": len(items)}})
        except Exception as e:  # noqa: BLE001
            return jsonify({"status": "error", "message": str(e)}), 500

    async def _webapi_tasks(self):
        args = getattr(request, "args", {}) or {}
        q = str(args.get("q", "")).strip()
        try:
            tasks = await _run_blocking(_dataset.search_tasks, q, 50)
            result = []
            for t in tasks:
                result.append({
                    "id": t.get("id"),
                    "name_zh": t.get("name_zh"),
                    "name_en": t.get("name_en"),
                    "trader_zh": t.get("trader_zh"),
                    "min_level": t.get("min_level"),
                    "map": t.get("map"),
                    "experience": t.get("experience"),
                    "objectives": t.get("objectives") or [],
                    "finish_items": t.get("finish_items") or [],
                    "task_requirements": t.get("task_requirements") or [],
                })
            return jsonify({"status": "ok", "data": {"tasks": result, "count": len(result)}})
        except Exception as e:  # noqa: BLE001
            return jsonify({"status": "error", "message": str(e)}), 500

    async def _webapi_refresh(self):
        try:
            res = await _run_blocking(_dataset.refresh_online, True)
            return jsonify({"status": "ok", "data": res})
        except Exception as e:  # noqa: BLE001
            return jsonify({"status": "error", "message": str(e)}), 500

    @cmd("tk", aliases={"塔科夫", "tarkov", "塔科夫物价", "物价"})
    async def tk(self, event: AstrMessageEvent):
        """查询物品物价。用法：/塔科夫 <物品名> [数量]"""
        text = _strip_command(event.message_str)
        if not text:
            yield event.plain_result(
                "用法：/塔科夫 <物品名> [数量]\n"
                "例如：/塔科夫 吗啡 5   /tk 显卡   /塔科夫 金星软膏"
            )
            return
        text, qty = _split_qty(text)
        try:
            report = await _run_blocking(_do_query, text, qty)
        except FileNotFoundError as e:
            logger.error(f"[tarkov_info] 数据缺失: {e}")
            report = f"数据文件缺失：{e}"
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_info] 查询失败: {e}")
            report = f"查询失败：{e}"
        yield event.plain_result(report)

    @cmd("tku", aliases={"tk用途", "塔科夫用途"})
    async def tku(self, event: AstrMessageEvent):
        """查询物品用途明细。用法：/塔科夫用途 <物品名>"""
        text = _strip_command(event.message_str)
        if not text:
            yield event.plain_result("用法：/塔科夫用途 <物品名>，例如：/tk用途 螺丝刀")
            return
        text, _qty = _split_qty(text)
        try:
            report = await _run_blocking(_do_usage, text)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_info] 用途查询失败: {e}")
            report = f"查询失败：{e}"
        yield event.plain_result(report)

    @cmd("tktask", aliases={"tk任务", "塔科夫任务", "任务"})
    async def tktask(self, event: AstrMessageEvent):
        """查询任务。用法：/塔科夫任务 <关键词>"""
        text = _strip_command(event.message_str)
        if not text:
            yield event.plain_result(
                "用法：/塔科夫任务 <关键词>\n"
                "例如：/塔科夫任务 首秀   /tk任务 惩罚者   /塔科夫任务 枪匠"
            )
            return
        try:
            report = await _run_blocking(_do_task, text)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_info] 任务查询失败: {e}")
            report = f"查询失败：{e}"
        yield event.plain_result(report)

    @cmd("tkrank", aliases={"tk榜", "塔科夫榜", "物价榜"})
    async def tkrank(self, event: AstrMessageEvent):
        """物价排行榜。用法：/塔科夫榜 [数量]"""
        arg = _strip_command(event.message_str)
        try:
            report = await _run_blocking(_do_rank, arg)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_info] 排行失败: {e}")
            report = f"查询失败：{e}"
        yield event.plain_result(report)

    @cmd("tkrefresh", aliases={"tk刷新", "塔科夫刷新", "刷新物价"})
    async def tkrefresh(self, event: AstrMessageEvent):
        """强制在线刷新实时价 + 任务（需联网，约 5~10 秒）。"""
        yield event.plain_result("正在拉取 tarkov.dev 最新物价与任务，请稍候…")
        try:
            report = await _run_blocking(_do_refresh)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_info] 刷新失败: {e}")
            report = f"在线刷新失败：{e}\n离线物品库仍可正常查询。"
        yield event.plain_result(report)

    @cmd("tkinfo", aliases={"tk信息", "塔科夫信息"})
    async def tkinfo(self, event: AstrMessageEvent):
        """显示当前数据集概况。"""
        try:
            report = await _run_blocking(_dataset.stats_report)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_info] 信息失败: {e}")
            report = f"读取数据集信息失败：{e}"
        yield event.plain_result(report)
