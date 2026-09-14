# -*- coding: utf-8 -*-
"""
爆仓计算器 —— 一天一收产出最大化
================================
固化「效率-爆仓-产出」计算过程的工具。口径真源：
- docs\1-基础设定\资源体系\库存与爆仓.md（爆仓公式与回归算例）
- docs\1-基础设定\资源体系\产出常数表.md（产出锚点）
- docs\1-基础设定\设施与进驻\罗德岛基建建设.md（电力模型）

用法：
    python 爆仓计算器.py             # 启动 GUI
    python 爆仓计算器.py --selftest  # 运行回归自测（对齐库存与爆仓.md 全部算例）
    python 爆仓计算器.py --list      # 列出内置组合预设
"""

import json
import math
import os
import sys

# =====================================================================
# 一、静态数据（全部来自库内真源）
# =====================================================================

HARVEST_H = 24.0          # 一天一收的标准间隔
MINUTES_PER_DAY = 1440.0

# 制造配方：体积 / 基础耗时(min) / 单件产出
# 出处：制造站机制.md·配方一览
RECIPES = {
    "基础作战记录": {"volume": 2, "minutes": 45, "yield": {"经验": 200}},
    "初级作战记录": {"volume": 3, "minutes": 80, "yield": {"经验": 400}},
    "中级作战记录": {"volume": 5, "minutes": 180, "yield": {"经验": 1000}},
    "赤金":         {"volume": 2, "minutes": 72, "yield": {"龙门币价值": 500}},
    "源石碎片":     {"volume": 3, "minutes": 60, "yield": {}},  # 搓玉原料，不自结算
}

# 制造站等级：仓库容量 / 耗电 / 进驻位
MANU_LEVELS = {1: {"cap": 24, "power": 10, "slots": 1},
               2: {"cap": 36, "power": 30, "slots": 2},
               3: {"cap": 54, "power": 60, "slots": 3}}

# 贸易站等级：订单上限 / 耗电 / 进驻位
TRADE_LEVELS = {1: {"cap": 6, "power": 10, "slots": 1},
                2: {"cap": 8, "power": 30, "slots": 2},
                3: {"cap": 10, "power": 60, "slots": 3}}

# 订单档位：赤金交付数 -> 基础获取耗时(min)、报酬
# 出处：贸易站机制.md·谈判策略（每赤金固定 500）
ORDER_TIERS = {2: {"minutes": 144, "pay": 1000},
               3: {"minutes": 210, "pay": 1500},
               4: {"minutes": 276, "pay": 2000}}

# 贵金属订单生成概率分布（Lv.3 档位；Lv.1/Lv.2 由站级分布键给出）
# 出处：贸易站机制.md·贵金属订单的生成概率、裁缝类两节
DISTRIBUTIONS = {
    "lv1_常规":   {2: 1.00, 3: 0.00, 4: 0.00},
    "lv2_常规":   {2: 0.60, 3: 0.40, 4: 0.00},
    "lv3_常规":   {2: 0.30, 3: 0.50, 4: 0.20},
    "裁缝α峰值":  {2: 0.15, 3: 0.30, 4: 0.55},
    "裁缝β峰值":  {2: 0.05, 3: 0.10, 4: 0.85},
    "αα叠加":     {2: 0.13, 3: 0.22, 4: 0.65},   # 双α观测口径（期望 3.46 赤）
}

# 特殊订单改写器：输入原分布 -> 输出 (期望耗时min, 期望赤金/单, 期望龙门币/单)
# 出处：贸易站机制.md·特殊订单；但书.md；可露希尔特别订单.md
def order_stats(dist=None, special=None, level=3):
    """返回该站单笔订单的期望属性。special 覆盖 dist。"""
    if special == "可露希尔特别订单":
        return {"minutes": 144, "gold": 2, "pay": 1200}
    if special == "开采协力(合成玉)":
        return {"minutes": 120, "gold": 0, "pay": 0, "orundum": 20, "frag": 2}
    if special == "佩佩特别独占":
        return {"minutes": 270, "gold": 0, "pay": 1000}
    if special and special.startswith("但书违约"):
        beta = special.endswith("β")
        d = dist or DISTRIBUTIONS["lv3_常规"]
        minutes = exp_minutes(d)
        pay = 0.0
        gold = 0.0
        for t, p in d.items():
            if p <= 0:
                continue
            if t < 4:  # 违约：赤金 +1(α)/+2(β)、报酬 +500/+1000
                pay += p * (ORDER_TIERS[t]["pay"] + (1000 if beta else 500))
                gold += p * (t + (2 if beta else 1))
            else:      # 4 赤订单不违约
                pay += p * ORDER_TIERS[t]["pay"]
                gold += p * t
        return {"minutes": minutes, "gold": gold, "pay": pay}
    # 普通 + 可选龙舌兰投资（4 赤订单报酬 +500，β 档）
    d = dist or DISTRIBUTIONS["lv3_常规"]
    pay = sum(p * ORDER_TIERS[t]["pay"] for t, p in d.items() if p > 0)
    gold = sum(p * t for t, p in d.items() if p > 0)
    r = {"minutes": exp_minutes(d), "gold": gold, "pay": pay}
    if special and special.startswith("龙舌兰投资"):
        bonus = 500 if special.endswith("β") else 250
        p4 = d.get(4, 0)
        r["pay"] += p4 * bonus
        r["等效赤金价值"] = p4 * bonus       # 凭空增益，折算隐含赤金产能（产出常数表口径）
    return r


def exp_minutes(dist):
    return sum(p * ORDER_TIERS[t]["minutes"] for t, p in dist.items() if p > 0)


# 产出锚点（每 1.0 总效率 · 24h；未饱和时 产出/日 = 锚点 × 总效率）
# 出处：产出常数表.md
ANCHORS = {
    ("贸易", 1, "常规"): 10000,
    ("贸易", 2, "常规"): 10141,
    ("贸易", 3, "常规"): 10265,
    ("贸易", 3, "开采协力(合成玉)"): 240,       # 合成玉
    ("可露希尔", 3, None): 12000,
    ("但书β", 1, None): 20000,
    ("但书β", 2, None): 18591.55,
    ("但书β", 3, None): 15929.2,
    ("制造", "赤金", None): 20,                  # 枚/日
    ("制造", "源石碎片", None): 24,               # 枚/日
    ("制造", "中级作战记录", None): 8000,          # 经验/日
}

# 电力模型：供电与耗电（罗德岛基建建设.md·等级表 / 用电平衡）
POWER_SUPPLY = {1: 60, 2: 130, 3: 270}                     # 发电站供电
POWER_DRAW = {
    "制造站": {1: 10, 2: 30, 3: 60},
    "贸易站": {1: 10, 2: 30, 3: 60},
    "宿舍":   {1: 10, 2: 20, 3: 30, 4: 45, 5: 65},
    "会客室": {1: 10, 2: 30, 3: 60},
    "办公室": {1: 10, 2: 30, 3: 60},
    "加工站": {1: 10, 2: 10, 3: 10},
    "训练室": {1: 10, 2: 30, 3: 60},
    "活动室": {1: 0, 2: 0, 3: 0},
    "发电站": {1: 0, 2: 0, 3: 0},                          # 发电站供电不耗电
    "控制中枢": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
}
DORM_SLOTS = 5   # 宿舍每间进驻位恒 5，与等级无关（心情与宿舍.md）


# =====================================================================
# 二、核心引擎
# =====================================================================

def total_efficiency(base=1.0, workers=3, worker_pct=0.01, skill_pct=0.0, aura_pct=0.0):
    """纸面总效率 = 基础100% + 每名非涣散进驻干员 +1% + 技能 + 中枢光环。"""
    return base + workers * worker_pct + skill_pct + aura_pct


def manufacture_burst(level, cap_bonus, recipe, efficiency, harvest_h=HARVEST_H):
    """制造站：容纳 = ⌊库存/体积⌋；爆仓 = 单件耗时/效率×容纳。
    返回 dict（饱和站日产出 = 一仓；未饱和 = 基准产出×效率）。"""
    cap_total = MANU_LEVELS[level]["cap"] + cap_bonus
    vol = RECIPES[recipe]["volume"]
    minutes = RECIPES[recipe]["minutes"]
    count = math.floor(cap_total / vol + 1e-9)
    leftover = cap_total - count * vol
    burst_h = minutes / efficiency * count / 60.0
    saturated = burst_h <= harvest_h
    if saturated:
        per_day = float(count)                      # 件/日（一仓）
    else:
        per_day = MINUTES_PER_DAY * efficiency / minutes   # 件/日（速率）
    return {"库存": cap_total, "体积": vol, "容纳数量": count, "剩余浪费": leftover,
            "爆仓时间h": burst_h, "饱和": saturated,
            "日产量单位": "份/枚" if recipe != "中级作战记录" else "份",
            "日产件数": per_day,
            "日产经验": per_day * RECIPES[recipe]["yield"].get("经验", 0),
            "日产值": per_day * RECIPES[recipe]["yield"].get("龙门币价值", 0)}


def trade_burst(level, cap_bonus, dist_key=None, special=None, efficiency=1.93,
               harvest_h=HARVEST_H, aura_applied=True):
    """贸易站：上限 = 站级 + 加成；爆仓 = 期望单件耗时/效率×上限。
    日产出双口径：饱和（一仓收益）/ 未饱和（锚点×效率 或 期望收益×日单数）。"""
    cap = TRADE_LEVELS[level]["cap"] + cap_bonus
    stats = order_stats(DISTRIBUTIONS.get(dist_key), special, level)
    burst_h = stats["minutes"] / efficiency * cap / 60.0
    saturated = burst_h <= harvest_h
    if saturated:
        orders_per_day = float(cap)
    else:
        orders_per_day = MINUTES_PER_DAY * efficiency / stats["minutes"]
    lmb = orders_per_day * stats["pay"]
    gold_need = orders_per_day * stats["gold"]
    return {"订单上限": cap, "期望单件耗时min": round(stats["minutes"], 2),
            "期望赤金/单": round(stats["gold"], 3), "期望报酬/单": round(stats["pay"], 1),
            "爆仓时间h": burst_h, "饱和": saturated,
            "日完成单数": round(orders_per_day, 3),
            "日龙门币": round(lmb, 0), "日赤金消耗": round(gold_need, 1),
            "日等效赤金价值": round(orders_per_day * stats.get("等效赤金价值", 0), 0)}


def jie_dynamic_burst(fixed_skill_pct, cap_bonus, order_minutes=144, workers=3,
                      aura_pct=0.0, harvest_h=HARVEST_H, pay_per_order=1200, gold_per_order=2):
    """孑市井之道动态站：效率 = 基础100% + 进驻 + 固定技能 + 光环 + 4%×在站订单数。
    订单获取逐单积分（每单获取时间随在站订单数上升而缩短）。"""
    base = 1.0 + 0.01 * workers + fixed_skill_pct + aura_pct
    cap = TRADE_LEVELS[3]["cap"] + cap_bonus
    per_order = [order_minutes / (base + 0.04 * n) for n in range(cap)]
    burst_min = sum(per_order)                       # 填满上限的累计时间
    orders_in_harvest = 0
    acc = 0.0
    for dt in per_order:
        if acc + dt > harvest_h * 60:
            break
        acc += dt
        orders_in_harvest += 1
    saturated = burst_min <= harvest_h * 60
    orders_per_day = float(cap) if saturated else orders_in_harvest
    return {"订单上限": cap, "基础效率(0单)": round(base, 3),
            "满单效率": round(base + 0.04 * (cap - 1), 3),
            "爆仓时间h": round(burst_min / 60.0, 2), "饱和": saturated,
            "日完成单数": orders_per_day,
            "日龙门币": round(orders_per_day * pay_per_order, 0),
            "日赤金消耗": round(orders_per_day * gold_per_order, 1),
            "日等效赤金价值": round(orders_per_day * (pay_per_order - 1000) / 1.0
                                   * (1 if pay_per_order > 1000 else 0), 0)}


def drone_station(charge_bonus_pct=0.20, stations=3, cap=235):
    """发电站：全基建汇总效率；充满 235 架的倒计时。"""
    e = 1.0 + 0.05 * stations + charge_bonus_pct * stations
    per_drone = 6.0 / e
    return {"总效率E": round(e, 3), "每架min": round(per_drone, 3),
            "充满235架h": round(per_drone * cap / 60.0, 2),
            "等效效率当量/日": round(cap / 480.0, 3)}     # 480 架/日 = 1.0 效率


def office_burst(skill_pct=0.45, central_pct=0.10):
    """办公室：12h/次，上限 3 次。"""
    e = 1.0 + 0.05 + skill_pct + central_pct
    return {"总效率E": round(e, 3), "每次h": round(12 / e, 2),
            "填满3次h": round(36 / e, 2)}


def parlor_burst(rarity_pct=0.05, elite_pct=0.16, skill_pct=0.25, workers=2,
                 level=3, ambience_pct=0.15):
    """会客室：20h/份，自有库 10 份；等级基础 107/109/111%。"""
    base = {1: 1.07, 2: 1.09, 3: 1.11}[level]
    e = base + ambience_pct + workers * (rarity_pct + elite_pct + 0.05 + skill_pct)
    return {"总效率E": round(e, 3), "每份h": round(20 / e, 2)}


def power_balance(gen_levels, manu_levels, trade_levels, dorm=(4, 1),
                  meeting=3, office=3, process=1, training=3, activities=0):
    """电力平衡：返回供电/耗电明细与判定。dorm=(间数, 等级)。"""
    supply = sum(POWER_SUPPLY[g] for g in gen_levels)
    draw = {}
    draw["贸易站"] = sum(POWER_DRAW["贸易站"][l] for l in trade_levels)
    draw["制造站"] = sum(POWER_DRAW["制造站"][l] for l in manu_levels)
    draw["宿舍"] = POWER_DRAW["宿舍"][dorm[1]] * dorm[0]
    draw["会客室"] = POWER_DRAW["会客室"][meeting]
    draw["办公室"] = POWER_DRAW["办公室"][office]
    draw["加工站"] = POWER_DRAW["加工站"][process]
    draw["训练室"] = POWER_DRAW["训练室"][training]
    total_draw = sum(draw.values())
    return {"供电": supply, "耗电明细": draw, "总耗电": total_draw,
            "富余": supply - total_draw, "可行": total_draw <= supply,
            "宿舍轮休位": dorm[0] * DORM_SLOTS}


# =====================================================================
# 三·五、效率-库存约束线（原方案 x=0.35+n/40 的通用化）
# =====================================================================

def constraint_line(level, recipe, target_h=24.0, workers=3, aura=0.0, n_max=50):
    """给定目标爆仓时长，返回 (库存加成区间, 容纳, 所需总效率, 所需技能合计) 列表。
    技能 = E − 100% − 进驻×1% − 光环。落在或高于线的组合产出相同（一仓/target_h）——
    高于线只是爆仓提前，产出不变，属效率浪费。"""
    import math as _m
    base_cap = MANU_LEVELS[level]["cap"]
    vol, minutes = RECIPES[recipe]["volume"], RECIPES[recipe]["minutes"]
    rows, cur_count, n_from = [], None, 0
    for n in range(0, n_max + 1):
        count = _m.floor((base_cap + n) / vol + 1e-9)
        if count != cur_count:
            if cur_count is not None:
                e = minutes * cur_count / (target_h * 60.0)
                rows.append((f"+{n_from}~+{n-1}" if n - 1 > n_from else f"+{n_from}",
                             cur_count, round(e, 3), round(e - 1 - workers * 0.01 - aura, 3)))
            cur_count, n_from = count, n
    e = minutes * cur_count / (target_h * 60.0)
    rows.append((f"+{n_from}~+{n_max}" if n_max > n_from else f"+{n_from}",
                 cur_count, round(e, 3), round(e - 1 - workers * 0.01 - aura, 3)))
    return rows


# =====================================================================
# 四、回归自测（对齐 库存与爆仓.md 全部算例与 产出常数表 锚点）
# =====================================================================

def _close(a, b, tol=0.06):
    return abs(a - b) <= tol


def selftest():
    ok, fail = 0, []

    def check(name, got, want, tol=0.06):
        nonlocal ok
        if _close(got, want, tol):
            ok += 1
        else:
            fail.append(f"{name}: got={got:.3f} want={want}")

    # --- 制造算例（库存与爆仓.md）---
    r = manufacture_burst(3, 0, "赤金", 1.96);       check("制造三级1.96赤金爆仓", r["爆仓时间h"], 16.5)
    r = manufacture_burst(3, 0, "中级作战记录", 1.96); check("制造三级1.96中级爆仓", r["爆仓时间h"], 15.3)
    r = manufacture_burst(3, 0, "源石碎片", 1.96);     check("制造三级1.96碎片爆仓", r["爆仓时间h"], 9.2)
    r = manufacture_burst(3, 0, "赤金", 2.26);        check("制造三级2.26赤金爆仓", r["爆仓时间h"], 14.3)
    r = manufacture_burst(3, 0, "中级作战记录", 2.26); check("制造三级2.26中级爆仓", r["爆仓时间h"], 13.3)
    r = manufacture_burst(3, 0, "源石碎片", 2.26);     check("制造三级2.26碎片爆仓", r["爆仓时间h"], 8.0)
    r = manufacture_burst(2, 0, "赤金", 1.75);        check("制造二级1.75赤金爆仓", r["爆仓时间h"], 12.3)
    r = manufacture_burst(2, 0, "中级作战记录", 1.75); check("制造二级1.75中级爆仓", r["爆仓时间h"], 12.0)
    assert r["容纳数量"] == 7 and r["剩余浪费"] == 1, "二级站中级经验 7 份余 1"

    # --- 贸易算例（库存与爆仓.md）---
    t = trade_burst(2, 0, "lv2_常规", special="但书违约β", efficiency=1.49)
    check("贸易二级但书1.49爆仓", t["爆仓时间h"], 15.2)
    t = trade_burst(3, 0, "lv3_常规", efficiency=2.00)
    check("贸易三级常规2.00爆仓", t["爆仓时间h"], 17.0)
    t = trade_burst(3, 0, "裁缝β峰值", efficiency=2.00)
    check("贸易三级裁缝β2.00爆仓", t["爆仓时间h"], 21.9)
    t = trade_burst(3, 0, special="可露希尔特别订单", efficiency=2.00)
    check("可露希尔2.00爆仓", t["爆仓时间h"], 12.0)
    t = trade_burst(3, 0, special="开采协力(合成玉)", efficiency=2.00)
    check("开采协力2.00爆仓", t["爆仓时间h"], 10.0)

    # --- 发电 / 办公室 / 会客室（库存与爆仓.md）---
    d = drone_station(0.20, 3);   check("发电E=1.75充满h", d["充满235架h"], 13.4)
    o = office_burst(0.45, 0.10); check("办公室E=1.60填满h", o["填满3次h"], 22.5)
    p = parlor_burst(0.05, 0.16, 0.25, 2, 3, 0.15); check("会客室E=2.28每份h", p["每份h"], 8.8)

    # --- 产出锚点（产出常数表.md，1.0 效率·24h；锚点为未饱和速率口径，用 harvest_h=0 禁用饱和截断）---
    INF = 0
    t = trade_burst(1, 0, "lv1_常规", efficiency=1.0, harvest_h=INF); check("锚点·贸易Lv1", t["日龙门币"], 10000, 5)
    t = trade_burst(2, 0, "lv2_常规", efficiency=1.0, harvest_h=INF); check("锚点·贸易Lv2", t["日龙门币"], 10141, 5)
    t = trade_burst(3, 0, "lv3_常规", efficiency=1.0, harvest_h=INF); check("锚点·贸易Lv3", t["日龙门币"], 10265, 5)
    t = trade_burst(1, 0, "lv1_常规", special="但书违约β", efficiency=1.0, harvest_h=INF); check("锚点·但书Lv1", t["日龙门币"], 20000, 5)
    t = trade_burst(2, 0, "lv2_常规", special="但书违约β", efficiency=1.0, harvest_h=INF); check("锚点·但书Lv2", t["日龙门币"], 18591.55, 5)
    t = trade_burst(3, 0, "lv3_常规", special="但书违约β", efficiency=1.0, harvest_h=INF); check("锚点·但书Lv3", t["日龙门币"], 15929.2, 8)
    t = trade_burst(3, 0, special="可露希尔特别订单", efficiency=1.0, harvest_h=INF); check("锚点·可露希尔", t["日龙门币"], 12000, 5)
    t = trade_burst(3, 0, "lv3_常规", special="龙舌兰投资β", efficiency=1.0)
    # 龙舌兰组锚点：第三人裁缝β → 需用裁缝β分布 + 龙舌兰投资
    t = trade_burst(3, 0, "裁缝β峰值", special="龙舌兰投资β", efficiency=1.0, harvest_h=INF)
    check("锚点·龙舌兰组裁缝β档", t["日龙门币"], 12739.73, 10)
    check("锚点·龙舌兰组裁缝β赤金等效", t["日等效赤金价值"], 2328.77, 10)
    t = trade_burst(3, 0, "lv3_常规", special="龙舌兰投资β", efficiency=1.0)
    # 白板档=仅巫恋α（15/30/55）
    t = trade_burst(3, 0, "裁缝α峰值", special="龙舌兰投资β", efficiency=1.0, harvest_h=INF)
    check("锚点·龙舌兰组白板档(巫恋α)", t["日龙门币"], 12030.46, 12)
    m = manufacture_burst(3, 0, "赤金", 1.0); check("锚点·赤金日产", m["日产件数"], 20, 0.01)
    m = manufacture_burst(3, 0, "中级作战记录", 1.0); check("锚点·中级经验日产", m["日产经验"], 8000, 1)

    # --- 电力（罗德岛基建建设.md：满配 870、缺口 330）---
    p = power_balance([3, 3], [3, 3, 3, 2], [3, 2, 1])
    assert p["可行"] and p["富余"] == 0, f"342-321-3332 应恰好平衡: {p}"
    assert p["宿舍轮休位"] == 20
    p = power_balance([3, 3, 3], [3, 3, 3], [3, 3, 3], dorm=(4, 5))
    assert p["可行"] and p["富余"] == 0, f"333 满配应恰好平衡: {p}"
    p = power_balance([3, 3], [3, 3, 2, 1], [3, 3, 2])
    assert p["可行"] and p["富余"] == 0, f"342-332-3321 应恰好平衡: {p}"

    # --- 约束线（三级赤金 n=0 → E=1.35；三级经验 n=0 → 1.25；原方案 x=0.35+n/40 口径） ---
    ln = {(r[0], r[1]): r for r in constraint_line(3, "赤金", 24)}
    check("约束线·三级赤金27枚所需E", [r[2] for r in constraint_line(3, "赤金", 24) if r[1] == 27][0], 1.35, 0.005)
    check("约束线·三级经验10份所需E", [r[2] for r in constraint_line(3, "中级作战记录", 24) if r[1] == 10][0], 1.25, 0.005)
    check("约束线·三级赤金35枚所需E", [r[2] for r in constraint_line(3, "赤金", 24) if r[1] == 35][0], 1.75, 0.005)
    check("约束线·二级赤金18枚所需E", [r[2] for r in constraint_line(2, "赤金", 24, workers=2) if r[1] == 18][0], 0.90, 0.005)

    print(f"[自测] 通过 {ok} 项；失败 {len(fail)} 项")
    for f in fail:
        print("  ✗", f)
    return len(fail) == 0


# =====================================================================
# 四、组合预设加载
# =====================================================================

PRESET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "组合预设.json")


def load_presets():
    if not os.path.exists(PRESET_PATH):
        return {}
    with open(PRESET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def eval_preset(p, aura_trade=0.07, aura_manu=0.03, harvest_h=HARVEST_H):
    """按预设条目直接计算并返回结果 dict。光环默认 贸易+7%/制造+3%，可覆盖。"""
    kind = p.get("设施")
    if kind == "制造站":
        eff = p.get("总效率") or total_efficiency(
            1.0, p.get("进驻", 3), 0.01, p.get("技能效率合计", 0.0), aura_manu)
        return manufacture_burst(p.get("站级", 3), p.get("库存加成", 0),
                                 p.get("配方", "赤金"), eff, harvest_h)
    if kind == "贸易站":
        if p.get("模式") == "孑动态":
            return jie_dynamic_burst(p.get("固定技能", 0.15), p.get("上限加成", 0),
                                     p.get("单件耗时min", 144), p.get("进驻", 3),
                                     p.get("光环", 0.0), harvest_h,
                                     p.get("单件报酬", 1200), p.get("单件赤金", 2))
        if p.get("模式") == "佩佩固定":
            orders = harvest_h * 60 / 270
            cap = TRADE_LEVELS[p.get("站级", 1)]["cap"] + p.get("上限加成", 0)
            sat = orders >= cap
            od = float(cap) if sat else orders
            return {"订单上限": cap, "爆仓时间h": round(270 * cap / 60.0, 2), "饱和": sat,
                    "日完成单数": round(od, 2), "日龙门币": round(od * 1000, 0),
                    "日赤金消耗": 0.0, "日等效赤金价值": 0.0,
                    "备注": "特别独占订单不受效率影响，4:30/单"}
        eff = p.get("总效率") or total_efficiency(
            1.0, p.get("进驻", 3), 0.01, p.get("技能效率合计", 0.0),
            p.get("光环", aura_trade))
        return trade_burst(p.get("站级", 3), p.get("上限加成", 0),
                           p.get("分布"), p.get("特殊"), eff, harvest_h)
    if kind == "发电站":
        return drone_station(p.get("充能技能", 0.20), p.get("站数", 3))
    if kind == "办公室":
        return office_burst(p.get("技能效率", 0.45), p.get("中枢联络", 0.10))
    if kind == "会客室":
        return parlor_burst(p.get("稀有度", 0.05), p.get("精英化", 0.16),
                            p.get("技能效率", 0.25), p.get("人数", 2),
                            p.get("站级", 3), p.get("氛围", 0.15))
    raise ValueError(f"未知设施: {kind}")


# =====================================================================
# 五、GUI（tkinter）
# =====================================================================

def _fmt_row(name, p, r):
    """把预设计算结果压成速查表一行。"""
    kind = p.get("设施", "?")
    burst = r.get("爆仓时间h")
    sat = r.get("饱和")
    if kind == "制造站":
        if r.get("日产经验"):
            out = f"{r['日产经验']:.0f} 经验/日"
        elif "日产值" in r and r["日产值"]:
            out = f"{r['日产件数']:.1f} 枚赤金/日"
        else:
            out = f"{r['日产件数']:.1f} 件/日"
        gold = f"+{r['日产件数']:.1f}" if p.get("配方") == "赤金" else "—"
    elif kind == "贸易站":
        out = f"{r.get('日龙门币', 0):.0f} 龙门币/日"
        gold = f"-{r.get('日赤金消耗', 0):.1f}"
    else:
        out = burst_line = ""
        for k, fmt in (("充满235架h", "充满 {:.1f}h"), ("填满3次h", "填满 {:.1f}h"), ("每份h", "{:.1f}h/份")):
            if k in r:
                out = fmt.format(r[k])
                break
        gold = "—"
    eq = r.get("日等效赤金价值", 0)
    burst_s = f"{burst:.1f}" if isinstance(burst, float) else "—"
    sat_s = {True: "饱和(一仓/日)", False: "未饱和"}.get(sat, "—") if sat is not None else "—"
    return (name, kind, burst_s, sat_s, out, gold,
            f"+{eq:.0f}" if eq else "—")


def run_gui():
    import tkinter as tk
    from tkinter import ttk

    presets = load_presets()
    names = [n for n in presets if not n.startswith("_")]

    root = tk.Tk()
    root.title("爆仓计算器 · 一天一收产出最大化")
    root.geometry("1020x660")

    # ---- 全局参数 ----
    top = ttk.Frame(root, padding=6)
    top.pack(fill="x")
    tk.Label(top, text="贸易光环 +%", width=10).pack(side="left")
    aura_trade = tk.DoubleVar(value=7)
    ttk.Spinbox(top, from_=0, to=20, increment=1, width=5, textvariable=aura_trade).pack(side="left")
    tk.Label(top, text="制造光环 +%", width=10).pack(side="left")
    aura_manu = tk.DoubleVar(value=3)
    ttk.Spinbox(top, from_=0, to=20, increment=1, width=5, textvariable=aura_manu).pack(side="left")
    tk.Label(top, text="收菜间隔 h", width=10).pack(side="left")
    harvest = tk.DoubleVar(value=24)
    ttk.Spinbox(top, from_=4, to=48, increment=0.5, width=5, textvariable=harvest).pack(side="left")

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=6, pady=4)

    # =============== Tab1 预设速查 ===============
    tab1 = ttk.Frame(nb)
    nb.add(tab1, text=" 预设速查（勾选即算） ")
    left = ttk.Frame(tab1)
    left.pack(side="left", fill="y", padx=4, pady=4)
    tk.Label(left, text="内置组合（可多选）").pack()
    lb = tk.Listbox(left, selectmode="multiple", width=36, height=30, exportselection=False)
    for n in names:
        lb.insert("end", n)
    lb.pack(fill="y", expand=True)

    cols = ("预设", "设施", "爆仓h", "饱和判定", "日产出", "赤金生产/消耗", "等效赤金价值")
    tv = ttk.Treeview(tab1, columns=cols, show="headings", height=28)
    for c, w in zip(cols, (230, 70, 60, 110, 150, 110, 100)):
        tv.heading(c, text=c)
        tv.column(c, width=w, anchor="center")
    tv.pack(side="left", fill="both", expand=True, padx=4, pady=4)

    summary_var = tk.StringVar(value="选中组合后显示合计")
    ttk.Label(tab1, textvariable=summary_var, padding=6,
              relief="groove").pack(side="bottom", fill="x")

    def refresh(*_):
        tv.delete(*tv.get_children())
        sel = [lb.get(i) for i in lb.curselection()]
        gold_prod = gold_use = eq = 0.0
        exp = lmb = 0.0
        for n in sel:
            p = presets[n]
            r = eval_preset(p, aura_trade.get() / 100.0, aura_manu.get() / 100.0, harvest.get())
            tv.insert("", "end", values=_fmt_row(n, p, r))
            if p.get("设施") == "制造站" and p.get("配方") == "赤金":
                gold_prod += r["日产件数"]
            if p.get("设施") == "贸易站":
                gold_use += r.get("日赤金消耗", 0)
                lmb += r.get("日龙门币", 0)
                eq += r.get("日等效赤金价值", 0)
            if p.get("设施") == "制造站" and r.get("日产经验"):
                exp += r["日产经验"]
        if sel:
            drone_eq = 235 / 480 * 20   # 无人机全投赤金的枚数
            summary_var.set(
                f"合计：龙门币 {lmb:.0f}/日 | 经验 {exp:.0f}/日 | 赤金 生产 {gold_prod:.1f} / 消耗 {gold_use:.1f} / "
                f"缺口 {gold_prod - gold_use:+.1f} 枚 | 等效赤金价值 {eq:.0f} | 无人机235架→赤金 +{drone_eq:.0f} 枚 或 经验 +{235/480*8000:.0f}")

    lb.bind("<<ListboxSelect>>", refresh)

    # =============== Tab2 制造站 ===============
    tab2 = ttk.Frame(nb, padding=8)
    nb.add(tab2, text=" 制造站 ")
    f2 = ttk.Frame(tab2)
    f2.pack(fill="x")
    m_level = tk.IntVar(value=3); m_cap = tk.IntVar(value=0)
    m_workers = tk.IntVar(value=3); m_skill = tk.DoubleVar(value=0.90); m_aura = tk.DoubleVar(value=3)
    for row_i, (label, var, lo, hi, inc) in enumerate([
            ("站级", m_level, 1, 3, 1), ("库存加成(格)", m_cap, -12, 60, 1),
            ("进驻人数", m_workers, 0, 3, 1), ("技能效率合计 %", m_skill, -50, 300, 5),
            ("中枢光环 %", m_aura, 0, 10, 1)]):
        tk.Label(f2, text=label, width=12).grid(row=row_i // 5, column=(row_i % 5) * 2, sticky="e")
        ttk.Spinbox(f2, from_=lo, to=hi, increment=inc, width=6, textvariable=var).grid(
            row=row_i // 5, column=(row_i % 5) * 2 + 1, padx=4)
    m_recipe = tk.StringVar(value="赤金")
    tk.Label(f2, text="配方", width=12).grid(row=1, column=0, sticky="e")
    ttk.Combobox(f2, textvariable=m_recipe, values=list(RECIPES), width=10, state="readonly").grid(row=1, column=1)
    m_out = tk.Text(tab2, height=12, width=90)
    m_out.pack(pady=8)

    def calc_manu(*_):
        eff = total_efficiency(1.0, m_workers.get(), 0.01, m_skill.get() / 100, m_aura.get() / 100)
        r = manufacture_burst(m_level.get(), m_cap.get(), m_recipe.get(), eff, harvest.get())
        m_out.delete("1.0", "end")
        m_out.insert("end", f"总效率 = {eff:.3f}\n")
        for k, v in r.items():
            m_out.insert("end", f"{k}: {v}\n")
    ttk.Button(tab2, text="计算", command=calc_manu).pack()
    for v in (m_level, m_cap, m_workers, m_skill, m_aura, m_recipe):
        v.trace_add("write", calc_manu)
    calc_manu()

    # =============== Tab3 贸易站 ===============
    tab3 = ttk.Frame(nb, padding=8)
    nb.add(tab3, text=" 贸易站 ")
    f3 = ttk.Frame(tab3)
    f3.pack(fill="x")
    t_level = tk.IntVar(value=3); t_cap = tk.IntVar(value=0)
    t_workers = tk.IntVar(value=3); t_skill = tk.DoubleVar(value=0); t_aura = tk.DoubleVar(value=7)
    for row_i, (label, var, lo, hi, inc) in enumerate([
            ("站级", t_level, 1, 3, 1), ("订单上限加成", t_cap, -6, 20, 1),
            ("进驻人数", t_workers, 0, 3, 1), ("技能效率合计 %", t_skill, -30, 300, 5),
            ("中枢光环 %", t_aura, 0, 10, 1)]):
        tk.Label(f3, text=label, width=12).grid(row=0, column=row_i * 2, sticky="e")
        ttk.Spinbox(f3, from_=lo, to=hi, increment=inc, width=6, textvariable=var).grid(
            row=0, column=row_i * 2 + 1, padx=4)
    t_dist = tk.StringVar(value="lv3_常规")
    t_spec = tk.StringVar(value="无")
    tk.Label(f3, text="订单分布", width=12).grid(row=1, column=0, sticky="e")
    ttk.Combobox(f3, textvariable=t_dist, values=list(DISTRIBUTIONS), width=10, state="readonly").grid(row=1, column=1)
    tk.Label(f3, text="特殊订单", width=12).grid(row=1, column=2, sticky="e")
    ttk.Combobox(f3, textvariable=t_spec, width=22, state="readonly",
                 values=["无", "可露希尔特别订单", "开采协力(合成玉)", "佩佩特别独占",
                         "但书违约β", "但书违约α", "龙舌兰投资β", "龙舌兰投资α"]).grid(row=1, column=3)
    t_out = tk.Text(tab3, height=14, width=90)
    t_out.pack(pady=8)

    def calc_trade(*_):
        spec = None if t_spec.get() == "无" else t_spec.get()
        dist = t_dist.get() if spec in (None, "龙舌兰投资β", "龙舌兰投资α", "但书违约β", "但书违约α") else None
        if spec and spec.startswith("但书"):
            dist = {"lv1_常规": "lv1_常规", "lv2_常规": "lv2_常规"}.get(t_dist.get(), "lv3_常规")
            if t_level.get() == 1:
                dist = "lv1_常规"
            elif t_level.get() == 2:
                dist = "lv2_常规"
            else:
                dist = "lv3_常规"
        eff = total_efficiency(1.0, t_workers.get(), 0.01, t_skill.get() / 100, t_aura.get() / 100)
        r = trade_burst(t_level.get(), t_cap.get(), dist, spec, eff, harvest.get())
        t_out.delete("1.0", "end")
        t_out.insert("end", f"总效率 = {eff:.3f} | 分布 = {dist} | 特殊 = {spec}\n")
        for k, v in r.items():
            t_out.insert("end", f"{k}: {v}\n")
    ttk.Button(tab3, text="计算", command=calc_trade).pack()
    for v in (t_level, t_cap, t_workers, t_skill, t_aura, t_dist, t_spec):
        v.trace_add("write", calc_trade)
    calc_trade()

    # =============== Tab4 发电/办公室/会客室 ===============
    tab4 = ttk.Frame(nb, padding=10)
    nb.add(tab4, text=" 发电/办公室/会客室 ")
    d_skill = tk.DoubleVar(value=20); d_stations = tk.IntVar(value=3)
    o_skill = tk.DoubleVar(value=45); o_central = tk.DoubleVar(value=10)
    p_skill = tk.DoubleVar(value=25); p_level = tk.IntVar(value=3); p_amb = tk.DoubleVar(value=15)
    box = ttk.Frame(tab4)
    box.pack()
    for r_i, items in enumerate([
            [("发电站技能 +%", d_skill, 0, 40, 5), ("发电站数", d_stations, 1, 3, 1)],
            [("办公室技能 +%", o_skill, 0, 60, 5), ("中枢联络 +%", o_central, 0, 20, 1)],
            [("会客室技能 +%", p_skill, 0, 60, 5), ("会客室等级", p_level, 1, 3, 1)],
            [("宿舍氛围 +%", p_amb, 0, 15, 5), None]]):
        c = 0
        for it in items:
            if it is None:
                break
            label, var, lo, hi, inc = it
            tk.Label(box, text=label).grid(row=r_i, column=c, sticky="e", padx=3, pady=4)
            ttk.Spinbox(box, from_=lo, to=hi, increment=inc, width=6, textvariable=var).grid(row=r_i, column=c + 1)
            c += 2
    misc_out = tk.Text(tab4, height=10, width=70)
    misc_out.pack(pady=8)

    def calc_misc(*_):
        misc_out.delete("1.0", "end")
        d = drone_station(d_skill.get() / 100, d_stations.get())
        o = office_burst(o_skill.get() / 100, o_central.get() / 100)
        pl = parlor_burst(0.05, 0.16, p_skill.get() / 100, 2, p_level.get(), p_amb.get() / 100)
        misc_out.insert("end", "发电站：\n")
        for k, v in d.items():
            misc_out.insert("end", f"  {k}: {v}\n")
        misc_out.insert("end", "办公室：\n")
        for k, v in o.items():
            misc_out.insert("end", f"  {k}: {v}\n")
        misc_out.insert("end", "会客室（两名6★精2）：\n")
        for k, v in pl.items():
            misc_out.insert("end", f"  {k}: {v}\n")
    for v in (d_skill, d_stations, o_skill, o_central, p_skill, p_level, p_amb):
        v.trace_add("write", calc_misc)
    calc_misc()

    # =============== Tab5 电力平衡 ===============
    tab5 = ttk.Frame(nb, padding=10)
    nb.add(tab5, text=" 电力平衡 ")
    pf = ttk.Frame(tab5)
    pf.pack()
    g1 = tk.IntVar(value=3); g2 = tk.IntVar(value=3); g3 = tk.IntVar(value=0)
    tr1, tr2, tr3 = tk.IntVar(value=3), tk.IntVar(value=2), tk.IntVar(value=1)
    mn = [tk.IntVar(value=v) for v in (3, 3, 3, 2, 0)]
    dorm_n = tk.IntVar(value=4); dorm_lv = tk.IntVar(value=1)
    meet = tk.IntVar(value=3); off = tk.IntVar(value=3); proc = tk.IntVar(value=1); train = tk.IntVar(value=3)
    fields = [("发电1", g1, 0, 3), ("发电2", g2, 0, 3), ("发电3", g3, 0, 3),
              ("贸易1", tr1, 1, 3), ("贸易2", tr2, 0, 3), ("贸易3", tr3, 0, 3),
              ("制造1", mn[0], 1, 3), ("制造2", mn[1], 0, 3), ("制造3", mn[2], 0, 3),
              ("制造4", mn[3], 0, 3), ("制造5", mn[4], 0, 3),
              ("宿舍间数", dorm_n, 1, 4), ("宿舍等级", dorm_lv, 1, 5),
              ("会客室", meet, 1, 3), ("办公室", off, 1, 3), ("加工站", proc, 1, 3), ("训练室", train, 1, 3)]
    for i, (label, var, lo, hi) in enumerate(fields):
        tk.Label(pf, text=label).grid(row=i // 6, column=(i % 6) * 2, sticky="e", padx=3, pady=3)
        ttk.Spinbox(pf, from_=lo, to=hi, width=4, textvariable=var).grid(row=i // 6, column=(i % 6) * 2 + 1)
    pw_out = tk.Text(tab5, height=12, width=70)
    pw_out.pack(pady=8)

    def calc_power(*_):
        gens = [g for g in (g1.get(), g2.get(), g3.get()) if g > 0]
        trades = [t for t in (tr1.get(), tr2.get(), tr3.get()) if t > 0]
        manus = [m.get() for m in mn if m.get() > 0]
        r = power_balance(gens, manus, trades, (dorm_n.get(), dorm_lv.get()),
                          meet.get(), off.get(), proc.get(), train.get())
        pw_out.delete("1.0", "end")
        pw_out.insert("end", f"供电 {r['供电']} | 总耗电 {r['总耗电']} | 富余 {r['富余']:+d} | "
                     f"{'✓ 可行' if r['可行'] else '✗ 超支'} | 宿舍轮休位 {r['宿舍轮休位']}\n")
        for k, v in r["耗电明细"].items():
            pw_out.insert("end", f"  {k}: {v}\n")
    for _, var, _, _ in fields:
        var.trace_add("write", calc_power)
    calc_power()

    root.mainloop()


# =====================================================================
# 六、入口
# =====================================================================

def main(argv):
    if "--selftest" in argv:
        return 0 if selftest() else 1
    if "--line" in argv:
        # 用法: --line 站级 配方 [目标小时] [光环%]
        i = argv.index("--line")
        level = int(argv[i + 1]); recipe = argv[i + 2]
        recipe = {"经验": "中级作战记录", "碎片": "源石碎片"}.get(recipe, recipe)
        if recipe not in RECIPES:
            hits = [k for k in RECIPES if recipe in k]
            if len(hits) != 1:
                print(f"未知配方「{recipe}」，可选：{'、'.join(RECIPES)}")
                return 1
            recipe = hits[0]
        target = float(argv[i + 3]) if len(argv) > i + 3 else 24.0
        aura = float(argv[i + 4]) / 100 if len(argv) > i + 4 else 0.0
        workers = MANU_LEVELS[level]["slots"]
        print(f"约束线：{recipe} · {level}级站 · 目标{target}h爆仓 · 光环+{aura*100:.0f}%")
        print(f"{'库存加成':<12}{'容纳':>6}{'所需总效率':>10}{'所需技能合计':>12}")
        for span, count, e, skill in constraint_line(level, recipe, target, workers, aura):
            print(f"{span:<12}{count:>6}{e:>10.3f}{skill:>11.1%}")
        return 0
    if "--list" in argv:
        presets = load_presets()
        for name, p in presets.items():
            if name.startswith("_"):
                continue
            print(f"{name:32s} {p.get('设施','?'):6s}")
        return 0
    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
