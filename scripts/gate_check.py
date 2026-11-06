#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁校验 · gate_check.py（marketing-analysis）

用途：问完门禁后、动笔写报告前跑一次。

  ⛔ 第 −0 关「内容主体」缺失或不是对照句 → **exit 1（硬拦）**
  ⚠️ 9 项门禁缺失 → **不拦**，但会逐项列出「将使用默认值」，让用户在动笔前知情
     （与 playbook 的区别：playbook 写方案，15 项每项都必须拿到；analysis 做分析，
      多数项有合理默认值，硬拦会让流程卡死）

与 marketing-playbook/scripts/gate_check.py 同构、不同项数，两边可对照维护。

用法：
    python gate_check.py rules.json
    cat rules.json | python gate_check.py -

输入 JSON（JSON 不支持行内注释，实际填写时删掉 `_注` 这类说明键）：
{
  "client": "客户名",
  "内容主体": "是【A 的 x】，不是【B 的 y】",
  "gate": { "分析哪家": "...", "报告体裁": "...", "怎么算成功": "..." },
  "rules_table_confirmed": true
}

退出码：0 通过 ｜ 1 不通过 ｜ 2 脚本错误
"""

import json
import re
import sys

# 9 项门禁：(标签, 别名, 默认值 or None=必答)
GATE_ITEMS = [
    ("分析哪家（业务范围与主要市场）",
     ["分析哪家", "公司", "标的", "对象", "业务范围"], None),
    ("报告体裁",
     ["体裁", "报告类型", "分析类型"], "全量分析"),
    ("用途与读者",
     ["用途", "读者", "受众"], "课程作业"),
    ("目标字数、页数上限",
     ["字数", "页数", "长度", "篇幅"], "6,000–10,000 字"),
    ("侧重",
     ["侧重", "重点", "偏向"], "均衡"),
    ("AIGC 加分项",
     ["AIGC", "加分项", "物料", "图表"], "要"),
    ("交付语言",
     ["语言", "简繁", "交付语言"], "简体"),
    ("外部引用文件",
     ["外部引用", "引用文件", "被引", "底稿", "上版"], "无"),
    ("怎么算成功（验收标准）",
     ["怎么算成功", "验收", "成功标准", "合格标准"], "按体裁默认"),
]

N_ITEMS = len(GATE_ITEMS)

OK, NG, OPT = "✅", "❌", "⚠️"


def load(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def filled(v):
    if v is None:
        return False
    s = str(v).strip()
    return bool(s) and s.lower() not in {
        "todo", "tbd", "待补", "待定", "待确认", "未知", "不清楚", "不确定",
        "暂无", "未定", "未确认", "n/a", "na", "?", "？", "查不到", "", "-", "null",
    }


def match(gate, aliases):
    """最长别名优先，避免「分析哪家」被短别名「对象」抢走。"""
    best_k, best_v, best_len = None, None, -1
    for k, v in gate.items():
        kl = str(k).lower()
        for a in aliases:
            al = str(a).lower()
            if al and al in kl and len(al) > best_len:
                best_k, best_v, best_len = k, v, len(al)
    return best_k, best_v


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if "--help" in sys.argv or "-h" in sys.argv else 1)

    try:
        data = load(sys.argv[1])
    except Exception as e:
        print(f"{NG} 无法读取输入：{e}")
        sys.exit(1)

    client = data.get("client") or data.get("客户") or "(未填客户名)"
    gate = data.get("gate") or {}
    confirmed = bool(data.get("rules_table_confirmed") or data.get("规则表已确认"))

    print("=" * 64)
    print(f"门禁校验 · 营销分析 · {client}")
    print("=" * 64)

    # ── 第 −0 关：内容主体 ──────────────────────────────────
    raw = (data.get("内容主体") or data.get("subject")
           or data.get("content_subject") or data.get("内容主体对照"))
    subject_ok = False
    if not raw:
        print(f"{NG} 内容主体   ← 缺失（第 −0 关，先于 {N_ITEMS} 项）")
        print('   写法："内容主体": "是【这家公司自己的营销打法拆解】，不是【行业综述】"')
    else:
        s = str(raw).strip()
        # ⚠️ `"是" in "不是…"` 恒为真 —— 必须用负向先行断言排除「不是」里的「是」
        has_pos = bool(re.search(r"(?<!不)是", s)) or ("＝" in s) or ("=" in s)
        has_neg = any(t in s for t in ("不是", "而非", "而不是", "≠"))
        if not (has_pos and has_neg):
            print(f"{NG} 内容主体   ← 不是对照句：「{s[:50]}」")
            print("   → 必须同时写正面和反面：「是【A 的 x】，不是【B 的 y】」。只写一面 = 没定边界。")
        else:
            print(f"{OK} 内容主体\n     {s if len(s) <= 46 else s[:46] + '…'}")
            subject_ok = True

    # ── 9 项门禁 ─────────────────────────────────────────
    print("-" * 64)
    hard_missing, using_default = [], []
    for label, aliases, default in GATE_ITEMS:
        k, v = match(gate, aliases)
        if filled(v):
            short = str(v).strip().replace("\n", " ")
            print(f"{OK} {label}\n     {short[:46]}{'…' if len(short) > 46 else ''}")
        elif default is None:
            print(f"{NG} {label}   ← 必答，缺失")
            hard_missing.append(label)
        else:
            print(f"{OPT} {label}   ← 未填，将用默认「{default}」")
            using_default.append((label, default))

    # ── 结论 ────────────────────────────────────────────
    print("-" * 64)
    if using_default:
        print(f"{OPT} {len(using_default)} 项将使用默认值 —— 动笔前请确认这些默认可接受：")
        for label, d in using_default:
            print(f"   · {label} → {d}")

    print(f"规则表确认状态：{'已确认 ' + OK if confirmed else '尚未确认 ' + NG}")

    print("-" * 64)
    if hard_missing or not subject_ok:
        print(f"{NG} 门禁不通过，禁止产出正文：")
        if not subject_ok:
            print("   · 内容主体（第 −0 关）")
        for m in hard_missing:
            print(f"   · {m}")
        sys.exit(1)

    if not confirmed:
        print(f"{NG} 门禁已问全，但《任务规则表》尚未经用户确认。")
        sys.exit(1)

    print(f"{OK} 门禁通过：第 −0 关内容主体已定 ＋ {N_ITEMS} 项齐全（{len(using_default)} 项取默认）＋ 规则表已确认。")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{NG} 已中断。")
        sys.exit(130)
    except Exception as e:
        print(f"\n{NG} 脚本出错：{type(e).__name__}: {e}")
        sys.exit(2)
