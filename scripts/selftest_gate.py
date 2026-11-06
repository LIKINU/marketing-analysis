#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest_gate.py · 门禁判据的自检（marketing-analysis）

四组样本在内存里现造，**不依赖任何成品文件** —— 防止「样本跟着被测物漂移，
反例不再是反例」（2026-11-01 在 playbook 侧踩过：给范例补了字段后，缺字段那组当场失效）。

用法：python scripts/selftest_gate.py
退出码：0 全绿 ｜ 1 有断言失败
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "gate_check.py")

BASE = {
    "client": "自检样本",
    "gate": {"分析哪家": "某新消费茶饮品牌，直营 3 店", "报告体裁": "全量分析"},
    "rules_table_confirmed": True,
}

CASES = [
    ("缺内容主体字段", {**BASE}, 1),
    ("只写正面（无对照）", {**BASE, "内容主体": "这家公司的营销打法"}, 1),
    ("只写反面（无正面）", {**BASE, "内容主体": "不是【行业综述】"}, 1),
    ("正确对照句", {**BASE, "内容主体": "是【这家公司自己的打法拆解】，不是【行业综述】"}, 0),
]


def main():
    fails = 0
    with tempfile.TemporaryDirectory() as td:
        for name, data, expect in CASES:
            p = os.path.join(td, "case.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            r = subprocess.run([sys.executable, GATE, p], capture_output=True, text=True)
            ok = (r.returncode == expect)
            print(f"{'✅' if ok else '❌'} {name}：exit={r.returncode}（期望 {expect}）")
            if not ok:
                fails += 1
                for line in (r.stdout or r.stderr).strip().splitlines()[-4:]:
                    print("   " + line)

    print("-" * 50)
    if fails:
        print(f"❌ {fails}/{len(CASES)} 组断言失败 —— 门禁判据不能信")
        return 1
    print(f"✅ {len(CASES)}/{len(CASES)} 组全绿")
    return 0


if __name__ == "__main__":
    sys.exit(main())
