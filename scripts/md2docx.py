#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md2docx.py — 把 Markdown 报告转为符合交付模板的 .docx（第 6 步最后一段）

为什么有这个脚本：SKILL 第 6 步要求「转 Word 并做 OOXML 加固」，但此前没有配套工具，
每次都靠临场手搓 —— 于是出现两类真实事故：
  ① 手设字体字号，破坏 `references/18` 的格式一致性；
  ② 图形引用扩展名与匹配正则不一致（md 写 .png、脚本只认 .svg），
     **产物里 0 张图，而脚本返回成功、不报错** —— 交付后才被用户发现。

本脚本的对策：
  · 以 `assets/交付模板.docx` 为底稿，只指定样式名（Heading 1/2/3/4 · Normal · Caption）
  · OOXML 结构加固：表格 `tblHeader` + `cantSplit`；图片段落独立 + `keepLines`
  · **转换后强制自检**：统计内嵌图片数 + 解包确认 `word/media/` 里是真图片（非空壳），
    数量对不上就 **exit 1 并打印原因**，不允许静默成功
  · 登记「源稿 sha256 → 产出 sha256」

用法:
  python md2docx.py 报告.md 报告.docx [--charts-dir charts] [--template assets/交付模板.docx]
  python md2docx.py 报告.docx --verify-only      # 只做产物自检
"""
import argparse
import hashlib
import os
import re
import sys
import zipfile

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(os.path.dirname(HERE), "assets", "交付模板.docx")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".emf")


# ── 产物自检：图片真的进去了吗 ────────────────────────────────
def verify_docx(path, expect_images=None):
    """返回 (ok, 报告字符串)。ok=False 时调用方应 exit 1。"""
    if not os.path.exists(path):
        return False, f"产物不存在：{path}"
    d = Document(path)
    n_inline = len(re.findall(r"<a:blip", d.element.body.xml))
    n_graphic = sum(1 for _ in d.element.body.iter() if str(_.tag).endswith("}graphicData"))
    media = []
    try:
        with zipfile.ZipFile(path) as z:
            media = [(n, z.getinfo(n).file_size)
                     for n in z.namelist() if n.startswith("word/media/")]
    except zipfile.BadZipFile:
        return False, "产物不是合法 zip（.docx 损坏）"

    lines = [
        f"  段落 {len(d.paragraphs)} ｜ 表格 {len(d.tables)} ｜ 内嵌图形 {max(n_inline, n_graphic)}"
    ]
    if media:
        for n, sz in media:
            lines.append(f"  media {os.path.basename(n)} = {sz} bytes")
    bad = [n for n, sz in media if sz < 1024]
    ok = True
    if expect_images is not None:
        if len(media) != expect_images:
            ok = False
            lines.append(f"  ⛔ 图形数量不符：期望 {expect_images} 张，实际 {len(media)} 张")
    if bad:
        ok = False
        lines.append(f"  ⛔ 疑似空壳图片（<1KB）：{bad}")
    lines.append("  ✅ 图片自检通过" if ok else "  ⛔ 图片自检未通过")
    return ok, "\n".join(lines)


# ── 样式安全的写法（只给样式名，不手搓字体字号）──────────────
def add_runs(par, text):
    """解析 **加粗**，不加字体字号——交给样式"""
    for i, seg in enumerate(re.split(r"\*\*", text)):
        if not seg:
            continue
        r = par.add_run(seg)
        if i % 2 == 1:
            r.bold = True
    return par


def harden_table(tbl):
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    for ri, row in enumerate(tbl.rows):
        trPr = row._tr.get_or_add_trPr()
        if ri == 0:
            trPr.append(OxmlElement("w:tblHeader"))
        trPr.append(OxmlElement("w:cantSplit"))


def add_image(doc, path, caption=None):
    p = doc.add_paragraph(style="Normal")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Pt(400))
    pPr = p._p.get_or_add_pPr()
    pPr.insert(0, OxmlElement("w:keepLines"))
    if caption:
        c = doc.add_paragraph(style="Caption")
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        c.add_run(caption)
    return p


def convert(md_path, out_path, charts_dir, template, expect_images=None):
    if not os.path.exists(template):
        print(f"⛔ 找不到交付模板：{template}", file=sys.stderr)
        return 1
    doc = Document(template)
    for p in list(doc.paragraphs):           # 清掉模板里的占位空段
        p._element.getparent().remove(p._element)

    lines = open(md_path, encoding="utf-8").read().splitlines()
    i, n_img_declared = 0, 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue

        if s.startswith("```"):              # 代码块 → Normal，不手设字体
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            p = doc.add_paragraph(style="Normal")
            p.add_run("\n".join(buf))
            continue

        if s == "---":
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            lvl = min(len(m.group(1)), 4)
            h = doc.add_heading("", level=lvl)
            add_runs(h, m.group(2))
            i += 1
            continue

        if s.startswith("|"):                # 表格块
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                ncols = max(len(r) for r in rows)
                tbl = doc.add_table(rows=len(rows), cols=ncols)
                tbl.style = "Normal Table"
                for ri, row in enumerate(rows):
                    for ci in range(ncols):
                        cell = tbl.cell(ri, ci)
                        cell.text = ""
                        par = cell.paragraphs[0]
                        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        add_runs(par, row[ci] if ci < len(row) else "")
                        for r in par.runs:   # 表格 10pt 居中（references/18 明列项）
                            r.font.size = Pt(10)
                            r.font.name = "宋体"
                            r._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
                harden_table(tbl)
            continue

        m = re.match(r"^[-*]\s+(.*)$", s)
        if m:
            p = doc.add_paragraph(style="Normal")
            add_runs(p, "· " + m.group(1))
            cm = re.search(r"charts/(chart[\w\-]*?)\.(?:png|svg|jpg|jpeg)", m.group(1))
            if cm:                            # 图形引用 → 插对应位图
                n_img_declared += 1
                for ext in IMG_EXT:
                    cand = os.path.join(charts_dir or "", cm.group(1) + ext)
                    if os.path.exists(cand):
                        add_image(doc, cand)
                        break
                else:
                    print(f"  ⚠️ 声明了图形但找不到文件：{cm.group(1)}.*（在 {charts_dir}）")
            i += 1
            continue

        m = re.match(r"^(\d+)\.\s+(.*)$", s)
        if m:
            add_runs(doc.add_paragraph(style="Normal"), m.group(1) + ". " + m.group(2))
            i += 1
            continue

        add_runs(doc.add_paragraph(style="Normal"), s)
        i += 1

    doc.save(out_path)

    expect = n_img_declared if expect_images is None else expect_images
    ok, rep = verify_docx(out_path, expect_images=expect if expect else None)
    print(f"已生成：{out_path}")
    print(rep)

    src_hash = hashlib.sha256(open(md_path, "rb").read()).hexdigest()
    dst_hash = hashlib.sha256(open(out_path, "rb").read()).hexdigest()
    reg = os.path.join(os.path.dirname(out_path), "交付哈希登记.txt")
    with open(reg, "w", encoding="utf-8") as f:
        f.write("交付哈希登记\n" + "=" * 60 + "\n")
        f.write(f"源稿  {os.path.basename(md_path)}\n  sha256 = {src_hash}\n")
        f.write(f"产出  {os.path.basename(out_path)}\n  sha256 = {dst_hash}\n")
        f.write("=" * 60 + "\n"
                "说明：源稿冻结后再转换；此后源稿只读，若再改动须重跑全套审计并作废旧哈希。\n")
    print(f"源稿 sha256 = {src_hash}\n产出 sha256 = {dst_hash}")
    if not ok:
        print("⛔ 产物自检未通过 —— 不要交付，先修上面的问题", file=sys.stderr)
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--charts-dir", default=None)
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    ap.add_argument("--expect-images", type=int, default=None)
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()

    if a.verify_only:
        ok, rep = verify_docx(a.md, expect_images=a.expect_images)
        print(rep)
        return 0 if ok else 1
    if not a.out:
        ap.error("需要 md 与 out 两个路径（或 --verify-only）")
    charts = a.charts_dir or os.path.join(os.path.dirname(os.path.abspath(a.md)), "charts")
    return convert(a.md, a.out, charts, a.template, a.expect_images)


if __name__ == "__main__":
    sys.exit(main())
