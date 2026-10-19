# -*- coding: utf-8 -*-
"""
AstrBot 插件：逃离塔科夫（Escape from Tarkov）物价查询

核心能力：
  - 定向查询任意物品的跳蚤价 / 商人收购价，并给出"卖给谁更划算"的建议
  - 支持数量倍数（/塔科夫 吗啡 5 → 5 份总价）
  - 附带物品用途（任务需求、商人兑换、工作台合成、藏身处升级）
  - 物价排行榜、数据集概况、手动在线刷新

数据来源：
  1. 离线库 data/items.json（由 tools/build_dataset.py 从 item_usage.xlsx 生成）
     —— 任何时候都能查，不需要联网
  2. 在线实时价 json.tarkov.dev（可选，/塔科夫刷新 触发，写入 data/live_prices.json）

指令：
  /塔科夫 <物品名> [数量]      查物价（别名 /tk /tarkov）
  /塔科夫用途 <物品名>         查用途明细（别名 /tk用途 /用途）
  /塔科夫榜 [n]                物价排行（别名 /tk榜）
  /塔科夫刷新                  在线更新实时价（别名 /tk刷新）
  /塔科夫信息                  数据集概况（别名 /tk信息）

并发约定：
  所有涉及文件读取 / 网络请求 / JSON 解析的同步函数，一律通过 _run_blocking
  放进线程池执行，绝不在 async 指令处理器里直接调用阻塞 I/O。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star

try:
    # 旧版 AstrBot（<= 3.x）用 @register 声明插件元信息
    from astrbot.api.star import register
except ImportError:  # pragma: no cover - 新版 AstrBot 已移除该符号
    # 新版 AstrBot 完全由 metadata.yaml 注册，这里退化成空装饰器
    def register(*args, **kwargs):
        def _deco(cls):
            return cls

        return _deco

from astrbot.api import logger

try:
    # 正常情况：插件目录作为包被 AstrBot 加载
    from .tarkov_data import Dataset, rub
except ImportError:  # pragma: no cover - 某些加载方式下 __package__ 为空
    from tarkov_data import Dataset, rub

PLUGIN_NAME = "tarkov_market"

# 已注册的指令名（含别名），用于从 message_str 里剥掉指令本身
COMMAND_TOKENS = {
    "tk", "tarkov", "塔科夫", "塔科夫物价", "物价",
    "tkrank", "tk榜", "塔科夫榜", "物价榜", "排行榜",
    "tku", "tk用途", "塔科夫用途", "用途",
    "tkrefresh", "tk刷新", "塔科夫刷新", "刷新物价",
    "tkinfo", "tk信息", "塔科夫信息", "物价信息",
}

MAX_CANDIDATES = 12

_dataset = Dataset()


def cmd(name: str, aliases=()):
    """注册指令，兼容不支持 `alias` 参数的旧版 AstrBot。

    新版支持 filter.command(name, alias={...})；旧版没有 alias 关键字会抛
    TypeError，此时改为堆叠注册多个指令名，效果等价，避免整个插件加载失败。
    """

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
    """把同步阻塞函数放进线程执行，避免阻塞 AstrBot 的事件循环。"""
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except AttributeError:  # pragma: no cover - Python < 3.9 兜底
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _strip_command(raw: str) -> str:
    """去掉开头的指令名与唤醒前缀，返回真正的查询串。

    部分版本的 message_str 会把指令本身一起带过来（如 "/塔科夫 吗啡"），
    不剥离的话会把指令名当成查询词导致搜不到。
    """
    s = (raw or "").strip()
    if not s:
        return ""
    tokens = s.split()
    head = tokens[0].lstrip("/#").lower()
    if head in COMMAND_TOKENS or tokens[0].startswith(("/", "#")):
        tokens = tokens[1:]
    return " ".join(tokens).strip()


def _split_qty(text: str) -> tuple[str, int]:
    """从查询串尾部剥离数量。'' -> ('',1)，'吗啡 5' -> ('吗啡',5)。

    位数过多不再当成数量的一部分丢弃，而是夹到上限，避免 '吗啡 99999' 整个失效。
    """
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
    """多个候选时，判断是否可以直接出报告。

    完全同名优先；但若这个精确匹配自己没有任何报价、而其他候选有，
    说明用户多半是想找变体（如『狗牌』→ BEAR/USEC 狗牌），此时应给候选列表。
    """
    if len(hits) == 1:
        return hits[0]
    exact = [h for h in hits if h["name"] == text]
    if len(exact) == 1:
        if _has_price(exact[0]) or not any(_has_price(h) for h in hits):
            return exact[0]
    return None


def _fmt_candidates(hits: list) -> str:
    """多个候选时输出带序号的精简列表。"""
    lines = [f"找到 {len(hits)} 个匹配，请输入更完整的名称：" ]
    ds = _dataset
    for i, h in enumerate(hits[:MAX_CANDIDATES], 1):
        it = h["item"]
        lv = ds.live_for(it.get("id") or "")
        price = lv.get("f") or it.get("f")
        mark = ""
        if price is None:
            # 没有跳蚤报价时退回商人收购价，避免候选列表里全是「—」
            price = lv.get("sell") or it.get("t")
            if price is not None:
                mark = "（商人）"
        tail = ""
        if h.get("variants", 1) > 1:
            tail = f"（{h['variants']} 变体）"
        lines.append(f"{i:>2}. {h['name']}{tail}  {rub(price)}{mark}")
    if len(hits) > MAX_CANDIDATES:
        lines.append(f"…共 {len(hits)} 个")
    return "\n".join(lines)


def _do_query(text: str, qty: int) -> str:
    """查价主流程（同步，需在线程里跑）。

    开箱即"最新价"：每次查询前先确认线上有没有变价（ETag 协商，未变则零流量）。
    """
    ds = _dataset
    ds.load()
    ds.ensure_fresh()
    hits = ds.search(text, limit=MAX_CANDIDATES + 8)
    if not hits:
        return f"没找到与「{text}」相关的物品。试试关键词片段，例如：吗啡、狗牌、螺丝刀"
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


def _do_rank(arg: str) -> str:
    ds = _dataset
    ds.load()
    ds.ensure_fresh()  # 排行也是看价，同样先确认最新
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
    # 手动触发一律强制重拉，不走 ETag 协商（用户就是要"现在给我拉一份新的"）
    res = ds.refresh_online(force=True)
    if not res.get("ok"):
        return (
            f"在线刷新失败：{res.get('msg', '未知错误')}\n"
            "离线物品库仍可正常查询（/塔科夫 <物品名>）。"
        )
    # 数据包自带的快照时间（UTC），换算成北京时间让用户知道多新鲜
    ts = res.get("data_updated") or (ds.live_prices().get("data_updated") or "")
    fresh = ""
    if ts:
        try:
            from datetime import datetime, timedelta, timezone

            dt = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
            fresh = f"\n数据包快照：{dt.strftime('%m-%d %H:%M')}（北京时间）"
        except Exception:  # noqa: BLE001
            fresh = f"\n数据包快照：{ts[:16]}".replace("T", " ")

    return f"已更新实时价：{res['items']} 件物品。\n来源：json.tarkov.dev{fresh}"


@register(
    PLUGIN_NAME,
    "sanddiao",
    "逃离塔科夫物价查询：定向查物品跳蚤价/商人收购价与用途",
    "1.0.0",
    "",
)
class TarkovMarketPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 这行日志是排查"指令没被接住"的关键：加载成功时控制台一定会看到它
        logger.info(
            "[tarkov_market] 插件已加载，可用指令："
            "/塔科夫 /tk /塔科夫用途 /塔科夫榜 /塔科夫刷新 /塔科夫信息"
        )

    @cmd("tk", aliases={"塔科夫", "tarkov", "塔科夫物价", "物价"})
    async def tk(self, event: AstrMessageEvent):
        """查询物品物价。用法：/塔科夫 <物品名> [数量]，例如 /塔科夫 吗啡 5"""
        text = _strip_command(event.message_str)
        if not text:
            yield event.plain_result(
                "用法：/塔科夫 <物品名> [数量]\n"
                "例如：/塔科夫 吗啡    /tk 已密封的武器箱    /塔科夫 6465 5"
            )
            return
        text, qty = _split_qty(text)
        try:
            if not _dataset.has_live_cache():
                yield event.plain_result(
                    "首次查询，正在拉取 tarkov.dev 最新物价（约 5~10 秒，之后就是秒回）…"
                )
            # 检索 + 读索引 + 自动保鲜都在线程里执行，避免卡住事件循环
            report = await _run_blocking(_do_query, text, qty)
        except FileNotFoundError as e:
            logger.error(f"[tarkov_market] 数据缺失: {e}")
            report = f"数据文件缺失：{e}"
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_market] 查询失败: {e}")
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
            logger.error(f"[tarkov_market] 用途查询失败: {e}")
            report = f"查询失败：{e}"
        yield event.plain_result(report)

    @cmd("tkrank", aliases={"tk榜", "塔科夫榜", "物价榜"})
    async def tkrank(self, event: AstrMessageEvent):
        """物价排行榜。用法：/塔科夫榜 [数量]"""
        arg = _strip_command(event.message_str)
        try:
            report = await _run_blocking(_do_rank, arg)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_market] 排行失败: {e}")
            report = f"查询失败：{e}"
        yield event.plain_result(report)

    @cmd("tkrefresh", aliases={"tk刷新", "塔科夫刷新", "刷新物价"})
    async def tkrefresh(self, event: AstrMessageEvent):
        """强制在线刷新实时物价（需联网，约 5~10 秒）。日常查询会自动保鲜，无需手动。"""
        yield event.plain_result("正在强制拉取 tarkov.dev 最新物价，请稍候…")
        try:
            report = await _run_blocking(_do_refresh)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_market] 刷新失败: {e}")
            report = f"在线刷新失败：{e}\n离线物品库仍可正常查询。"
        yield event.plain_result(report)

    @cmd("tkinfo", aliases={"tk信息", "塔科夫信息"})
    async def tkinfo(self, event: AstrMessageEvent):
        """显示当前数据集概况。"""
        try:
            report = await _run_blocking(_dataset.stats_report)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[tarkov_market] 信息失败: {e}")
            report = f"读取数据集信息失败：{e}"
        yield event.plain_result(report)
