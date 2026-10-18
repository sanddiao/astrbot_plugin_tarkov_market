#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 item_usage.xlsx 转成插件运行时使用的紧凑数据集 data/items.json。

输入表格的表头（顺序可变，按列名匹配）：
    物品ID | 物品名 | 用途类型 | 用途详情 | 物品卖给商人的价格 | 当前跳蚤价格

一行 = 一条「物品 × 用途」记录，同一个物品会出现多行，
因此本脚本按 物品ID 聚合：价格取第一条非空值，用途按类型分组去重。

设计要点：
  - 纯标准库（zipfile + xml.etree），不依赖 openpyxl，服务器环境无需装任何包
  - 输出用短字段名（id/n/t/f/u），把体积压到最小，插件启动时一次性载入内存

用法：
    python tools/build_dataset.py                        # 自动在常见位置找 xlsx
    python tools/build_dataset.py /path/item_usage.xlsx  # 指定输入
    python tools/build_dataset.py in.xlsx data/items.json  # 指定输入+输出
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# 表头别名：兼容列名微调
COL_ALIAS = {
    "物品ID": "id", "物品id": "id", "ID": "id", "id": "id",
    "物品名": "name", "物品名称": "name", "名称": "name", "中文名": "name",
    "用途类型": "utype", "用途": "utype",
    "用途详情": "udetail", "详情": "udetail",
    "物品卖给商人的价格": "trader", "商人价格": "trader", "商人收购价": "trader",
    "当前跳蚤价格": "flea", "跳蚤价格": "flea", "跳蚤价": "flea",
}

CANDIDATE_INPUTS = [
    "item_usage.xlsx",
    os.path.join("..", "item_usage.xlsx"),
    os.path.join("..", "..", "item_usage.xlsx"),
]


def _shared_strings(z: zipfile.ZipFile) -> list:
    """读取 xlsx 的共享字符串池。"""
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall(f"{NS}si"):
        # 富文本会把一句话切成多个 <t>，需要拼接
        out.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    return out


def _cell_value(c, shared: list) -> str:
    """取单元格文本：处理共享字符串 / 内联字符串 / 数字三种情况。"""
    t = c.get("t")
    is_node = c.find(f"{NS}is")
    if is_node is not None:  # 内联字符串
        return "".join(x.text or "" for x in is_node.iter(f"{NS}t"))
    v = c.find(f"{NS}v")
    if v is None:
        return ""
    raw = v.text or ""
    if t == "s":  # 共享字符串下标
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return raw
    return raw


def read_sheet(path: str) -> OrderedDict:
    """返回 {规范列名: 该列的值列表}，按表头的实际列序对齐。"""
    z = zipfile.ZipFile(path)
    shared = _shared_strings(z)

    # 取第一个工作表
    sheet_names = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]
    if not sheet_names:
        raise ValueError("xlsx 中找不到工作表")
    sheet_names.sort()
    root = ET.fromstring(z.read(sheet_names[0]))

    rows = []
    for r in root.iter(f"{NS}row"):
        rows.append([_cell_value(c, shared) for c in r.findall(f"{NS}c")])
    if not rows:
        raise ValueError("工作表为空")

    header = [h.strip() for h in rows[0]]
    col_map = {}
    for idx, h in enumerate(header):
        key = COL_ALIAS.get(h)
        if key:
            col_map[key] = idx
    missing = [k for k in ("id", "name", "utype", "udetail") if k not in col_map]
    if missing:
        raise ValueError(f"表头缺少必需列 {missing}，实际表头：{header}")

    out = OrderedDict((k, []) for k in col_map)
    for r in rows[1:]:
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        for key, idx in col_map.items():
            out[key].append(r[idx] if idx < len(r) else "")
    return out


def to_price(v) -> int | None:
    """价格字段容错：去 ₽ / 逗号 / 空格，转成整数卢布。"""
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("₽", "").replace(" ", "")
    if not s or s in ("-", "—", "None", "nan", "0"):
        return None
    try:
        f = float(s)
        return int(f) if f == f else None  # 过滤 NaN
    except ValueError:
        return None


def build(rows: OrderedDict) -> dict:
    items = {}
    order = []
    n_row = len(rows["id"])
    for i in range(n_row):
        iid = (rows["id"][i] or "").strip()
        name = (rows["name"][i] or "").strip()
        if not iid and not name:
            continue
        key = iid or name
        d = items.get(key)
        if d is None:
            d = {"id": key, "n": name, "t": None, "f": None, "u": defaultdict(list)}
            items[key] = d
            order.append(key)
        if not d["n"] and name:
            d["n"] = name
        # 价格取第一条有效值
        if d["t"] is None:
            d["t"] = to_price(rows.get("trader", [""] * n_row)[i])
        if d["f"] is None:
            d["f"] = to_price(rows.get("flea", [""] * n_row)[i])
        utype = (rows["utype"][i] or "").strip()
        udetail = (rows["udetail"][i] or "").strip()
        if utype and udetail and udetail not in d["u"][utype]:
            d["u"][utype].append(udetail)

    out_items = []
    for key in order:
        d = items[key]
        out_items.append({
            "id": d["id"],
            "n": d["n"],
            "t": d["t"],
            "f": d["f"],
            "u": {k: v for k, v in d["u"].items() if v},
        })

    usage_total = sum(len(v) for i in out_items for v in i["u"].values())
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "item_usage.xlsx",
        "counts": {
            "items": len(out_items),
            "usage": usage_total,
        },
        "items": out_items,
    }


def find_input(arg: str | None) -> str:
    if arg:
        if not os.path.exists(arg):
            sys.exit(f"找不到输入文件：{arg}")
        return arg
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in CANDIDATE_INPUTS:
        for base in (os.getcwd(), here, os.path.dirname(here)):
            p = os.path.join(base, rel)
            if os.path.exists(p):
                return p
    sys.exit("未找到 item_usage.xlsx，请用参数指定路径")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    src = find_input(args[0] if args else None)
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dst = args[1] if len(args) > 1 else os.path.join(plugin_root, "data", "items.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    print(f"读取 {src} ...")
    rows = read_sheet(src)
    print(f"  数据行 {len(rows['id'])}")
    data = build(rows)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(dst) / 1024
    print(f"写出 {dst}")
    print(f"  物品 {data['counts']['items']} / 用途 {data['counts']['usage']} / {size:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
