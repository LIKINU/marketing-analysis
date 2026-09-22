#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""storyline.py — 故事线（ghost deck）工具：标题通读测试 + 结论句判定

MBB 最便宜、最狠的一道整稿质检：把所有标题抽出来连读，若能复述完整论证 → 结构成立；
若读出来是一堆「市场概览 / 现状分析」式主题词 → 论证不存在。

用法:
  python storyline.py report.md            # 通读测试 + 逐条判定
  python storyline.py report.md --ghost    # 输出 ghost deck 骨架（先写标题，再填内容）
  python storyline.py --check-titles titles.txt
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mbb_common import headings, is_conclusion_title, is_topic_title, read_text  # noqa: E402

GHOST = """# Ghost Deck 骨架（先写标题，再填内容）

> 规则：每个标题必须是**完整结论句**（含谓语 + 尽量含数字）；读不出结论的标题不许进这一页。
> 用法：先把下面 6–10 行的标题填满，确认叙事成立，再展开正文。

1. 【封面】{{报告名}}：{{一句话结论}}
2. 【执行摘要】{{五句话：问题 / 结论 / 依据 / 代价 / 建议}}
3. 【核心发现 1】{{结论句 + 数字}}
4. 【核心发现 2】{{结论句 + 数字}}
5. 【核心发现 3】{{结论句 + 数字}}
6. 【机制归因】{{它为什么能/不能做到——因果链}}
7. 【AI 营销专项】{{AI 用在哪个环节，省了多少 / 提了多少}}
8. 【对标与差距】{{我们 vs 对标：差在哪一项、差多少}}
9. 【风险与反方】{{最可能怎么错 / 什么会推翻它}}
10. 【结论与含义】{{所以对决策者意味着什么，下一步是什么}}

自检：把 3–10 行的标题单独复制成一段连读，如果能读成一个完整论证 → 通过；否则重写标题。
"""


def classify(titles):
    rows = []
    for lvl, t in titles:
        if lvl < 2 or lvl > 4:
            continue
        if is_conclusion_title(t):
            kind = "结论句"
        elif is_topic_title(t):
            kind = "主题词"
        else:
            kind = "中性"
        rows.append((lvl, t, kind))
    return rows


def report(path):
    text = read_text(path)
    rows = classify(headings(text))
    total = len(rows)
    conclus = sum(1 for r in rows if r[2] == "结论句")
    topic = [r for r in rows if r[2] == "主题词"]
    rate = (conclus / total * 100) if total else 0.0

    print(f"【标题通读测试】{os.path.basename(path)}")
    print(f"标题总数 {total} ｜ 结论句 {conclus} ｜ 主题词 {len(topic)} ｜ 结论句占比 {rate:.0f}%\n")
    for lvl, t, kind in rows:
        flag = {"结论句": "OK  ", "中性": "WARN", "主题词": "NG  "}[kind]
        print(f"  [{flag}] {'  ' * (lvl - 2)}{t}")

    print("\n── 通读结果（只读标题）──")
    print(" / ".join(t for _, t, k in rows if k != "主题词") or "（无可读标题）")
    print()

    verdict_ok = rate >= 80 and not topic
    if topic:
        print("主题词标题（必须改成结论句）：")
        for _, t, _ in topic:
            print(f"  · {t}  →  改成：<结论 + 数字>")
    print(f"\n判定：{'通过（叙事成立）' if verdict_ok else '不通过——标题读不出论证，禁止定稿'}")
    print(f"门槛：结论句占比 ≥80% 且主题词标题 = 0（当前 {rate:.0f}% / {len(topic)} 个）")
    return 0 if verdict_ok else 1


def check_titles(path):
    titles = []
    for line in read_text(path).splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            titles.append((2, s))
    return report_titles(titles, os.path.basename(path))


def report_titles(rows_in, name):
    rows = []
    for lvl, t in rows_in:
        if is_conclusion_title(t):
            kind = "结论句"
        elif is_topic_title(t):
            kind = "主题词"
        else:
            kind = "中性"
        rows.append((lvl, t, kind))
    total = len(rows)
    conclus = sum(1 for r in rows if r[2] == "结论句")
    topic = [r for r in rows if r[2] == "主题词"]
    for lvl, t, kind in rows:
        flag = {"结论句": "OK  ", "中性": "WARN", "主题词": "NG  "}[kind]
        print(f"  [{flag}] {t}")
    ok = total > 0 and conclus / total >= 0.8 and not topic
    print(f"\n{name}：结论句 {conclus}/{total}，主题词 {len(topic)} → {'通过' if ok else '不通过'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="报告 markdown")
    ap.add_argument("--ghost", action="store_true", help="输出 ghost deck 骨架")
    ap.add_argument("--check-titles", help="只校验一份纯标题清单")
    a = ap.parse_args()

    if a.ghost:
        print(GHOST)
        return 0
    if a.check_titles:
        return check_titles(a.check_titles)
    if not a.path:
        ap.error("需要报告路径，或用 --ghost / --check-titles")
    return report(a.path)


if __name__ == "__main__":
    sys.exit(main())
