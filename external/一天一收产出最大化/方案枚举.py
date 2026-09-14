# -*- coding: utf-8 -*-
"""
方案枚举 —— 一天一收产出最大化（R4 版）
==========================================
以 6 天 ＝ 两个 72h 周期（每周期 A 段 48h 主力 ＋ B 段 24h 顶班，第 2 周期
B 段兼作泡泡火神/洋灰豆苗的休整日）逐站逐日核算推荐方案 R3，并附对照口径。
全部计算调用 爆仓计算器.py 的引擎，报告数字以本脚本输出为准。

结构总纲（口径真源见 01-最终报告.md）：
- 布局 342-321-3332，宿舍全 1 级，发电/会客空放，540 电恰好平衡；
- 中枢两套轮换：
    A 段（D1-2 / D4-5，各 48h）：玛恩纳+Mon3tr+临光+杜宾+红
        —— 公事公办扩散 5 笑脸 = 全基建 +0.25/h；Mon3tr 制造+2%；无贸易光环。
    B 段（D3 / D6，各 24h）：维什戴尔+魔王+明椒+灵知+冰酿
        —— 巴别塔之帜体系 +0.20/h；明椒贸易+7%；灵知精密计算（-15%效率/+6上限，
           仅通过贸易站谢拉格干员银灰生效）支撑孑组；中枢笑脸 = 冰酿+灵知幕后指挥。
- 但书站（菲亚 007 永续）队友接力制：D1-2 焰狐龙梓兰（20%/+3上限）→ D3 但书单人 →
  D4-5 四月（精零 α 档即可，+10%/+2 上限未锁）→ D6 但书单人；
  菲亚每周期只换但书 4 次（D1/D3/D4/D6 上岗前），D2/D5 换玛恩纳作体系保险（R4 口径）；
- 三级赤金站第三人轮换：奇周期 D1-2 清流（60%，饱和 41）→ D3 夜烟 → 偶周期 D4-5 砾 →
  D6 休整日（泡泡火神下岗，夜烟+砾+白板 27 枚）；
- 二级赤金站：洋灰豆苗常驻，D6 休整（黑角+卡达 22.4 枚）。

用法：python 方案枚举.py
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from 爆仓计算器 import manufacture_burst, power_balance, trade_burst, total_efficiency

HARVEST = 24.0
DRONE_BUDGET = 235               # 无人机日预算（清理区域满）
DRONE_EFF = DRONE_BUDGET / 480.0  # 0.4896 效率当量/日
EXT_GOLD = 10                    # 外源赤金 枚/日

# 六天 = 两周期；A 段（贸易无光环、制造+2%）、B 段（贸易+7%、制造无光环）
DAYS = [("D1", 0.00, 0.02), ("D2", 0.00, 0.02), ("D3", 0.07, 0.00),
        ("D4", 0.00, 0.02), ("D5", 0.00, 0.02), ("D6", 0.07, 0.00)]


# =====================================================================
# 一、R2 站点清单：每站一个函数 day(0..5) -> (在岗成员, 结果dict, 产物类型)
# =====================================================================

def s_trade3(d):
    """三级贸易：A 段巫恋组（桃金娘档，未饱和按效率）；B 段（D3/D6）孑银灰可露希尔（灵知中枢）。
    孑组口径（用户裁决）：市井之道按满单稳定效率 4%×上限；上限=10+4(银灰)+6(灵知借银灰)=20；
    灵知-15% 只压银灰（谢拉格），银灰 20→5；固定技能=5+10=15%。"""
    _, aura_t, _ = DAYS[d]
    if d not in (2, 5):
        e = total_efficiency(1.0, 3, 0.01, 0.90, aura_t)
        r = trade_burst(3, 5, "裁缝α峰值", "龙舌兰投资β", e, HARVEST)
        return "巫恋+龙舌兰+桃金娘", r, "贸易"
    cap_total, jie = 20, 0.80                      # 上限 20（压缩取整敏感性档见报告§五.4）
    e = 1.0 + 0.03 + 0.05 + 0.10 + jie + aura_t
    r = trade_burst(3, cap_total - 10, None, "可露希尔特别订单", e, HARVEST)
    return "孑+银灰+可露希尔（灵知中枢）", r, "贸易"


def s_trade2(d):
    """二级贸易：但书站菲亚 007 永续；队友接力 D1-2 崖心 → D3 单人 → D4-5 四月 → D6 单人。"""
    _, aura_t, _ = DAYS[d]
    if d in (0, 1):
        e = total_efficiency(1.0, 2, 0.01, 0.20, aura_t)
        r = trade_burst(2, 3, "lv2_常规", "但书违约β", e, HARVEST)
        return "但书+焰狐龙梓兰（菲亚007）", r, "贸易"
    if d in (3, 4):
        e = total_efficiency(1.0, 2, 0.01, 0.10, aura_t)
        r = trade_burst(2, 2, "lv2_常规", "但书违约β", e, HARVEST)
        return "但书+四月（精零α档，菲亚007）", r, "贸易"
    e = total_efficiency(1.0, 1, 0.01, 0.00, aura_t)
    r = trade_burst(2, 4, "lv2_常规", "但书违约β", e, HARVEST)
    return "但书单人（菲亚007，B段）", r, "贸易"


def s_trade1(d):
    """一级贸易：佩佩 48h 班（D1-2 / D4-5），B 段（D3/D6）空放。"""
    if d in (2, 5):
        return "空放", {"日龙门币": 0.0, "日赤金消耗": 0.0}, "贸易"
    minutes, cap, pay = 270, 7, 1000
    orders = min(HARVEST * 60 / minutes, cap)
    r = {"E": "固定4:30/单", "订单上限": cap, "爆仓时间h": round(minutes * cap / 60.0, 1),
         "饱和": orders >= cap, "日完成单数": round(orders, 2),
         "日龙门币": round(orders * pay), "日赤金消耗": 0.0, "日等效赤金价值": 0.0}
    return "佩佩（48h 班）", r, "贸易"


def s_gold3(d):
    """三级赤金：泡泡+火神常驻（D6 休整）；第三人 奇周期 D1-2 清流（60%）→ D3 夜烟 →
    偶周期 D4-5 砾 → D6 顶班 夜烟+砾+白板。技能基数：火神转化57−自身5＋泡泡10＝62%。"""
    _, _, aura_m = DAYS[d]
    if d in (0, 1):
        e = total_efficiency(1.0, 3, 0.01, 0.62 + 0.39, aura_m)
        r = manufacture_burst(3, 29, "赤金", e, HARVEST)
        return "泡泡+火神+引星棘刺", r, "赤金"
    if d == 2:
        e = total_efficiency(1.0, 3, 0.01, 0.62 + 0.30, aura_m)
        r = manufacture_burst(3, 29, "赤金", e, HARVEST)
        return "泡泡+火神+夜烟", r, "赤金"
    if d in (3, 4):
        e = total_efficiency(1.0, 3, 0.01, 0.62 + 0.60, aura_m)
        r = manufacture_burst(3, 29, "赤金", e, HARVEST)
        return "泡泡+火神+清流", r, "赤金"
    e = total_efficiency(1.0, 3, 0.01, 0.30 + 0.35, 0.0)
    r = manufacture_burst(3, 0, "赤金", e, HARVEST)
    return "夜烟+砾+白板（泡泡火神休整日）", r, "赤金"


def s_exp1(d):
    """三级经验 1：A 段红云组（16 份饱和）；B 段（D3/D6）卡缇+斑点+红豆（12 份饱和）。"""
    _, _, aura_m = DAYS[d]
    if d not in (2, 5):
        e = total_efficiency(1.0, 3, 0.01, 1.06, aura_m)
        r = manufacture_burst(3, 28, "中级作战记录", e, HARVEST)
        return "红云+稀音+刻俄柏", r, "经验"
    e = total_efficiency(1.0, 3, 0.01, 0.70, aura_m)
    r = manufacture_burst(3, 6, "中级作战记录", e, HARVEST)
    return "卡缇+斑点+红豆（顶班）", r, "经验"


def s_exp2(d):
    """三级经验 2：A 段圣约送葬人组（13 份饱和）；B 段（D3/D6）裁度+蛇屠箱+Castle-3（未饱和按速率）。"""
    _, _, aura_m = DAYS[d]
    if d not in (2, 5):
        e = total_efficiency(1.0, 3, 0.01, 0.60, aura_m)
        r = manufacture_burst(3, 15, "中级作战记录", e, HARVEST)
        return "圣约送葬人+食铁兽+卡达", r, "经验"
    e = total_efficiency(1.0, 3, 0.01, 0.65, aura_m)
    r = manufacture_burst(3, 16, "中级作战记录", e, HARVEST)
    return "裁度+蛇屠箱+Castle-3（顶班）", r, "经验"


def s_gold2(d):
    """二级赤金：洋灰豆苗常驻（每 2 周期需 1 休）；D6 休整（黑角+卡达）。"""
    _, _, aura_m = DAYS[d]
    if d != 5:
        e = total_efficiency(1.0, 2, 0.01, 0.30, aura_m)
        r = manufacture_burst(2, 18, "赤金", e, HARVEST)
        return "洋灰+豆苗", r, "赤金"
    e = total_efficiency(1.0, 2, 0.01, 0.10, 0.0)
    r = manufacture_burst(2, 25, "赤金", e, HARVEST)
    return "黑角+卡达（洋灰豆苗休整日）", r, "赤金"


STATIONS = [
    ("贸易Lv3", s_trade3), ("贸易Lv2", s_trade2), ("贸易Lv1", s_trade1),
    ("制造Lv3赤金", s_gold3), ("制造Lv3经验1", s_exp1),
    ("制造Lv3经验2", s_exp2), ("制造Lv2赤金", s_gold2),
]


def scheme_r3():
    rows = []
    for name, fn in STATIONS:
        rows.append((name, [fn(d) for d in range(6)]))

    print("=" * 104)
    print("R4 推荐方案 · 6 天两周期逐站逐日核算（342-321-3332，宿舍全 1 级，发电/会客空放）")
    print("周期：D1-2 A段 → D3 B段 → D4-5 A段 → D6 B段(休整日：泡泡火神、洋灰豆苗下岗休整)")
    print("=" * 104)
    for name, days in rows:
        print(f"\n【{name}】")
        for (day_name, _, _), (who, r, _kind) in zip(DAYS, days):
            burst = r.get("爆仓时间h")
            burst_s = f"{burst:.1f}h" if isinstance(burst, (int, float)) else "—"
            sat_s = "饱和" if r.get("饱和") else "未饱和"
            if "日龙门币" in r:
                if r.get("日龙门币", 0) == 0 and who == "空放":
                    print(f"  {day_name}: 空放（0 产出、0 赤耗）")
                    continue
                print(f"  {day_name}: {who} | 爆仓 {burst_s} [{sat_s}] "
                      f"| 币 {r['日龙门币']:.0f} | 赤耗 {r.get('日赤金消耗', 0):.1f}")
            else:
                out = r.get("日产经验") or r.get("日产件数") or 0
                unit = "经验" if r.get("日产经验") else "枚"
                print(f"  {day_name}: {who} | 爆仓 {burst_s} [{sat_s}] | 产出 {out:.1f} {unit}")

    lmb = exp = gold_prod = gold_use = 0.0
    for name, days in rows:
        for _, r, kind in days:
            if kind == "贸易":
                lmb += r.get("日龙门币", 0.0)
                gold_use += r.get("日赤金消耗", 0.0)
            elif kind == "赤金":
                gold_prod += r.get("日产件数", 0.0)
            else:
                exp += r.get("日产经验", 0.0)
    lmb, exp, gold_prod, gold_use = (x / 6 for x in (lmb, exp, gold_prod, gold_use))

    gap = gold_prod + EXT_GOLD - gold_use
    drone_used = abs(gap) * 480 / 20 if gap < 0 else 0.0    # 补平缺口所需架数
    drone_left = DRONE_BUDGET - drone_used
    exp_bonus = drone_left / 480 * 8000 if drone_left > 0 else 0.0

    pw = power_balance([3, 3], [3, 3, 3, 2], [3, 2, 1])
    print("\n" + "=" * 104)
    print("R4 日均汇总（6 天 / 6）")
    print("=" * 104)
    print(f"  龙门币        {lmb:>10.0f} /日")
    print(f"  经验          {exp:>10.0f} /日 ＋ 无人机余架 +{exp_bonus:.0f} ＝ {exp + exp_bonus:.0f} /日")
    print(f"  赤金 产出     {gold_prod:>10.1f} 枚/日 ＋ 外源 {EXT_GOLD} ＝ {gold_prod + EXT_GOLD:.1f}")
    print(f"  赤金 消耗     {gold_use:>10.1f} 枚/日")
    print(f"  赤金 盈亏     {gap:>10.1f} 枚/日 → 无人机投 {drone_used:.0f} 架补平，余 {drone_left:.0f} 架投经验")
    print(f"  钱书比        {lmb / max(exp + exp_bonus, 1):>10.2f} : 1")
    print(f"  电力          供电 {pw['供电']} / 耗电 {pw['总耗电']} / 富余 {pw['富余']:+d}（宿舍轮休位 {pw['宿舍轮休位']}）")
    return {"龙门币": lmb, "经验": exp + exp_bonus, "赤金盈亏": gap,
            "赤耗": gold_use, "赤产": gold_prod}


def scheme_r1m_reference():
    """对照 R1m：企鹅版 B 段 + 银灰 007 但书站 + 同样的休整日成本与夜烟 30% 修正口径。
    该口径下赤金失衡——展示孑组对赤金账的修复价值。"""
    lmb = exp = gold_prod = gold_use = 0.0
    e = total_efficiency(1.0, 3, 0.01, 0.90, 0.00)             # 巫恋 ×4
    r = trade_burst(3, 5, "裁缝α峰值", "龙舌兰投资β", e, HARVEST)
    lmb += r["日龙门币"] * 4; gold_use += r["日赤金消耗"] * 4
    e = total_efficiency(1.0, 2, 0.01, 0.65, 0.07)             # 企鹅 ×2
    r = trade_burst(3, 4, "lv3_常规", None, e, HARVEST)
    lmb += r["日龙门币"] * 2; gold_use += r["日赤金消耗"] * 2
    for aura, n in ((0.00, 4), (0.07, 2)):                     # 银灰 007 ×6
        e = total_efficiency(1.0, 2, 0.01, 0.20, aura)
        r = trade_burst(2, 4, "lv2_常规", "但书违约β", e, HARVEST)
        lmb += r["日龙门币"] * n; gold_use += r["日赤金消耗"] * n
    lmb += 5333 * 4                                             # 佩佩 ×4
    for d in range(6):                                          # 制造与 R2 相同（含休整日）
        for fn in (s_gold3, s_gold2, s_exp1, s_exp2):
            _, r, kind = fn(d)
            if kind == "赤金":
                gold_prod += r["日产件数"]
            else:
                exp += r["日产经验"]
    gap = (gold_prod / 6 + EXT_GOLD) - gold_use / 6
    print("\n" + "=" * 104)
    print("对照 R1m：企鹅版 B 段＋银灰 007 但书站（含休整日成本、夜烟 30% 修正口径）")
    print("=" * 104)
    print(f"  龙门币 {lmb / 6:.0f} / 经验 {exp / 6:.0f} / 赤金缺口 {gap:+.1f} 枚/日"
          f" → 无人机上限 +{DRONE_EFF * 20:.1f} 仍缺 {max(0.0, -gap - DRONE_EFF * 20):.1f} 枚/日 —— 赤金失衡")
    print("  差额拆解（R2 − R1m）：孑组替换企鹅 币 +2046；但书站接力制替换银灰 007 币 −2228；")
    print("  赤金：孑组比企鹅多耗 +1.4、但书接力省 3.9 → 净 −2.5 枚/日，赤金恢复平衡。")


def main():
    scheme_r3()
    scheme_r1m_reference()
    print("\n口径：A 段无贸易光环/制造+2%（Mon3tr）；B 段贸易+7%（明椒）/制造无光环；")
    print("     孑组按满单稳定效率（用户裁决），上限 20（压缩取整敏感性档 19：币 −133、赤耗 −0.7，仍平衡）；")
    print("     饱和站日产＝一仓容量；未饱和站＝速率（1440×E/单件耗时）。")


if __name__ == "__main__":
    main()
