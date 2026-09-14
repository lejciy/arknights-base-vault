# -*- coding: utf-8 -*-
"""
心情计算器 —— 一天一收产出最大化（配套工具）
==============================================
逐人计算心情净消耗 / 最长在岗 / 恢复时间 / 菲亚梅塔007容量。
口径真源：docs\1-基础设定\设施与进驻\心情与宿舍.md、docs\2-干员技能\释义\菲亚梅塔.md

关键口径（2026-09-14 用户裁决）：
1. 技能心情修正只作用于**自己**（囤积者-0.25 = 泡泡自己减），除非技能原文写明
   "全体/同站"（如巫恋低语全体+0.25、槐琥团队精神消除同站自身影响）；
2. 中枢干员自身也消耗（1.0/h），中枢内笑脸技能（+0.05）互相恢复；
3. 三大群体恢复体系（玛恩纳扩散/维什戴尔/重岳）取最高不叠加；
4. 一天一收 = 每天一次操作窗口 → 菲亚每日只能互换 1 次，输送上限 24 点/日；
5. **红脸涣散后果（心情与宿舍.md:19）**：心情归零后后勤技能与进驻加成（+1%/+5%等）
   全部失效、干员仍占位——任何依赖技能的站位（含佩佩特别独占订单）都必须维持心情，
   不存在"红脸白嫖"。

用法：python 心情计算器.py           # GUI
      python 心情计算器.py --check   # 自检（口径用例）
"""
import sys

# ---------------------------------------------------------------- 引擎

# 站内多人减免：按工作状态人数
IN_STATION_RELIEF = {1: 0.00, 2: 0.05, 3: 0.10}
CENTRAL_FULL_RELIEF = 0.25      # 中枢满 5 名工作干员
FIYA_DAILY_CAP = 24.0           # 每日 1 次互换的输送上限（24 − 目标剩余 ≤ 24）
DORM_RECOVERY = {1: 2.0, 2: 2.5, 3: 3.0, 4: 3.5, 5: 4.0}   # 简化档：宿舍等级→恢复/h


def mood_rate(workers, self_skill=0.0, station_wide=0.0,
              aura_recovery=0.0, central_full=True):
    """单人心情净消耗/h。aura_recovery=中枢体系恢复（取最高档，见下）。"""
    r = (1.0
         - IN_STATION_RELIEF.get(workers, 0.0)
         - (CENTRAL_FULL_RELIEF if central_full else 0.0)
         - aura_recovery
         + station_wide
         + self_skill)
    return round(max(r, 0.0), 4)


# 中枢体系恢复档（作用于五类设施工作干员；中枢自己不吃自己的体系）
AURAS = {
    "无": 0.0,
    "玛恩纳扩散×3(3笑脸)": 0.15,
    "玛恩纳扩散×4(4笑脸)": 0.20,
    "玛恩纳扩散×5(全笑脸套)": 0.25,
    "维什戴尔+魔王": 0.20,
    "维什戴尔单人": 0.10,
    "重岳(基础档)": 0.05,
}


def max_shift_hours(rate, cap=24.0):
    return float("inf") if rate <= 0 else cap / rate


def recover_hours(loss, dorm_level=1):
    speed = DORM_RECOVERY[dorm_level]
    return loss / speed


def central_member_rate(inner_relieve_count=5):
    """中枢干员净耗：1.0 − 中枢满员0.25 − 中枢内笑脸技能数×0.05。"""
    return round(1.0 - CENTRAL_FULL_RELIEF - 0.05 * inner_relieve_count, 4)


def fiya_support(daily_loss_total, targets_cycle=2):
    """菲亚007判定：全组日耗 ≤ 24 点（每日一次互换），成员隔天轮换被换。"""
    ok = daily_loss_total <= FIYA_DAILY_CAP + 1e-9
    return {"组日耗": round(daily_loss_total, 2),
            "菲亚日输送上限": FIYA_DAILY_CAP,
            "可永续": ok,
            "备注": "每日互换1次（操作窗口限制）；成员隔天轮换，被换者回到24点"}


# 常用干员心情修正（自身档；来源：技能快照）
SELF_MOOD = {
    "泡泡": -0.25, "火神": -0.25, "贝娜": -0.25, "红云": -0.25, "刻俄柏": -0.25,
    "帕拉斯": -0.25, "洋灰": -0.25, "豆苗": -0.25, "卡达": -0.25, "娜仁图雅": -0.25,
    "Miss.Christine": -0.25, "清道夫": -0.25,
    "巫恋": -0.25, "龙舌兰": -0.25, "桃金娘": -0.25, "柏喙": -0.25, "卡夫卡": -0.25,
    "明椒": -0.25, "折光": -0.25,
    "裁度(精2前)": +0.25, "拉普兰德": +0.3, "阿罗玛": +0.25,
    "水灯心": +1.0, "地灵": +2.0, "斥罪": +0.5,
    "恩怨拉普兰德档": +0.3,
}
STATION_WIDE = {"巫恋低语": +0.25}   # 全站每人


def check():
    ok = True
    cases = []
    # 1. 泡泡（囤积者-0.25 是自己）：Lv3 站、玛恩纳5笑脸扩散0.25
    r = mood_rate(3, SELF_MOOD["泡泡"], 0, 0.25)
    cases.append(("泡泡@玛恩纳全笑脸套", r, 0.15))
    # 2. 砾（无技能修正）同站
    r = mood_rate(3, 0, 0, 0.25)
    cases.append(("砾@同上", r, 0.40))
    # 3. 巫恋（低语全站+0.25、自身裁缝-0.25）
    r = mood_rate(3, SELF_MOOD["巫恋"], STATION_WIDE["巫恋低语"], 0.25)
    cases.append(("巫恋@同上", r, 0.40))
    # 4. 中枢干员（5 技能笑脸）
    r = central_member_rate(5)
    cases.append(("中枢·全笑脸套成员", r, 0.50))
    r = central_member_rate(4)
    cases.append(("中枢·4笑脸+1功能位", r, 0.55))
    # 5. 菲亚容量
    f = fiya_support(24.0)
    cases.append(("菲亚·但书站日耗24", f["可永续"], True))
    f = fiya_support(32.4)
    cases.append(("菲亚·巫恋组日耗32.4", f["可永续"], False))
    for name, got, want in cases:
        flag = abs(got - want) < 1e-6 if isinstance(want, float) else got == want
        ok &= flag
        print(f"  {'✓' if flag else '✗'} {name}: got={got} want={want}")
    print("[心情计算器自检]", "全部通过" if ok else "存在失败")
    return ok


# ---------------------------------------------------------------- GUI
def run_gui():
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("心情计算器 · 一天一收")
    root.geometry("760x520")

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=6, pady=6)

    # Tab1 逐人计算
    t1 = ttk.Frame(nb, padding=8)
    nb.add(t1, text=" 逐人净耗/在岗/恢复 ")
    f = ttk.Frame(t1)
    f.pack(fill="x")
    workers = tk.IntVar(value=3)
    self_skill = tk.DoubleVar(value=0.0)
    station_wide = tk.DoubleVar(value=0.0)
    aura = tk.StringVar(value="玛恩纳扩散×5(全笑脸套)")
    dorm = tk.IntVar(value=1)
    op_full = tk.BooleanVar(value=True)
    is_central = tk.BooleanVar(value=False)
    central_smiles = tk.IntVar(value=5)
    for i, (lab, var, opts) in enumerate([
            ("站内人数(1-3)", workers, None),
            ("自身技能修正/h", self_skill, None),
            ("全站技能修正/h(如低语+0.25)", station_wide, None),
            ("宿舍等级", dorm, None)]):
        tk.Label(f, text=lab).grid(row=i // 4, column=(i % 4) * 2, sticky="e", padx=3, pady=2)
        ttk.Spinbox(f, from_=-2.0 if isinstance(var, tk.DoubleVar) else 1,
                    to=3.0 if isinstance(var, tk.DoubleVar) else 5,
                    increment=0.05 if isinstance(var, tk.DoubleVar) else 1,
                    width=6, textvariable=var).grid(row=i // 4, column=(i % 4) * 2 + 1)
    tk.Label(f, text="中枢体系").grid(row=1, column=0, sticky="e")
    ttk.Combobox(f, textvariable=aura, values=list(AURAS), width=20, state="readonly").grid(row=1, column=1)
    ttk.Checkbutton(f, text="中枢满员-0.25", variable=op_full).grid(row=1, column=2, columnspan=2)
    ttk.Checkbutton(f, text="本人是中枢干员(中枢内笑脸数→)", variable=is_central).grid(row=2, column=0, columnspan=2)
    ttk.Spinbox(f, from_=0, to=5, width=4, textvariable=central_smiles).grid(row=2, column=2)
    out = tk.Text(t1, height=10, width=80)
    out.pack(pady=6)

    def calc(*_):
        out.delete("1.0", "end")
        if is_central.get():
            rate = central_member_rate(central_smiles.get())
            out.insert("end", f"中枢干员：净耗 {rate}/h\n")
        else:
            rate = mood_rate(workers.get(), self_skill.get(), station_wide.get(),
                             AURAS[aura.get()], op_full.get())
            out.insert("end", f"净消耗：{rate}/h\n")
        mh = max_shift_hours(rate)
        if mh == float("inf"):
            out.insert("end", "最长在岗：∞（净回复）\n")
        else:
            out.insert("end", f"最长在岗：{mh:.1f}h（24点心情）\n")
            for shift in (24, 48):
                loss = rate * shift
                if loss <= 24:
                    out.insert("end", f"{shift}h 班：耗 {loss:.1f} 点 → 宿舍{dorm.get()}级恢复 "
                                       f"{recover_hours(loss, dorm.get()):.1f}h\n")
    for v in (workers, self_skill, station_wide, aura, dorm, op_full, is_central, central_smiles):
        v.trace_add("write", calc)
    calc()

    # Tab2 菲亚 007 判定
    t2 = ttk.Frame(nb, padding=8)
    nb.add(t2, text=" 菲亚梅塔007容量 ")
    tk.Label(t2, text="输入被支撑组每人净耗/h（逗号分隔，如 0.45,0.45,0.4）：").pack(anchor="w")
    entry = tk.StringVar(value="0.5,0.5")
    ttk.Entry(t2, textvariable=entry, width=30).pack(anchor="w", pady=4)
    out2 = tk.Text(t2, height=8, width=70)
    out2.pack()

    def calc2(*_):
        try:
            rates = [float(x) for x in entry.get().replace("，", ",").split(",") if x.strip()]
        except ValueError:
            out2.delete("1.0", "end")
            out2.insert("end", "输入格式错误")
            return
        daily = [r * 24 for r in rates]
        r = fiya_support(sum(daily))
        out2.delete("1.0", "end")
        out2.insert("end", f"各人日耗：{[round(d,1) for d in daily]}\n")
        for k, v in r.items():
            out2.insert("end", f"{k}: {v}\n")
        out2.insert("end", "（一天一收=每日 1 次互换窗口；成员隔天轮换被换满 24 点）\n")
    entry.trace_add("write", calc2)
    ttk.Button(t2, text="计算", command=calc2).pack()
    calc2()

    # Tab3 常用干员速查
    t3 = ttk.Frame(nb, padding=8)
    nb.add(t3, text=" 干员心情修正表 ")
    tv = ttk.Treeview(t3, columns=("干员", "自身修正/h", "说明"), show="headings", height=22)
    for c, w in zip(("干员", "自身修正/h", "说明"), (150, 100, 380)):
        tv.heading(c, text=c)
        tv.column(c, width=w, anchor="center")
    notes = {"裁度(精2前)": "精2替换后无增耗", "恩怨拉普兰德档": "恩怨+0.3",
             "水灯心": "办公室45%档不可24h连岗", "地灵": "同上+2/h", "斥罪": "50%档不可24h连岗"}
    for name, v in SELF_MOOD.items():
        tv.insert("", "end", values=(name, f"{v:+.2f}", notes.get(name, "")))
    tv.insert("", "end", values=("巫恋低语(全站)", "+0.25", "作用于同站每人"))
    tv.insert("", "end", values=("槐琥团队精神(全站)", "消除", "消除同站所有干员自身心情影响"))
    tv.pack(fill="both", expand=True)

    root.mainloop()


def main(argv):
    if "--check" in argv:
        return 0 if check() else 1
    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
