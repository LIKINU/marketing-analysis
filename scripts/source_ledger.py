#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_ledger.py — 数据来源台账：扫描「无来源数字」并生成附录台账

MBB 硬规矩：每个数字必须有 SOURCE；IPA 硬规矩：图表须标基值/显著性/置信区间。
本脚本机械检查「含数字的句子有没有来源与口径」，并输出可直接粘进附录的台账骨架。

用法:
  python source_ledger.py report.md                 # 覆盖率 + 缺来源清单
  python source_ledger.py report.md --out 台账.md    # 生成《数据来源台账》附录骨架
  python source_ledger.py report.md --min 0.8        # 覆盖率门槛（默认 0.8）
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mbb_common import (  # noqa: E402
    CONFIDENCE, VAGUE_SOURCES, has_source, is_fake_source, numbered_sentences, read_text,
)

CALIBER_HINTS = ["口径", "定义为", "计算方式", "=", "＝"]


def scan(path):
    text = read_text(path)
    sents = numbered_sentences(text)
    no_source, with_source, vague, unverified = [], [], [], []
    for ln, s in sents:
        if any(v in s for v in VAGUE_SOURCES):
            vague.append((ln, s))
        if "【未核实】" in s:
            unverified.append((ln, s))
        if has_source(s):
            with_source.append((ln, s))
        else:
            no_source.append((ln, s))
    return text, sents, with_source, no_source, vague, unverified


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--out", help="生成台账 markdown")
    ap.add_argument("--min", type=float, default=0.8, help="来源覆盖率门槛")
    a = ap.parse_args()

    text, sents, with_src, no_src, vague, unver = scan(a.path)
    total = len(sents)
    rate = (len(with_src) / total) if total else 0.0

    print(f"【数据来源台账】{os.path.basename(a.path)}")
    print(f"含数字句 {total} ｜ 有来源 {len(with_src)} ｜ 缺来源 {len(no_src)} ｜ 覆盖率 {rate:.0%}（门槛 {a.min:.0%}）\n")

    if no_src:
        print(f"── 缺来源清单（{len(no_src)} 条，按优先级补）──")
        for ln, s in no_src[:40]:
            print(f"  L{ln}: {s[:90]}")
        if len(no_src) > 40:
            print(f"  …另有 {len(no_src) - 40} 条")
    if vague:
        print(f"\n── 泛引用（不合格来源，硬错误）──")
        for ln, s in vague:
            print(f"  L{ln}: {s[:90]}")
    if unver:
        print(f"\n── 【未核实】泄漏（硬错误，不得进交付稿）──")
        for ln, s in unver:
            print(f"  L{ln}: {s[:90]}")

    has_caliber = sum(1 for _, s in with_src if any(h in s for h in CALIBER_HINTS))
    print(f"\n── 三要素检查 ──")
    print(f"  [{'OK' if len(with_src) else 'NG'}] 来源标注：{len(with_src)} 条")
    print(f"  [{'OK' if has_caliber else 'WARN'}] 口径说明：{has_caliber} 条含口径/计算方式")
    print(f"  [{'OK' if not unver else 'NG'}] 【未核实】泄漏：{len(unver)} 条")
    print(f"  [{'OK' if not vague else 'NG'}] 泛引用：{len(vague)} 条")

    ok = rate >= a.min and not unver and not vague
    print(f"\n判定：{'通过（数据底座合格）' if ok else '不通过——来源不达标，禁止定稿'}")

    if a.out:
        rows = []
        for ln, s in sents:
            mark = "【行业认知】"
            for cm in CONFIDENCE:
                if cm in s:
                    mark = cm
            frag = re.sub(r"[|\n]", " ", s)[:60]
            rows.append(f"| {frag} | <数值> | <来源> | <口径> | <时点> | {mark} |")
        out = ["# 附录 · 数据来源台账\n",
               "> 每个数字必须能回答三件事：谁出的（来源）、怎么算的（口径）、什么时候的（时点）。",
               "> 缺任一列 = 不合格数据；【未核实】不得进正文。\n",
               "| 数据点 | 数值 | 来源 | 口径 | 时点 | 可信度 |",
               "|---|---|---|---|---|---|"] + rows
        with open(a.out, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        print(f"\n已生成台账骨架：{a.out}（{len(rows)} 行待补，模糊项已填入原文片段）")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
