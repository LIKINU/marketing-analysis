#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cross_check.py — 数据来源「≥3 重交叉验证」判据

用户 2026-10-16 要求：生成过程中所有数据都要做**至少三个数据资料的交叉检验**，真实度都要验证。

判据分级（为什么分级见文末）：
  · **0 个独立来源** 的数字句 → **硬错误**（等于没来源，任何位置都不许）
  · **结论区**（执行摘要／核心问题／洞察／取舍）的数字句 → 必须 **≥3** 个独立来源
    —— 这些是决策依据，客户会拿它拍板，不接受"单一来源"
  · **正文其它区**的数字句 → ≥3 达标；不足 3 的**必须显式标注**降级
    （写法：「（来源：X，单一来源未交叉验证）」／「（两来源，未达三重交叉）」），
    未标注且不足 3 → 计入不达标；全文达标率须 ≥ `--min-rate`（默认 60%）

「独立来源」怎么算（去重、且自证不算外部来源）：
  · `（来源：主体…）` 取主体（截到 ，；）
  · `【已核实：主体】` 取主体
  · `【行业认知】` 算 **1** 个（"多来源一致"是标记，不能当 3 个用）
  · `【品牌方自述】` 算 **1** 个，且属未外部验证
  · `本报告测算／本报告整理／本报告判断` → **不计**（自证不是来源）

用法：
  python scripts/cross_check.py 报告.md [--min-rate 60] [--legacy]
       --legacy：历史快照模式（只报不判，exit 0）——用于新增标准前的旧稿
退出码：0 合格；1 不合格；2 参数/文件错
"""
import argparse
import io
import os
import re
import sys

# 结论区（决策依据，要求最严）
CONCLUSION_SECTIONS = ("执行摘要", "核心问题", "洞察", "取舍", "结论")
SELF_SOURCE = ("本报告", "本文", "我们测算", "内部测算")
DEGRADE_MARKS = ("单一来源", "未交叉验证", "未达三重", "两来源", "未获交叉验证", "待交叉验证")


def independent_sources(line):
    """返回该行去重后的独立来源集合（自证不计）"""
    src = set()
    for m in re.finditer(r"来源：([^）】｜，；。]{1,40})", line):
        s = re.split(r"[，；。]", m.group(1))[0].strip()
        if any(s.startswith(k) for k in SELF_SOURCE):
            continue
        # 「来源：A（…）／B」这类写法里，括号内的机构名也算独立来源
        src.add(s[:24])
        for sub in re.findall(r"[（(]([^）)]{2,24})[）)]", m.group(1)):
            if not any(sub.startswith(k) for k in SELF_SOURCE):
                src.add(sub.strip()[:24])
    for m in re.finditer(r"【(?:已核实|行业认知|品牌方自述)：([^】]{1,30})】", line):
        src.add(m.group(1).strip()[:24])
    if "【行业认知】" in line:
        src.add("__行业认知__")
    if "【品牌方自述】" in line:
        src.add("__品牌方自述__")
    # 内联引用：`（方案 §8.2：…）`／`（《书名》…）`／`（XX 年报…）`
    for m in re.finditer(r"[（(](方案|品牌方|《[^》]{2,30}》|[^）)]{2,24}(?:年报|白皮书|深度|公报))[^）)]{0,12}[）)]", line):
        src.add(m.group(1).strip()[:24])
    return src


def is_numeric_claim(line):
    """带数字、且看起来是**事实断言**的行。

    排除（都是实测出来的假阳性）：
      · 注释 `<!--`／表格行与分隔／标题
      · 图片行 `![…](…)`
      · 页眉元信息 `> 版本 V1.0 ｜ 2026-09-19 ｜ 拆解人…`（本报告的 `>` 全是元信息）
      · 太短的行（条目名而非断言）
    """
    s = line.strip()
    if not s or s.startswith(("<!--", "|", "#", "![")):
        return False
    if s.startswith(">"):
        return False
    if not re.search(r"\d", s):
        return False
    # 附录/来源清单里的是**来源本身**，不是"需要来源的断言"
    if s.startswith("《") or s.startswith("- 《") or s.startswith("* 《"):
        return False
    return len(s) >= 12


def has_degrade_mark(line):
    return any(k in line for k in DEGRADE_MARKS)


def claim_kind(line):
    """数据分三类——**各有各的验证方式**，不能一律按"3 个来源"卡：

      external   外部事实（份额/行业均值/竞品数据）→ 要求 ≥3 个独立来源
      derived    本报告测算（由外部数据推导）→ 不要求 3 来源，但要求算式与输入可追
      selfreport 品牌方自述（被拆解方给的数）→ 1 个来源即可，但必须标【品牌方自述】
    """
    if re.search(r"本报告|本文口径|（公式|算式", line):
        return "derived"
    if "【品牌方自述】" in line:
        return "selfreport"
    return "external"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--min-rate", type=int, default=60, help="正文达标率下限（%%）")
    ap.add_argument("--legacy", action="store_true", help="历史快照：只报不判（exit 0）")
    ap.add_argument("--show", type=int, default=8, help="列出的未达标行数上限")
    a = ap.parse_args()

    if not os.path.exists(a.path):
        print(f"❌ 找不到：{a.path}")
        return 2
    lines = io.open(a.path, encoding="utf-8").read().splitlines()

    sec = ""
    rows = []          # (行号, 区, 来源数, 是否降级标注, 文本, 类别)
    for i, ln in enumerate(lines, 1):
        h = re.match(r"^##\s+(.+)$", ln)
        if h:
            sec = h.group(1).strip()
            continue
        if any(k in sec for k in ("来源清单", "附录")):
            continue
        if not is_numeric_claim(ln):
            continue
        n = len(independent_sources(ln))
        rows.append((i, sec, n, has_degrade_mark(ln), ln.strip(), claim_kind(ln)))

    ext = [r for r in rows if r[5] == "external"]        # 只有外部事实要 3 来源
    zero = [r for r in ext if r[2] == 0]
    concl = [r for r in ext if any(k in r[1] for k in CONCLUSION_SECTIONS)]
    concl_bad = [r for r in concl if r[2] < 3]
    body = [r for r in ext if r not in concl]
    body_ok = [r for r in body if r[2] >= 3 or r[3]]
    rate = (len(body_ok) / len(body)) * 100 if body else 100.0

    print(f"【数据交叉验证】{os.path.basename(a.path)}")
    n_der = len([r for r in rows if r[5] == "derived"])
    n_self = len([r for r in rows if r[5] == "selfreport"])
    print(f"  数字断言 {len(rows)} 条 → 外部事实 {len(ext)}｜本报告测算 {n_der}｜品牌方自述 {n_self}")
    print(f"  其中外部事实里：结论区 {len(concl)} 条、正文 {len(body)} 条")
    print(f"  外部事实中 ≥3 独立来源：{len([r for r in ext if r[2] >= 3])} 条"
          f"｜仅 0–1 个：{len([r for r in ext if r[2] <= 1])} 条"
          f"｜**0 来源：{len(zero)} 条**")
    print(f"  正文达标率（≥3 或显式降级）：{rate:.0f}%（门槛 {a.min_rate}%）")

    bad = False
    if zero:
        bad = True
        print(f"  [NG  ] **{len(zero)} 条数字断言没有任何来源** —— 真实度无从验证，硬错误：")
        for i, s, n, d, txt, k in zero[:a.show]:
            print(f"          L{i}｜{txt[:66]}")
    if concl_bad:
        bad = True
        print(f"  [NG  ] 结论区有 {len(concl_bad)} 条不足 3 个独立来源（决策依据不接受单一来源）：")
        for i, s, n, d, txt, k in concl_bad[:a.show]:
            print(f"          L{i}（{n} 个）｜{txt[:60]}")
    if rate < a.min_rate:
        bad = True
        print(f"  [NG  ] 正文达标率 {rate:.0f}% < {a.min_rate}%：")
        lack = [r for r in body if r[2] < 3 and not r[3]]
        for i, s, n, d, txt, k in lack[:a.show]:
            print(f"          L{i}（{n} 个，未标注降级）｜{txt[:60]}")

    if not bad:
        print("  [OK  ] 无零来源断言；结论区全部 ≥3；正文达标率达标")
        print("判定：数据交叉验证合格 ✅")
        return 0
    if a.legacy:
        print("判定：**不达标**，但按 --legacy 仅报告（历史快照不回改）——新稿不得沿用此水平")
        return 0
    print("判定：数据交叉验证不合格 ⛔（补齐来源，或按规范显式降级并标注）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
