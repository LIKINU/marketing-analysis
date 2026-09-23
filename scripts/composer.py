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
> 体裁：**{tier}** ｜ **深度档：{depth}**（{dnote}） ｜ {stamp} ｜ 章 {n_ch} 个 ／ 小点 {n_sub} 个
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


def render(tier, with_guide=False, depth="标准", stamp=True):
    secs = sections_for(tier)
    n_sub = sum(len(subs_for(s, tier, depth)) for s, _, _, _ in secs)
    # ⚠️ 入库骨架必须用**可复现的命令**代替时间戳 —— 否则 `--check-skeletons` 永远判过期
    #    （曾经踩过：时间戳每次都不同，判据成了"永远不通过"，属于假判据家族）
    stamp = (f"生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}" if stamp
             else f"复现：`python scripts/composer.py --tier {tier} --depth {depth}`")
    buf = [HEADER.format(tier=tier, depth=depth, dnote=SD.DEPTH.get(depth, {}).get("note", ""),
                         stamp=stamp, n_ch=len(secs), n_sub=n_sub), ""]
    # 目录（两级：章 → 小点）—— 对应交付模板的「WPSOffice手动目录 1 / 2」样式
    # ⚠️ 目录里的标题是**结构主题词**；成稿的标题必须是结论句，故出稿前用 `--toc` 重生成
    buf.append(render_toc(tier, depth))
    buf.append("<!-- ↑ 目录：成稿后标题会变成结论句，出稿前用 `composer.py --toc 报告.md` 重生成目录 -->")
    buf.append("")
    NT = numbered_titles(tier)
    for sid, title, lvl, cond in secs:
        g = SD.GUIDE.get(sid, {})
        if cond:
            buf.append(f"<!-- 条件节（{cond}）：符合才写；不符合请在此说明为何不写 -->")
        buf.append(f"{'#' * (lvl + 1)} {NT[sid]}")
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


# ── 现成骨架：给「无代码平台」（豆包/ChatGPT 等）直接复制粘贴用 ──────
# 为什么入库：SKILL 里写着「跑 composer.py 生成骨架」，但豆包没有代码执行能力
#   → 它拿不到结构 → 只能自己编 → 产出很浅。骨架必须是**可复制的成品**。
def _skeleton_name(tier_slug, depth):
    return f"骨架-{tier_slug}-{depth}.md"


def build_skeletons(outdir):
    os.makedirs(outdir, exist_ok=True)
    made = []
    for tier_slug, tier in SD.TIERS.items():
        for depth in SD.DEPTH:
            doc = render(tier, False, depth, stamp=False)
            path = os.path.join(outdir, _skeleton_name(tier_slug, depth))
            io.open(path, "w", encoding="utf-8").write(doc)
            made.append((path, len(doc)))
    # 单文件粘贴包（无代码平台首选）
    p = paste_pack_path(outdir)
    made.append((p, build_paste_pack(p)))
    return made


def check_skeletons(outdir):
    """与现算结果逐份比对；不一致 = 已过期（改了骨架忘了重新生成）→ exit 1"""
    bad, missing = [], []
    for tier_slug, tier in SD.TIERS.items():
        for depth in SD.DEPTH:
            path = os.path.join(outdir, _skeleton_name(tier_slug, depth))
            if not os.path.exists(path):
                missing.append(os.path.basename(path))
                continue
            cur = io.open(path, encoding="utf-8").read()
            if cur != render(tier, False, depth, stamp=False):
                bad.append(os.path.basename(path))
    # 粘贴包也核对
    pp = paste_pack_path(outdir)
    if not os.path.exists(pp):
        missing.append(os.path.basename(pp))
    else:
        import tempfile
        tmp = os.path.join(tempfile.mkdtemp(), "pp.md")
        build_paste_pack(tmp)
        if io.open(pp, encoding="utf-8").read() != io.open(tmp, encoding="utf-8").read():
            bad.append(os.path.basename(pp))
    n = len(SD.TIERS) * len(SD.DEPTH) + 1
    print(f"【现成骨架核对】{outdir}｜应有 {n} 份（9 骨架 + 1 粘贴包）")
    if missing:
        for x in missing:
            print(f"  [NG  ] 缺失：{x}")
    if bad:
        for x in bad:
            print(f"  [NG  ] 已过期：{x}（跑 --build-skeletons 重新生成）")
    if missing or bad:
        print("判定：现成骨架不齐或过期（无代码平台会拿到旧结构）")
        return 1
    print("  [OK  ] 9 份齐全且与 composer 现算结果一致")
    print("判定：现成骨架可用 ✅")
    return 0


# ── 无代码粘贴包：**单文件**（骨架 ＋ 规则），豆包/ChatGPT 一次粘贴即可 ──
def build_paste_pack(path, tier="全量分析", depth="标准"):
    """把「规则段（门禁/工作流/纪律）」和「骨架」合成一份，供无代码平台一次性粘贴。

    为什么需要它：无代码平台不能跑脚本、也不方便分两次粘贴（容易截断/漏贴第二段），
    于是只贴 SKILL 得到很浅的产出。**一份文件把"规矩 + 结构"都给全**才是正解。
    """
    skill = io.open(os.path.join(os.path.dirname(HERE), "SKILL.md"), encoding="utf-8").read()
    keep, grab = [], None
    for ln in skill.splitlines():
        if ln.startswith("## "):
            grab = ("门禁" in ln) or ("工作流" in ln) or (ln.strip() == "## 纪律")
            if grab:
                keep.append("")
                keep.append(ln)
            continue
        if grab:
            keep.append(ln)
    rules = "\n".join(keep).strip()
    doc = f"""# 无代码平台粘贴包（豆包 / ChatGPT / 其他对话式 AI）

> **怎么用**：把本文件**全文粘贴**给 AI，然后补一句：
> 「请按上面骨架的**每一个小点**逐条填写；每个小点的『必含 / 句式 / 查 / 反例』四件套都要满足，
> 每个小点写足字数下限。**缺一章、缺一个小点都算不合格。**」
>
> ⚠️ 这个包是 `composer.py --build-skeletons` 生成的。**不要手改**——改了结构就跑偏了。

---

# 第一部分 · 规则（门禁 / 工作流 / 纪律）

{rules}

---

# 第二部分 · 骨架（{tier} · {depth} 档）

{render(tier, False, depth, stamp=False)}
"""
    io.open(path, "w", encoding="utf-8").write(doc)
    return len(doc)


def paste_pack_path(outdir):
    return os.path.join(outdir, "无代码粘贴包-全量分析-标准.md")


# ── 章号：**按顺序自动生成**（不再手写「三、」「四、」）────────────────
# 执行摘要 / 图表清单 / 附录 是"外壳"，不编号；其余正文章节按出现顺序给中文数字。
_CN = "一二三四五六七八九十"


def cn_num(n):
    """1→一 … 10→十，11→十一，20→二十"""
    if n <= 10:
        return _CN[n - 1]
    if n < 20:
        return "十" + _CN[n - 11]
    return _CN[n // 10 - 1] + "十" + (_CN[n % 10 - 1] if n % 10 else "")


UNNUMBERED = {"summary", "charts", "appendix"}


def numbered_titles(tier):
    """返回 {sid: 带章号的标题}"""
    out, i = {}, 0
    for sid, title, lvl, cond in sections_for(tier):
        if sid in UNNUMBERED:
            out[sid] = title
        else:
            i += 1
            out[sid] = f"{cn_num(i)}、{title}"
    return out


def _toc_title(text):
    """目录里用**主题词**：切掉结论部分与 <占位符>，并去掉悬空尾巴。

    ⚠️ 三种切法要叠加，否则会出现「同行已公开的案例集中在 ，而非」这种残缺条目：
       ① 有「：」→ 取冒号前
       ② 无「：」→ 再按 逗号/括号 切
       ③ 去 <占位符> 后，清掉「集中在 / 而非 / 与」这类悬空连接词
    """
    x = re.split(r"[：:]", text)[0]
    if x == text:                                   # ② 没冒号 → 按逗号/括号切
        x = re.split(r"[，（(]", x)[0]
    x = re.sub(r"<[^>]*>", "", x)
    x = re.sub(r"(集中在|而非|以及|与|并)\s*$", "", x.strip("　 ｜·，、"))
    return x or text[:16]


def render_toc(tier, depth="标准"):
    """骨架里的结构目录（两级：章 → 小点）"""
    lines = ["## 目录", ""]
    NT = numbered_titles(tier)
    for sid, title, lvl, cond in sections_for(tier):
        lines.append(f"- {NT[sid]}" + ("　<!-- 条件节 -->" if cond else ""))
        for s in subs_for(sid, tier, depth):
            lines.append(f"  - {_toc_title(s['t'])}")
    lines.append("")
    return "\n".join(lines)


def toc_from_report(path):
    """从**成稿的实际标题**重生成目录（标题是结论句，只有成稿后才知道）"""
    md = io.open(path, encoding="utf-8").read()
    out = ["## 目录", ""]
    in_toc = False
    for ln in md.splitlines():
        m2 = re.match(r"^##\s+(.+?)\s*$", ln)
        m3 = re.match(r"^###\s+(.+?)\s*$", ln)
        if m2:
            name = m2.group(1)
            if name.strip() in ("目录",):
                in_toc = True
                continue
            in_toc = False
            out.append(f"- {name}")
        elif m3 and not in_toc:
            out.append(f"  - {re.sub(r'^\d+(?:\.\d+)*[\.\s、]*', '', m3.group(1))}")
    out.append("")
    return "\n".join(out)


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


def check(path, min_chars, allow_missing=()):
    """allow_missing：显式豁免的章节 sid（用于**历史快照**——新增章节后，旧稿必然缺，
    但它是真实交付快照、不该回改）。豁免项会计入 WARN，不算硬判。"""

    md = io.open(path, encoding="utf-8").read()
    chaps = _split(md, 2)
    missing, thin, warn = [], [], []

    for sid, title, lvl, cond, tags in SD.SECTIONS:
        if cond:
            continue
        if sid in allow_missing:
            warn.append(f"{title}：已显式豁免（历史快照，新增章节后必然缺）")
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
    # 目录：金标准稿本身没有目录 → **只提示不判死**（硬判会误杀）
    if not re.search(r"^#{1,3}\s*目录", md, re.M):
        warn.append("缺目录（骨架已含「目录」，成稿后跑 `composer.py --toc 报告.md` 重生成）")
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
    ap.add_argument("--toc", metavar="报告.md", help="从成稿的实际标题重生成目录（输出到 stdout）")
    ap.add_argument("--spec-audit", metavar="TIER", nargs="?", const="全量分析",
                    help="核对每个小点是否都带「必含/句式/查/反例」四件套（缺即 exit 1）")
    ap.add_argument("--min-chars", type=int, default=SD.MIN_SUB_CHARS)
    ap.add_argument("--build-skeletons", metavar="DIR",
                    help="生成现成骨架（3 体裁 × 3 深度 = 9 份）到目录，供无代码平台复制粘贴")
    ap.add_argument("--check-skeletons", metavar="DIR",
                    help="核对现成骨架是否齐全且未过期（过期 exit 1）")
    ap.add_argument("--allow-missing", default="",
                    help="显式豁免的章节 sid（逗号分隔，用于历史快照）")
    a = ap.parse_args()

    if a.build_skeletons:
        made = build_skeletons(a.build_skeletons)
        for p, n in made:
            print(f"  已生成 {os.path.basename(p)}（{n:,} 字符）")
        print(f"共 {len(made)} 份 → 无代码平台（豆包/ChatGPT 等）直接复制粘贴使用")
        return 0
    if a.check_skeletons:
        return check_skeletons(a.check_skeletons)
    if a.toc:
        print(toc_from_report(a.toc))
        return 0
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
        allow = tuple(x.strip() for x in a.allow_missing.split(",") if x.strip())
        return check(a.check, a.min_chars, allow)
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
