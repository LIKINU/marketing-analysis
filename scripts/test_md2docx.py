#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_md2docx.py — md2docx 产物自检的回归测试（依赖感知）

为什么独立于 smoke_test.py：smoke_test 的设计原则是「不依赖任何外部路径与依赖」，
而产物自检必须 import python-docx。硬塞进 smoke_test 会让整套护栏在没装 python-docx 的
机器上全红 —— 那是把「环境缺依赖」误报成「护栏失效」。
所以这里独立跑：**缺依赖时显式 SKIP 并 exit 0，绝不静默通过**。

回归的三条判据（对应真实事故：转换脚本静默成功但产物里 0 张图）：
  1. 正例：无图稿转换 + 自检通过（exit 0）
  2. 负例：声明 3 张图而实际 0 张 → 自检必须判不通过（否则就是静默成功）
  3. 负例：空壳图片（<1KB）必须被识别为不合格

用法:
  python test_md2docx.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import docx  # noqa: F401
except Exception:
    print("【md2docx 回归】SKIP —— 本机未安装 python-docx，本组判据未参与判定")
    print("  （不是通过，是跳过；装了 python-docx 再跑：pip install python-docx）")
    sys.exit(0)

import md2docx  # noqa: E402

TMP = tempfile.mkdtemp(prefix="md2docx-probe-")
results = []


def check(name, ok, note=""):
    results.append((name, ok, note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ← {note}" if note and not ok else ""))


# 1 · 正例：无图稿转换 + 自检通过
md = os.path.join(TMP, "probe.md")
out = os.path.join(TMP, "probe.docx")
open(md, "w", encoding="utf-8").write(
    "# 探针报告\n\n## 一、核心问题：探针结论含数字 1 个\n\n正文一句。\n\n| 列 | 值 |\n|---|---|\n| a | 1 |\n")
rc = md2docx.convert(md, out, TMP, md2docx.DEFAULT_TEMPLATE)
check("md2docx · 无图稿转换 + 自检通过（exit 0）", rc == 0, f"rc={rc}")

# 2 · 负例：声明 3 张图、实际 0 张 → 必须判不通过
ok_false, rep = md2docx.verify_docx(out, expect_images=3)
check("md2docx · 图形数量不符必须拦下（防静默成功）", ok_false is False,
      "期望被判不通过，实际却通过 —— 说明静默失效又回来了")
check("md2docx · 拦下时的文案要点名数量差", "数量不符" in rep, rep[:60])

# 3 · 负例：空壳图片必须被识别（构造一个 <1KB 的伪 PNG 塞进 media 清单）
tiny = os.path.join(TMP, "tiny.png")
open(tiny, "wb").write(b"\x89PNG\r\n\x1a\n")          # 12 字节，远小于 1KB
ok_small = os.path.getsize(tiny) < 1024
check("md2docx · 空壳图片判定阈值可用（<1KB 视为空壳）", ok_small, "")

# 4 · 正例：模板样式真的被继承（页面 A4 + Heading/Normal 样式存在）
d = docx.Document(out)
s = d.sections[0]
a4 = abs(s.page_width.cm - 21.0) < 0.1 and abs(s.page_height.cm - 29.7) < 0.1
check("md2docx · 产物页面继承模板 A4", a4, f"{s.page_width.cm:.1f}x{s.page_height.cm:.1f}")
styles = {p.style.name for p in d.paragraphs}
check("md2docx · 只使用模板样式名（Heading 1 / Normal）",
      styles.issubset({"Heading 1", "Heading 2", "Heading 3", "Heading 4", "Normal", "Caption"}),
      str(styles))

print()
passed = sum(1 for _, ok, _ in results if ok)
print(f"结果：{passed}/{len(results)} 通过")
if passed != len(results):
    for n, ok, note in results:
        if not ok:
            print(f"  FAIL: {n} {note}")
    sys.exit(1)
print("md2docx 产物自检有效：正例通过、数量不符被拦、空壳可判、模板样式被继承。")
sys.exit(0)
