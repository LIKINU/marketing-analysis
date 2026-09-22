#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""composer.py — 报告骨架组装器（Analysis 的「真·强制」引擎）

为什么有它（沿用 playbook 的定调）：
    「模型根本做不了强制使用，它只做到读取，相当于 prompt / RAG，不是 skill。」
→ 结构与要求由**脚本机械注入**，不靠模型自愿遵守。

**两级骨架**：
    章（##）→ 小点（###）。每个小点单独给「必含要素 + 字数下限」，
    `--check` 会**分别拦两种病**：① 缺章 ② **小节内容过薄**（低于下限）。

骨架唯一真相在本文件（SECTIONS 顺序/条件节/渲染）＋ `skeleton_data.py`（GUIDE 章级 / SUB 小点级 / MATCH 关键词）。

用法：
    python composer.py --out 骨架.md                                # 默认「全量分析」
    python composer.py --out 骨架.md --tier 对标研究                  # 全量分析|对标研究|尽调式拆解
    python composer.py --out 骨架.md --with-guide                   # 连关键句片段写入（不写【填】）
    python composer.py --check 报告.md                              # 缺章 / 内容过薄 → exit 1
    python composer.py --check 报告.md --min-chars 150              # 自定义小点字数下限
退出码：0 正常；1 有缺章或内容过薄；2 执行错误
"""
import argparse
import datetime
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skeleton_data as SD  # noqa: E402

HEADER = """# {tier} · 报告骨架（由 `scripts/composer.py` 机械生成）

> **这是固定骨架，不要改结构。** 每节 / 每小点上方的小字是「该写什么」；`【填】` 处补内容。
> 体裁：**{tier}** ｜ **深度档：{depth}**（{dnote}） ｜ 生成时间：{now} ｜ 章 {n_ch} 个 ／ 小点 {n_sub} 个
> 知识库路由已按节注入 —— **按需查，不要通读**（每份参考档开头有自解释头）。
> ⚠️ **拆解类章节（二/三/四/五/六/八/九）是深度所在：每个小点都要写实，不要一段交差。**
"""


def sections_for(tier):
    return [(sid, title, lvl, cond) for sid, title, lvl, cond, tags in SD.SECTIONS if tier in tags]


def subs_for(sid, tier, depth="标准"):
    """按体裁与深度档取该章小点。深度档控制「保留几个 + 字数目标缩放」——直接决定生成时长。"""
    if sid in SD.TIER_SKIP_SUB.get(tier, set()):
        return []
    subs = [dict(x) for x in SD.SUB.get(sid, [])]
    d = SD.DEPTH.get(depth, SD.DEPTH["标准"])
    if d["keep"]:
        subs = subs[:d["keep"]]
    if d["scale"] != 1.0:
        for x in subs:
            x["mn"] = max(80, int(x["mn"] * d["scale"]))
    return subs


def render(tier, with_guide=False, depth="标准"):
    secs = sections_for(tier)
    n_sub = sum(len(subs_for(s, tier, depth)) for s, _, _, _ in secs)
    buf = [HEADER.format(tier=tier, depth=depth, dnote=SD.DEPTH.get(depth, {}).get("note", ""),
                         now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                         n_ch=len(secs), n_sub=n_sub), ""]
    for sid, title, lvl, cond in secs:
        g = SD.GUIDE.get(sid, {})
        if cond:
            buf.append(f"<!-- 条件节（{cond}）：符合才写；不符合请在此说明为何不写 -->")
        buf.append(f"{'#' * (lvl + 1)} {title}")
        buf.append("")
        req = []
        if g.get("must"):
            req.append("必含：" + "；".join(g["must"]))
        if g.get("size"):
            req.append("篇幅：" + g["size"])
        if req:
            buf.append("<!-- " + " ｜ ".join(req) + " -->")
        if g.get("refs"):
            buf.append("<!-- 查：" + " ；".join(g["refs"]) + " -->")
        if g.get("judge"):
            buf.append("<!-- 判据：" + g["judge"] + " -->")
        buf.append("")

        subs = subs_for(sid, tier, depth)
        if not subs:
            buf.append("".join(g["lines"][:1]) if (with_guide and g.get("lines")) else "【填】")
            buf.append("")
            continue
        for i, s in enumerate(subs, 1):
            buf.append(f"### {i}. {s['t']}")
            # 填空规格：把「怎么写」夹住，减少 agent 的自由发挥
            # 用 .get() 容错：字段缺失时渲染继续，由 --spec-audit 干净地判 NG
            # （若直接 s['x'] 会 KeyError 崩栈 —— 那也是"叫"，但看不出是哪个小点缺什么）
            buf.append(f"<!-- 必含：{s.get('need', '')} ｜ **字数 ≥ {s.get('mn', 0)}** -->")
            buf.append(f"<!-- 句式（照填，不要自创结构）：{s.get('lines', '')} -->")
            buf.append(f"<!-- 查：{s.get('refs', '')} ｜ 反例（不要写成）：{s.get('anti', '')} -->")
            _miss = [k for k in ("need", "lines", "refs", "anti") if not str(s.get(k, "")).strip()]
            if _miss:
                # ⚠️ 只查"标签在不在"是假判据（值空了也通过）→ 渲染时显式标出缺哪个字段
                buf.append(f"<!-- ⚠️ SPEC-MISSING: {','.join(_miss)} -->")
            buf.append("")
            buf.append(s["lines"] if with_guide else "【填】")
            buf.append("")
    return "\n".join(buf)


# ── 检查：① 缺章 ② 内容过薄 ──────────────────────────────────────────
def _split(md, level):
    """按 # 级别切块 → [(标题, 正文)]"""
    # ⚠️ 必须加 (?!\#) 负向断言：否则 `^##` 会把 `###` 也当成二级标题，
    #    导致二级章的正文被下一个三级标题截断成空 → 小点数永远数成 0
    pat = re.compile(rf"^{'#' * level}(?!\#)\s*(.+?)\s*$", re.M)
    marks = [(m.start(), m.end(), m.group(1)) for m in pat.finditer(md)]
    out = []
    for i, (s, e, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(md)
        out.append((title, md[e:end]))
    return out


def _body_chars(text):
    t = re.sub(r"<!--.*?-->", "", text, flags=re.S)          # 去掉要求注记
    t = re.sub(r"^#{1,6}\s*.*$", "", t, flags=re.M)           # 去掉小标题行
    t = re.sub(r"\s", "", t)
    return len(t)


def check(path, min_chars):
    md = io.open(path, encoding="utf-8").read()
    chaps = _split(md, 2)
    missing, thin, warn = [], [], []

    for sid, title, lvl, cond, tags in SD.SECTIONS:
        if cond:
            continue
        keys = SD.MATCH.get(sid, [title])
        hit = next((c for c in chaps if any(k and k in c[0] for k in keys)), None)
        if not hit:
            missing.append(f"{title}（识别关键词：{'/'.join(keys)}）")
            continue
        subs = SD.SUB.get(sid, [])
        if not subs:
            continue
        subs_in_doc = _split(hit[1], 3)
        if len(subs_in_doc) < len(subs):
            # ⚠️ 只提示，不判死：真实金标准稿里就有若干章是平铺的（如「AI 与传统运营对比」）
            warn.append(f"{title} 的小点偏少（期望 {len(subs)} 个，实 {len(subs_in_doc)} 个）——可再拆细以加深度")
        for st, body in subs_in_doc:
            n = _body_chars(body)
            if n < min_chars:
                thin.append(f"{title} → {st[:26]}（{n} 字 < {min_chars}）")

    n_ch = len([s for s in SD.SECTIONS if not s[3]])
    print(f"【骨架检查】{os.path.basename(path)}｜必备章 {n_ch}｜小点硬下限 {min_chars} 字")
    if missing:
        for m in missing:
            print(f"  [NG  ] {m}")
    if warn:
        for w in warn:
            print(f"  [WARN] {w}")
    if thin:
        print(f"  —— 内容过薄 {len(thin)} 处 ——")
        for x in thin[:12]:
            print(f"  [THIN] {x}")
        if len(thin) > 12:
            print(f"         …另有 {len(thin) - 12} 处")
    if missing or thin:
        print(f"判定：不合格（缺章 {len(missing)}｜内容过薄 {len(thin)}）—— 骨架是固定的，小点要写实")
        return 1
    print("  [OK  ] 章节齐备，且每个小点都达到字数下限")
    print("判定：结构完整 ✅")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--tier", default="全量分析", choices=list(SD.TIERS.keys()))
    ap.add_argument("--with-guide", action="store_true")
    ap.add_argument("--depth", default="标准", choices=list(SD.DEPTH.keys()),
                    help="深度档：快档=每章留 2 小点且目标×0.6｜标准｜深度=目标×1.25（直接决定生成时长）")
    ap.add_argument("--check")
    ap.add_argument("--spec-audit", metavar="TIER", nargs="?", const="全量分析",
                    help="核对每个小点是否都带「必含/句式/查/反例」四件套（缺即 exit 1）")
    ap.add_argument("--min-chars", type=int, default=SD.MIN_SUB_CHARS)
    a = ap.parse_args()

    if a.spec_audit:
        doc = render(a.spec_audit)
        blocks = re.findall(r'^### \d+\. (.+?)\n((?:<!--.*?-->\n?)*)', doc, re.M)
        bad = [b[0][:40] for b in blocks if "SPEC-MISSING" in b[1]]
        if not blocks:
            # ⚠️ 防空转：一个小点都没匹配到 = 判据根本没在工作（曾经因此假通过一次）
            print("  [NG  ] 判据空转：一个小点都没匹配到（正则或渲染坏了）")
            print("判定：判据失效，必须修（不是「没问题」）")
            return 1
        print(f'【填空规格核对】{a.spec_audit}｜小点 {len(blocks)} 个')
        if bad:
            for x in bad:
                print(f'  [NG  ] 缺规格：{x}')
            print('判定：有空白规格的小点（agent 会自由发挥）')
            return 1
        print('  [OK  ] 每个小点都带「必含 / 句式 / 查 / 反例」')
        # 基线比对：各章小点数不得低于下限（防"加厚这章＝削薄那章"）
        thin_ch = []
        for sid, base in SD.SUB_BASELINE.items():
            cur = len(subs_for(sid, a.spec_audit, "标准"))
            if sid == "bm":
                cur = len(SD.SUB.get("bm", []))      # 商业模式章按全量算，不受深度档影响
            elif cur == 0:
                cur = len(SD.SUB.get(sid, []))
            if cur < base:
                thin_ch.append(f"{sid}：{cur} < 基线 {base}")
        if thin_ch:
            print('  [NG  ] 低于小点基线（不许"加厚这章＝削薄那章"）：')
            for x in thin_ch:
                print(f'         {x}')
            print('判定：有章被削到基线以下')
            return 1
        print('  [OK  ] 各章小点数均不低于基线（商业模式章 4 小点未被削减）')
        print('判定：填空规格齐备 ✅')
        return 0
    if a.check:
        return check(a.check, a.min_chars)
    if not a.out:
        ap.error("需要 --out 或 --check")
    doc = render(a.tier, a.with_guide, a.depth)
    io.open(a.out, "w", encoding="utf-8").write(doc)
    n_ch = len(sections_for(a.tier))
    n_sub = sum(len(subs_for(s, a.tier, a.depth)) for s, _, _, _ in sections_for(a.tier))
    print(f"已生成骨架：{a.out}（体裁 {a.tier}｜深度 {a.depth}｜章 {n_ch}｜小点 {n_sub}｜{len(doc):,} 字符）")
    print("下一步：逐个小点写实；填完跑 `python scripts/composer.py --check 报告.md`。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
