#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mbb_audit.py — 交付前机械审计：对标 MBB / 4A 可判定标准的 25 项检查

v2 · 2026-09-19 红队评审后加固（堵住实测可绕过路径）：
  · 来源判据改为「可核验」（机构/《报告》/URL/可信度标记），自我指认「来源：见附录」不再算有来源
  · 中文数字（八千家/九万元/百分之二十）进分母
  · 标题硬门收紧（数字须带单位；去掉弱单字动词）
  · A2 改为去重计数且只统计议题树章节内；C1 取消「回落正文前 25 行」兜底
  · 新增占位符检测（量化目标写「从 A 提到 B」直接判不通过）
  · 硬错误误杀修复：内部泄漏词不再用裸词「门禁」

v3 · 2026-09-19 独立验证后重做 E6 语义（判据三态）：
  · E6 不再把「审计者的输入错误」算成「报告的红线」：
    ① 已验证·通过            → 计满分
    ② 已验证·幻影引用        → 报告的硬错误（打回）
    ③ 未验证（--dep 缺失/无效/与报告声明的被引文件对不上）
                             → **不扣 E6 分**，但进「阻断项」，阻断放行（exit 1）
  · 打印分节：⛔ 硬错误（报告的缺陷）vs ⚠️ 阻断项（验证未完成，补齐后可放行）
  · 新增 --cite-min（默认 0.9）转发给 cite_resolve.py --min；--min 若 ≤1 也按比率采用

v4 · 2026-09-19 堵住 E6 的「信任根漏洞」（被审者自己交出伪造源即洗白）：
  · 新增 --dep-trust {auditor,author}（默认 author，从严）与 --registry（默认
    <skill>/assets/dep-registry.json），原样转发给 cite_resolve.py。
  · E6 语义不变（仍是三态），但「① 已验证·通过」的门槛收紧为：
    hard == 0、rate ≥ 门槛，**且**全部 --dep 声明 auditor、**且**每个 dep 的
    sha256 在 registry 里匹配到同名条目。任一环不成立 → ③（阻断，不扣分）。
  · E6 标签保持 [OK]/[HARD]/[BLOCK]；[BLOCK] 走「⚠️ 阻断项（验证未完成）」分节、
    不扣 E6 分、阻断放行（exit 1），并在说明里点名缺哪一项。

用法:
  python mbb_audit.py report.md
  python mbb_audit.py report.md --min 85 --words 6000 --json scorecard.json
  python mbb_audit.py report.md --dep outputs/品牌方方案.md --cite-min 0.9
  python mbb_audit.py report.md --dep X.md --dep-trust auditor --registry assets/dep-registry.json
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mbb_common import (  # noqa: E402
    SELF_SOURCE_HINTS, UNVERIFIED_MARKS, VAGUE_SOURCES, WEAK_CITE_WORDS,
    body_word_count, count_leaks, find_sections, has_placeholder, has_source,
    headings, is_conclusion_title, is_fake_source, is_topic_title,
    numbered_sentences, read_text, sections,
)

# E6 的引用可解析性：默认 registry 与 cite_resolve.py 同源（<skill>/assets/dep-registry.json）
DEFAULT_REGISTRY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "dep-registry.json")
DEP_TRUST_CHOICES = ("auditor", "author")
DEP_TRUST_DEFAULT = "author"      # 从严：不声明即视为「被审者提供」

FAMILIES = {
    "A 问题定义与结构": 25,
    "B 证据与量化": 25,
    "C 洞察与叙事": 20,
    "D 判断与压测": 10,
    "E 交付治理": 20,
}

SOWHAT_RE = re.compile(r"所以|含义|意味着|因此|这说明|对决策者")
NON_ANALYTIC_SECTIONS = ["附录", "图表清单", "图表目录", "来源清单", "参考文献", "版本", "目录"]

# id, 家族, 名称, 家族内权重, 是否硬错误
SPEC = [
    ("A1", "A", "核心问题含量化目标与时限（无占位符）", 5, False),
    ("A2", "A", "议题树存在且顶层去重分支 3±2", 6, False),
    ("A3", "A", "假设台账（假设 + 验证方式 + 证伪影响）", 5, False),
    ("A4", "A", "被证伪假设留档", 3, False),
    ("A5", "A", "明确「不做清单」/取舍", 3, False),
    ("A6", "A", "MECE 遗漏检查句", 3, False),

    ("B1", "B", "数字句来源覆盖率 ≥80% 且外部来源占比 ≥30%", 5, False),
    ("B2", "B", "未核实/未验证数据泄漏 = 0", 4, True),
    ("B3", "B", "口径说明（怎么算的）", 2, False),
    ("B4", "B", "关键结论三档情景/敏感性", 3, False),
    ("B5", "B", "反事实或相关性/因果区分（须量化）", 3, False),
    ("B6", "B", "图表清单且每个图有 SOURCE（建议含真实图形）", 2, False),
    ("B7", "B", "口径自洽：闭环等式 + 指标唯一值 + 时钟声明", 6, True),

    ("C1", "C", "执行摘要：独立成章、结论先行、含数字", 5, True),
    ("C2", "C", "标题结论句占比 ≥80%", 5, False),
    ("C3", "C", "主题词标题 = 0", 3, True),
    ("C4", "C", "so-what 章节覆盖率 ≥50%", 4, False),
    ("C5", "C", "洞察句 + 至少 1 条非消费者来源洞察", 3, False),

    ("D1", "D", "Red Team ≥3 条反方论点", 4, False),
    ("D2", "D", "利益相关者与变革阻力", 3, False),
    ("D3", "D", "Pre-mortem（最可能怎么死）", 3, False),

    ("E1", "E", "字数达标", 2, False),
    ("E2", "E", "版本/日期/作者可追溯", 2, False),
    ("E3", "E", "来源清单附录含可查证条目", 3, True),
    ("E4", "E", "无内部过程文档泄漏", 4, True),
    ("E5", "E", "合规披露齐备、无泛引用与自指来源", 4, True),
    ("E6", "E", "引用可解析（三态：通过／幻影引用=打回／未验证=阻断）", 5, True),
]


def audit(path, min_words=3000, deps=(), cite_min=0.9,
          dep_trust=DEP_TRUST_DEFAULT, registry=DEFAULT_REGISTRY):
    text = read_text(path)
    res = {}

    # ── A 问题定义与结构 ───────────────────────────────
    gq = find_sections(text, ["核心问题", "Governing", "问题定义", "议题树"], max_level=3)
    gq_body = "\n".join(b for _, _, b in gq)
    if not gq:
        res["A1"] = (False, "找不到「核心问题」章节")
    elif has_placeholder(gq_body):
        res["A1"] = (False, "量化目标仍是占位符（如「从 A 提到 B」）——占位符不许进交付稿")
    else:
        res["A1"] = (bool(re.search(r"\d", gq_body)), "核心问题段含数字目标")

    tree = find_sections(text, ["议题树", "问题树", "Issue Tree"], max_level=2)
    if tree:
        tree_body = tree[0][2]
        branches = set(re.findall(r"分支\s*(\d+|一|二|三|四|五|六)", tree_body))
        res["A2"] = (1 <= len(branches) <= 5, f"议题树内去重分支 {len(branches)} 支")
    else:
        res["A2"] = (False, "缺「议题树」章节（没有 issue tree 就写正文 = 不合格）")

    res["A3"] = (bool(find_sections(text, ["假设台账", "关键假设", "假设与验证"]))
                 and bool(re.search(r"验证方式|怎么验|如何验证|若为假|证伪", text)),
                 "需含「假设 | 验证方式 | 若为假结论改为」")
    res["A4"] = (bool(re.search(r"被证伪|证伪假设|被推翻的假设|作废假设", text)),
                 "被推翻的假设必须留档")
    res["A5"] = (bool(re.search(
        r"不做的事|不做什么|不做清单|明确不做|明确舍弃|排除在范围外|非目标|放弃[^。；\n]{0,12}(分析|对照|清单|范围)", text)),
        "必须有显式取舍")
    res["A6"] = (bool(re.search(r"是否遗漏|有没有漏|遗漏检查|是否有其他可能", text)),
                 "需一句显式「是否遗漏」检查")

    # ── B 证据与量化 ───────────────────────────────────
    sents = numbered_sentences(text)
    with_src = [s for _, s in sents if has_source(s)]
    rate = (len(with_src) / len(sents)) if sents else 0.0
    self_src = [s for s in with_src if any(h in s for h in SELF_SOURCE_HINTS)]
    ext_rate = ((len(with_src) - len(self_src)) / len(with_src)) if with_src else 0.0
    res["B1"] = (rate >= 0.8 and ext_rate >= 0.30,
                 f"覆盖率 {rate:.0%}（{len(sents)} 条含数字句）；外部来源占比 {ext_rate:.0%}"
                 f"（{'达标' if ext_rate >= 0.30 else '不足 30%——疑为「自己给自己作证」'}）")
    unver = [w for w in UNVERIFIED_MARKS if w in text]
    unver += re.findall(r"【未核实[^】]*】|未核实的数据|数据未经核实", text)
    res["B2"] = (not unver, f"检出 {len(unver)} 处未核实/未验证标记：{unver[:3]}")
    res["B3"] = (bool(re.search(r"口径|计算方式|定义为|统计范围", text)), "关键指标需写清怎么算的")
    res["B4"] = (bool(re.search(r"三档|悲观|乐观|基准情景|敏感性", text)), "关键结论须给 base/upside/downside")
    cf = [s for _, s in numbered_sentences(text) if "反事实" in s or "holdout" in s.lower()]
    cf_quant = bool(cf) and (any(re.search(r"\d", s) for s in cf) or "无法量化" in text)
    res["B5"] = (cf_quant and bool(re.search(r"相关性.{0,6}因果|排除其他解释|对照实验", text)),
                 f"反事实/对照句 {len(cf)} 条，{'已量化' if cf_quant else '缺量化——反事实必须落到数或明确写「无法量化」'}")

    chart_hits = find_sections(text, ["图表清单", "图表目录", "Exhibit"], max_level=3)
    if chart_hits:
        body = chart_hits[0][2]
        entries = [l for l in body.splitlines() if l.strip().startswith(("-", "*", "|"))]
        with_s = [l for l in entries if has_source(l)]
        ratio = (len(with_s) / len(entries)) if entries else 0.0
        imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)|[\w\-/]+\.(?:png|svg|jpg|jpeg)", text)
        res["B6"] = (len(entries) > 0 and ratio >= 0.8,
                     f"图表条目 {len(entries)}，带来源 {len(with_s)}（{ratio:.0%}）；实际图形引用 {len(imgs)} 个"
                     f"{'（纯文字清单）' if not imgs else ''}")
    else:
        res["B6"] = (False, "缺「图表清单」章节（每张图必须有 SOURCE 行）")

    # B7 口径自洽（硬错误）：闭环等式 + 指标值局部限定 + 时钟声明
    # v3 修复：限定词必须在「该数值的局部窗口」内，不能用全文词频（否则出现 3 次「口径」即放行）
    lines = text.splitlines()
    eq_line = any(
        (sum(k in ln for k in ["期初", "新增", "流失", "期末"]) >= 3 and re.search(r"[=＝]|＋|\+|[−-]", ln))
        for ln in lines
    )
    hits = []
    # 单位必须覆盖 万/亿/人/家/元/条/个/%（早期版本只认「万」，会把用「家」「人」写闭环的稿子误杀）
    for m in re.finditer(r"期末[^\n。；]{0,24}?\d+(?:\.\d+)?\s*(?:万|亿|人|家|元|条|个|次|台|单|%)", text):
        frag = m.group(0)
        if re.search(r"期末\s*\d+(?:\.\d+)?\s*(?:万|亿|人|家|元|条|个|次|台|单|%)?\s*(所需|需要|目标)", frag):
            continue   # 目标列名，不是模拟值
        win = text[max(0, m.start() - 45):m.end() + 45]
        qualified = bool(re.search(r"时钟|口径|逐月|逐季|按季|月度|季度|恒定|线性|区间|四种|方案原文", win))
        hits.append((frag[-12:], qualified))
    total = len(hits)
    q_ratio = (sum(1 for _, q in hits if q) / total) if total else 1.0   # 无期末数值时不因缺单位而误杀
    clock_decl = bool(re.search(r"时钟约定|统一采用|指定唯一时钟|一律标注|口径声明|本报告统一", text))
    res["B7"] = (eq_line and q_ratio >= 0.8 and clock_decl,
                 f"闭环等式 {'有' if eq_line else '缺（须写出「期初 + 新增 − 流失 = 期末」）'}；"
                 f"期末值 {total} 处，其中带时钟/口径限定 {sum(1 for _, q in hits if q)} 处"
                 f"（{q_ratio:.0%}，需 ≥80%）；时钟声明 {'有' if clock_decl else '缺'}；"
                 f"未限定值：{[f for f, q in hits if not q][:3]}")

    # ── C 洞察与叙事 ───────────────────────────────────
    es_hits = find_sections(text, ["执行摘要", "核心结论", "摘要", "Executive Summary"], max_level=2)
    if not es_hits:
        res["C1"] = (False, "缺独立的「执行摘要/核心结论」章节（不许把正文前几行当摘要）")
    else:
        es = es_hits[0][2]
        es_ok = len(es.strip()) > 80 and bool(re.search(r"\d", es)) and es.count("。") >= 2
        res["C1"] = (es_ok, "执行摘要须独立成章、含数字、≥2 句结论")

    hd = [(l, t) for l, t in headings(text) if 2 <= l <= 4]
    conclus = [t for _, t in hd if is_conclusion_title(t)]
    topic_titles = [t for _, t in hd if is_topic_title(t)]
    c_rate = (len(conclus) / len(hd)) if hd else 0.0
    res["C2"] = (c_rate >= 0.8, f"结论句标题 {len(conclus)}/{len(hd)} = {c_rate:.0%}")
    res["C3"] = (len(topic_titles) == 0, f"主题词标题 {len(topic_titles)} 个：{topic_titles[:3]}")

    # 章节级判定：一个二级章节的范围包含其全部子标题内容，直到下一个二级标题
    marks = list(re.finditer(r"^##\s+(.+?)\s*$", text, re.M))
    chapters = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chapters.append((m.group(1).strip(), text[m.end():end]))
    anal = [c for c in chapters if not any(k in c[0] for k in NON_ANALYTIC_SECTIONS)]
    with_sowhat = [c for c in anal if SOWHAT_RE.search(c[1])]
    c4_rate = (len(with_sowhat) / len(anal)) if anal else 0.0
    res["C4"] = (c4_rate >= 0.5, f"有含义句的分析章节 {len(with_sowhat)}/{len(anal)} = {c4_rate:.0%}")
    res["C5"] = (bool(re.search(r"洞察", text)) and bool(re.search(r"文化|竞品|包装|渠道|行业结构|社会情绪", text)),
                 "洞察不能全部来自消费者调研（APG 口径）")

    # ── D 判断与压测 ───────────────────────────────────
    rt = find_sections(text, ["Red Team", "反方", "红队", "反向论证"], max_level=3)
    rt_body = "\n".join(b for _, _, b in rt)
    rt_n = len(re.findall(r"^\s*[-*\d]", rt_body, re.M))
    res["D1"] = (rt_n >= 3, f"反方论点 {rt_n} 条（需 ≥3）")
    res["D2"] = (bool(find_sections(text, ["利益相关者", "干系人", "变革阻力", "受众立场"])),
                 "谁会反对、为什么、怎么处理")
    res["D3"] = (bool(re.search(r"最可能怎么(死|错|失败)|pre-?mortem|失败预演", text, re.I)),
                 "交付前必须回答「最可能怎么死」")

    # ── E 交付治理 ─────────────────────────────────────
    wc = body_word_count(text)
    res["E1"] = (wc >= min_words, f"当前 {wc} 字（门槛 {min_words}）")
    res["E2"] = (bool(re.search(r"版本|V\d+\.\d|修订|日期|作者", text)), "需版本/日期/作者")

    src_hits = find_sections(text, ["来源清单", "参考资料", "数据来源", "参考文献"])
    if not src_hits:
        res["E3"] = (False, "缺「来源清单」附录")
    else:
        body = src_hits[0][2]
        entries = [l for l in body.splitlines() if l.strip().startswith(("-", "*", "|"))
                   and any(k in l for k in ["http", "《", "来源", "年报", "报告", "官网"])]
        # 占位域名与「转引/未证实」不算可查证条目
        real = [l for l in entries if not re.search(
            r"example\.|test\.com|localhost|127\.0\.0\.1|" + "|".join(WEAK_CITE_WORDS), l)]
        res["E3"] = (len(real) >= 3,
                     f"可查证条目 {len(real)} 条（需 ≥3；已排除占位域名与转引类 {len(entries) - len(real)} 条）")

    leaks = count_leaks(text)
    res["E4"] = (not leaks, f"泄漏词：{leaks}")

    vague = [v for v in VAGUE_SOURCES if v in text]
    fake_hits = [s for _, s in numbered_sentences(text) if is_fake_source(s)]
    comp_words = ["个人信息", "隐私", "AI 参与", "AI 完成", "AIGC", "AI 生成", "同意", "免责"]
    comp_secs = find_sections(text, ["合规", "披露", "隐私", "免责"], max_level=3)
    # 只要任一合规章节的正文含合规要素即算齐备（不只看第一个匹配章节）
    comp_ok = any(w in body for _, _, body in comp_secs for w in comp_words)
    res["E5"] = (not vague and not fake_hits and comp_ok,
                 f"泛引用 {len(vague)} 处；自指来源 {len(fake_hits)} 处；合规要素 {'齐备' if comp_ok else '缺失'}（匹配章节 {len(comp_secs)} 个）")

    # E6 引用可解析（调用同级脚本 cite_resolve.py）
    # v3 三态：① 已验证·通过 → 计满分；② 已验证·幻影引用 → 报告的硬错误（打回）；
    #          ③ 未验证 → **不是报告的硬错误**，列入阻断项、阻断放行，但不扣 E6 分。
    # v4 收紧 ① 的准入：只有「全部 dep 声明 --dep-trust auditor」且「每个 dep 的 sha256
    #          在 --registry 里匹配到同名条目」时，cite_resolve 才会判 ①；
    #          否则（含 hard == 0）一律落 ③ —— 被审者交上伪造源也无法洗白。
    # 返回值是三元组 (ok, note, block)；其余检查项仍是二元组。
    cit = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cite_resolve.py")
    if not os.path.exists(cit):
        res["E6"] = (False, "cite_resolve.py 未找到——引用可解析性无法校验", False)
    else:
        import json as _json
        import subprocess as _sp
        import tempfile as _tf
        with _tf.TemporaryDirectory() as td:
            js = os.path.join(td, "cite.json")
            cmd = [sys.executable, cit, os.path.abspath(path), "--json", js,
                   "--min", f"{cite_min:g}",
                   "--dep-trust", dep_trust, "--registry", registry]
            for d in deps:
                cmd += ["--dep", d]
            _sp.run(cmd, capture_output=True, text=True)
            try:
                r = _json.load(open(js, encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                r = None
                err = exc
            if r is None:
                res["E6"] = (False, f"cite_resolve 未产出 JSON（{err}）", False)
            else:
                hard = r.get("hard", 0)
                rate = r.get("rate", 1.0)
                tot = r.get("total", 0)
                pend = r.get("pend", 0)
                block = bool(r.get("block"))
                state = r.get("state", "")
                if block:
                    why = r.get("block_reason") or "被引文件未提供"
                    note = (f"**未验证**：需审计者提供被引文件（{why}）"
                            f"→ 补齐后重跑（不扣本项分，但阻断放行）")
                    missing = r.get("trust_missing") or []
                    if missing:
                        note += "；缺项：" + "；".join(missing[:3])
                        note += (f"；本次 --dep-trust={r.get('dep_trust', dep_trust)}"
                                 f"，registry={r.get('registry', registry)}")
                    if r.get("declared_deps"):
                        note += f"；报告声明的被引文件：{'、'.join('《' + n + '》' for n in r['declared_deps'][:2])}"
                    res["E6"] = (True, note, True)
                else:
                    ok = (hard == 0) and (tot == 0 or rate >= cite_min) and state == "pass"
                    note = f"引用 {tot} 条，可解析率 {rate:.0%}，硬错误 {hard} 处"
                    if state == "pass":
                        note += (f"；来源归属 auditor＋registry 哈希已核（{dep_trust}）")
                    if pend:
                        note += f"；待核验 {pend} 条（来源清单自证，不计入可解析分子）"
                    if hard:
                        note += "；幻影引用——逐条回被引文件核对该版本号/章节是否真实存在"
                    elif tot and rate < cite_min:
                        note += f"；可解析率低于 {cite_min:.0%}（有引用未被来源清单收录或待核验）"
                    res["E6"] = (ok, note, False)

    return res, {"sentences": len(sents), "source_rate": rate, "words": wc,
                 "title_rate": c_rate, "topic_titles": topic_titles,
                 "fake_sources": fake_hits[:5], "vague": vague,
                 "dep_trust": dep_trust, "registry": registry}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--min", type=float, default=85.0, help="百分制及格线（默认 85）")
    ap.add_argument("--words", type=int, default=3000, help="字数门槛")
    ap.add_argument("--json", help="导出 scorecard json")
    ap.add_argument("--dep", action="append", default=[],
                    help="被引文件路径（可多次）；报告引用了外部文件时必传，缺失则 E6 记「未验证（阻断）」")
    ap.add_argument("--cite-min", type=float, default=None,
                    help="E6 引用可解析率门槛（默认 0.9，转发给 cite_resolve.py --min）")
    ap.add_argument("--dep-trust", choices=DEP_TRUST_CHOICES, default=DEP_TRUST_DEFAULT,
                    help="本次 --dep 的来源归属：auditor=审计者独立取得；"
                         "author=由被审者提供（默认，从严）。转发给 cite_resolve.py")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY,
                    help=f"被引文件哈希登记表（默认 {DEFAULT_REGISTRY}），转发给 cite_resolve.py")
    a = ap.parse_args()

    # E6 的可解析率门槛：显式 --cite-min 优先；否则 --min 若明显是比率（≤1）就按比率用；再否则 0.9
    if a.cite_min is not None:
        cite_min = a.cite_min
    elif 0 < a.min <= 1.0:
        cite_min = a.min
    else:
        cite_min = 0.9

    res, meta = audit(a.path, a.words, a.dep, cite_min, a.dep_trust, a.registry)
    fam_w = {}
    for cid, fam, name, w, hard in SPEC:
        fam_w.setdefault(fam, []).append((cid, name, w, hard, res.get(cid, (False, "未执行"))))

    total = 0.0
    hard_fails = []
    block_fails = []
    print(f"【MBB/4A 交付审计 v2】{os.path.basename(a.path)}")
    print(f"含数字句 {meta['sentences']} ｜ 来源覆盖率 {meta['source_rate']:.0%} ｜ 字数 {meta['words']} "
          f"｜ 标题结论句 {meta['title_rate']:.0%}")
    if a.dep:
        print(f"被引文件来源归属：--dep-trust={a.dep_trust}"
              f"（{'审计者独立持源' if a.dep_trust == 'auditor' else '由被审者提供'}）"
              f"；registry={a.registry}")
    print()

    scorecard = {}
    for fam_key, weight in FAMILIES.items():
        got_w = 0
        rows = fam_w.get(fam_key.split()[0], [])
        inner = sum(r[2] for r in rows) or 1
        print(f"── {fam_key}（满分 {weight}）──")
        for cid, name, w, hard, val in rows:
            ok, note = val[0], val[1]
            blk = bool(val[2]) if len(val) > 2 else False   # 第三态（阻断）只在 E6 出现
            got = w if ok else 0
            got_w += got
            flag = "BLOCK" if blk else ("OK  " if ok else ("HARD" if hard else "NG  "))
            print(f"  [{flag:<5}] {cid} {name} — {note}")
            if hard and not ok:
                hard_fails.append(f"{cid} {name}（{note}）")
            elif blk:
                block_fails.append(f"{cid} {name}（{note}）")
        fam_score = got_w / inner * weight
        total += fam_score
        scorecard[fam_key] = round(fam_score, 1)
        print(f"  小计：{fam_score:.1f} / {weight}\n")

    print("═" * 46)
    print(f"总分：{total:.1f} / 100　（及格线 {a.min}）")
    for k, v in scorecard.items():
        print(f"  {k}: {v}")
    if meta.get("fake_sources"):
        print("\n自指来源样例：" + "｜".join(s[:40] for s in meta["fake_sources"]))
    if hard_fails:
        print(f"\n⛔ 硬错误（报告的缺陷）{len(hard_fails)} 项 —— 无论总分多少，禁止交付：")
        for h in hard_fails:
            print(f"  · {h}")
    if block_fails:
        print(f"\n⚠️ 阻断项（验证未完成，补齐后可放行）{len(block_fails)} 项"
              f" —— 这不是报告的缺陷，但不可放行：")
        for b in block_fails:
            print(f"  · {b}")
    if not hard_fails and not block_fails:
        print("\n无硬错误，验证已完成。")

    if hard_fails:
        print("判定：打回重写（有硬错误）")
    elif block_fails:
        print("判定：不可放行（验证未完成——补齐被引文件后重跑，本次不对报告下结论）")
    elif total >= a.min:
        print(f"判定：可交付（≥{a.min:g} 且无硬错误）")
    elif total >= (a.min - 10):
        print(f"判定：补完再交（{a.min - 10:g}–{a.min - 1:g}）")
    else:
        print("判定：打回重写")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"total": round(total, 1), "families": scorecard,
                       "hard_fails": hard_fails, "block_fails": block_fails,
                       "cite_min": cite_min, "meta": meta}, f, ensure_ascii=False, indent=2)
        print(f"\nscorecard 已导出：{a.json}")

    return 0 if (total >= a.min and not hard_fails and not block_fails) else 1


if __name__ == "__main__":
    sys.exit(main())
