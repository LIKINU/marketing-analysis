#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_find.py — 知识库「查，不通读」入口

为什么有它（实测出来的成本）：知识库里的大文件单份就很大 ——
  `03-方法论操作手册.md` 15.6 万字符 ≈ 8.6 万 token；`12-范式库` 14.2 万。
**读一节也得把整份加载进上下文**，而这份上下文在之后每一轮都要重算（"越写越慢"的主因）。
本脚本把「查」变成一步：命中 → 给 `文件:行号` → 你再用 Read(offset,limit) 只读那一段。

用法：
  python scripts/kb_find.py "单位经济"                # 全库检索（默认每文件最多 3 条）
  python scripts/kb_find.py "单位经济" --context 2     # 每条带上下文行
  python scripts/kb_find.py "AARRR" --files           # 只列命中文件（先决定读哪份）
  python scripts/kb_find.py --sections references/03-方法论操作手册.md   # 该文件的节索引（含行号）
  python scripts/kb_find.py --sections --top 8        # 列最大的 8 份文件的节索引概览
退出码：0 有命中；1 无命中；2 参数错
"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SKIP_DIRS = {".git", "__pycache__"}


def iter_docs():
    for base in ("references",):
        for dp, dn, fn in os.walk(os.path.join(ROOT, base)):
            dn[:] = [d for d in dn if d not in SKIP_DIRS]
            for f in sorted(fn):
                if f.endswith((".md", ".json")):
                    yield os.path.join(dp, f), os.path.relpath(os.path.join(dp, f), ROOT)


def find(kw, per_file=3, ctx=0, files_only=False):
    pat = re.compile(re.escape(kw), re.I)
    hits, nfile = [], 0
    for path, rel in iter_docs():
        try:
            lines = io.open(path, encoding="utf-8").read().splitlines()
        except Exception:
            continue
        got = 0
        for i, ln in enumerate(lines, 1):
            if pat.search(ln):
                got += 1
                if got <= per_file:
                    hits.append((rel, i, ln.strip()[:150], lines[max(0, i - 1 - ctx):i + ctx]))
        if got:
            nfile += 1
            if files_only:
                print(f"  {rel}（{got} 处命中，{sum(1 for x in io.open(path, encoding='utf-8') if x):,} 行）")
    if files_only:
        return nfile
    for rel, i, ln, around in hits:
        print(f"  {rel}:{i}")
        print(f"      {ln}")
        if ctx:
            for a in around:
                print(f"      │ {a.strip()[:130]}")
    return len(hits)


def sections(path=None, top=0):
    docs = []
    for p, rel in iter_docs():
        try:
            n = os.path.getsize(p)
        except Exception:
            continue
        docs.append((n, p, rel))
    docs.sort(reverse=True)
    if path:
        docs = [(n, p, r) for n, p, r in docs if r.endswith(os.path.basename(path))]
    elif top:
        docs = docs[:top]
    else:
        docs = docs[:5]
    for n, p, rel in docs:
        lines = io.open(p, encoding="utf-8").read().splitlines()
        heads = [(i, l) for i, l in enumerate(lines, 1) if re.match(r"^#{2,3}\s+\S", l)]
        print(f"\n  ── {rel}（{n:,} 字节｜{len(lines):,} 行｜{len(heads)} 节）")
        for i, l in heads[:top if top else 40]:
            print(f"     {i:>6}  {re.sub(r'^#+\s*', '', l)[:66]}")
        if len(heads) > (top if top else 40):
            print(f"     …另有 {len(heads) - (top if top else 40)} 节")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword", nargs="?")
    ap.add_argument("--per-file", type=int, default=3)
    ap.add_argument("--context", type=int, default=0)
    ap.add_argument("--files", action="store_true", help="只列命中文件")
    ap.add_argument("--sections", nargs="?", const="", metavar="FILE",
                    help="列节索引（含行号）；不给文件则列最大的几份")
    ap.add_argument("--top", type=int, default=0, help="--sections 的条数上限")
    a = ap.parse_args()

    if a.sections is not None:
        return sections(a.sections or None, a.top)
    if not a.keyword:
        ap.error("需要关键词，或用 --sections")
    print(f"【知识库检索】「{a.keyword}」")
    n = find(a.keyword, a.per_file, a.context, a.files)
    if not n:
        print("  无命中——换个词，或先跑 --sections 看有哪些节")
        return 1
    print(f"\n  命中 {n} 处。**只读命中那几行**：Read(offset=行号-5, limit=20)，不要整份读。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
