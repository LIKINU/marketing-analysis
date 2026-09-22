#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chart_check.py — 图表规范检查（MBB「one exhibit = one message」+ SOURCE 纪律）

判据来源：MBB 幻灯片惯例（每页一个信息；标题须为结论句；100% 图表带 SOURCE 与口径）
          + IPA 实效奖 12 条（柱状图 y 轴原点必须为 0；须标基值）。

用法:
  python chart_check.py report.md          # 检查「图表清单」
  python chart_check.py --template         # 输出图表清单模板
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mbb_common import find_sections, is_conclusion_title, read_text  # noqa: E402

CALIBER = ["口径", "单位", "区间", "统计范围", "样本", "y 轴", "Y 轴", "基准值", "基值", "显著性"]
PREFIX_RE = re.compile(r"^\s*[-*]?\s*(图|图表|Exhibit|Exhibit\s*\d+|图\s*\d+)[\s\.、:：]*", re.I)

TEMPLATE = """# 图表清单（每张图 = 一个信息）

> 规则：① 标题必须是**结论句**（含数字或结论动词），不是「XX 趋势图」；② 每张图必须有 **SOURCE** 行（来源 + 口径 + 时点）；
> ③ 「一图一信息」——同一张图里不允许塞两个结论；④ 柱状图的 y 轴必须从 0 起，折线/柱图须标基值。

| # | 图表标题（结论句） | 图表类型 | 回答什么问题 | 来源 | 口径 | 时点 |
|---|---|---|---|---|---|---|
| 图 1 | <结论 + 数字> | 柱状/折线/矩阵 | <一句话> | <谁出的> | <怎么算的> | <时间段> |
| 图 2 | <结论 + 数字> | | | | | |
| 图 3 | <结论 + 数字> | | | | | |
"""


def check(path):
    text = read_text(path)
    hits = find_sections(text, ["图表清单", "图表目录", "Exhibit"], max_level=3)
    if not hits:
        print(f"【图表规范】{os.path.basename(path)}")
        print("  [NG] 缺「图表清单」章节 —— 无法逐图核查（每张图必须有 SOURCE 行）")
        print("\n判定：不通过")
        return 1

    body = hits[0][2]
    entries = [l.strip() for l in body.splitlines()
               if l.strip().startswith(("-", "*", "|")) and re.search(r"图|Exhibit", l)]
    if not entries:
        print("  [NG] 图表清单里没有条目（空清单 = 没做图表规划）")
        return 1

    print(f"【图表规范】{os.path.basename(path)}")
    print(f"  检出图表条目 {len(entries)} 条\n")

    bad_title, no_source, no_caliber, titles = [], [], [], []
    for e in entries:
        core = PREFIX_RE.sub("", e).split("（")[0].split("(")[0].strip()
        titles.append(core)
        flag = []
        if not is_conclusion_title(core):
            bad_title.append(core)
            flag.append("标题非结论句")
        if not ("来源" in e or "SOURCE" in e.upper() or "source" in e.lower()):
            no_source.append(core)
            flag.append("缺来源")
        if not any(c in e for c in CALIBER):
            no_caliber.append(core)
            flag.append("缺口径")
        print(f"  [{'OK  ' if not flag else 'NG  '}] {core[:52]}{'  ← ' + '；'.join(flag) if flag else ''}")

    dup = len(titles) != len(set(titles))
    has_yaxis_note = bool(re.search(r"y\s*轴|Y\s*轴|原点", text))
    print()
    checks = [
        ("每张图标题为结论句", not bad_title, f"不合格 {len(bad_title)} 条"),
        ("每张图有来源（SOURCE）", not no_source, f"缺来源 {len(no_source)} 条"),
        ("每张图有口径说明", not no_caliber, f"缺口径 {len(no_caliber)} 条（建议项）"),
        ("一图一信息（无重复标题）", not dup, "标题重复 → 疑似一图多信息" if dup else "标题无重复"),
        ("柱图 y 轴原点说明", has_yaxis_note, "缺「y 轴从 0 起」类说明（IPA 口径）"),
    ]
    ok_all = True
    for name, ok, note in checks:
        soft = name in ("每张图有口径说明", "柱图 y 轴原点说明")
        print(f"  [{'OK  ' if ok else ('WARN' if soft else 'NG  ')}] {name} — {note}")
        if not ok and not soft:
            ok_all = False
    print(f"\n判定：{'通过（图表规范合格）' if ok_all else '不通过——图表不合格，禁止定稿'}")
    return 0 if ok_all else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--template", action="store_true")
    a = ap.parse_args()
    if a.template:
        print(TEMPLATE)
        return 0
    if not a.path:
        ap.error("需要报告路径，或 --template")
    return check(a.path)


if __name__ == "__main__":
    sys.exit(main())
