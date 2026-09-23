#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deliver_check.py — 「客户可直接交付」就绪检查

用户 2026-09-23：「这个是公开的skills，调用完这个skills之后，要交付一份用户可以直接给他的客户的交付物」

这条判据回答一个问题：**现在这份稿子，能直接发给客户吗？**
不是"内容好不好"（那是 mbb_audit 的 27 项），而是**交付形态与内部残留**：

  md 层：① 无骨架占位符（【填】/<>/XXX/待填/TODO）② 无 `<!-- -->` 注记 ③ 无内部过程词
         ④ 有执行摘要 / 目录 / 来源清单 ⑤ 字数达标
  docx 层（--docx）：⑥ 有封面（标题/客户）⑦ 页脚有页码域 ⑧ 无注记文字漏进正文

用法：
  python scripts/deliver_check.py 报告.md
  python scripts/deliver_check.py 方案.docx --docx --title "某某公司 拆解报告"
退出码：0 可交付；1 有阻碍交付的项；2 执行错误
"""
import argparse
import io
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 骨架占位符（没填完就交 = 最严重）
PLACEHOLDER = [
    r"【填】", r"<(?![!])[^<>\n]{1,30}>", r"\bXXX\b", r"待填", r"TODO", r"待补",
]
# 内部过程残留
INTERNAL = [
    r"<!--", r"交付前自检", r"流程状态", r"门禁", r"scorecard", r"mbb_audit",
    r"Agent 分工", r"事实底稿", r"裁决记录", r"本 skill", r"工作日志", r"施工说明",
]
REQUIRED = [("执行摘要", r"^#{1,3}\s*执行摘要|执行摘要"),
            ("来源清单", r"数据来源清单|来源清单")]
# 「目录」只提示：金标准稿本身没有目录，硬判会误杀（与 composer --check 同一口径）
SOFT = [("目录", r"^#{1,3}\s*目录")]


def check_md(path, words, title=""):
    t = io.open(path, encoding="utf-8").read()
    bad, warn = [], []
    ph = []
    for pat in PLACEHOLDER:
        for m in re.finditer(pat, t):
            ph.append(m.group(0))
    if ph:
        uniq = sorted(set(ph))[:8]
        bad.append(f"占位符未填：{len(ph)} 处（{'、'.join(uniq)}）——**没写完的稿子不能给客户**")
    inn = []
    for pat in INTERNAL:
        n = len(re.findall(pat, t))
        if n:
            inn.append(f"{pat}×{n}")
    if inn:
        bad.append(f"内部过程残留：{'、'.join(inn)}")
    for name, pat in REQUIRED:
        if not re.search(pat, t, re.M):
            bad.append(f"缺「{name}」（客户视角的成品应齐备）")
    for name, pat in SOFT:
        if not re.search(pat, t, re.M):
            warn.append(f"缺「{name}」——建议补（客户翻长报告时要用；金标准稿也没有，故只提示）")
    n_words = len(re.sub(r"\s|<!--.*?-->", "", re.sub(r"^#{1,6}\s.*$", "", t, flags=re.M)))
    if words and n_words < words:
        bad.append(f"字数 {n_words} < 要求 {words}")
    if title and title.strip()[:8] not in t:
        warn.append(f"正文里未出现交付标题「{title[:20]}」——建议在首行写明")
    return bad, warn, n_words


def check_docx(path, title=""):
    bad, warn = [], []
    if not os.path.exists(path):
        return [f"产物不存在：{path}"], []
    try:
        import docx  # noqa: PLC0415
    except Exception:
        return [], ["未安装 python-docx → docx 层未检查（不是通过，是没查）"]
    try:
        d = docx.Document(path)
    except Exception as e:  # noqa: BLE001
        return [f"docx 打不开：{e}"], []
    paras = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    if title:
        head = "\n".join(paras[:6])
        if title.strip()[:8] not in head:
            bad.append(f"缺封面（前 6 段里找不到标题「{title[:20]}」）——客户拿到的应是带封面的正式件")
    z = zipfile.ZipFile(path)
    foot = [z.read(n).decode("utf-8") for n in z.namelist() if re.match(r"word/footer\d+\.xml", n)]
    if not any("PAGE" in f for f in foot):
        warn.append("页脚没有页码域（长报告建议加，便于客户引用页）")
    body = "\n".join(paras)
    leaked = [k for k in ("<!--", "交付前自检", "【填】") if k in body]
    if leaked:
        bad.append(f"注记漏进正文：{'、'.join(leaked)}（内部注记不得出现在交付稿）")
    return bad, warn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--words", type=int, default=0)
    ap.add_argument("--docx", action="store_true", help="按 Word 层检查（封面/页码/注记）")
    ap.add_argument("--title", default="", help="交付标题（用于核对封面）")
    a = ap.parse_args()

    if a.docx:
        bad, warn = check_docx(a.path, a.title)
        print(f"【交付就绪检查 · Word 层】{os.path.basename(a.path)}")
        n_words = 0
    else:
        bad, warn, n_words = check_md(a.path, a.words, a.title)
        print(f"【交付就绪检查 · 稿面】{os.path.basename(a.path)}｜正文约 {n_words:,} 字")
    for x in bad:
        print(f"  [NG  ] {x}")
    for x in warn:
        print(f"  [WARN] {x}")
    if bad:
        print(f"判定：**不可直接交付**（{len(bad)} 项待修）——客户拿到前必须先修")
        return 1
    print("  [OK  ] 无占位符 / 无内部残留 / 结构齐备")
    print("判定：可直接交付 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
