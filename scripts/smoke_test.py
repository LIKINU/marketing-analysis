#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smoke_test.py — 五支护栏脚本的冒烟测试（正/负夹具 + 作弊夹具，秒级）

设计原则（红队评审后加固）：
  1. **负向夹具必须被判失败** —— 负向也通过 = 护栏是假的（静默失效）。
  2. **作弊夹具必须拿不到高分** —— 「只写格式、不做分析」的稿子不能过 85 分（防「合法但空心」）。
  3. **硬错误不许误杀** —— 例如分析安防行业的报告提到「门禁」不得被判内部泄漏。

v4 · 2026-09-19 堵「信任根漏洞」（被审者自己交出伪造源即洗白）：
  · 凡是断言「必须判 ① 已验证通过」的用例，一律补上
    `--dep-trust auditor --registry <skill>/assets/dep-registry.json`：
    这是把判据**收紧**（不声明归属就只配判 ③），不是放宽。
  · 新增断言：① 的准入（归属+哈希）、作者侧伪造源不得洗白、
    改一字即哈希不匹配、registry 缺失时不得判 ①（fail-closed）。

用法:
  python smoke_test.py
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
F = os.path.join(HERE, "fixtures")

# 真实长稿 + 它的正确依赖文件（回归用；不存在时该条显式 SKIP，不静默通过）
LONG_REPORT = os.path.join(F, "喵鲜日记-拆解报告.md")       # 内置真实长稿（自足 golden set）
LONG_DEP = os.path.join(F, "虚构品牌-商业模式方案.md")        # 其被引文件（basename 须与 dep-registry 条目一致）

# 哈希登记表（v4）：① 已验证通过的准入凭证
REGISTRY = os.path.normpath(os.path.join(HERE, "..", "assets", "dep-registry.json"))

# 刻意不存在的 registry（验证 fail-closed：读不到登记表就不许判 ①）
MISSING_REGISTRY = "/tmp/wb-cite-tests/definitely-missing-registry.json"

# 与真稿无关的另一份文件（模拟「审计者传错 --dep」）
UNRELATED_DEP = os.path.join(HERE, "..", "references", "00-打法库.md")

# 刻意不存在的 --dep 路径（模拟「审计者路径打错」）
MISSING_DEP = "/tmp/wb-cite-tests/definitely-missing-dep.md"
ALLOW_MISSING = {MISSING_DEP, "/tmp/_kuaidang.md"}   # 后者是 composer 的 --out 产出路径，不是输入      # 显式允许缺失，否则会被 inputs_exist 当成夹具缺失而跳过

TMP = "/tmp/wb-cite-tests"          # 临时稿一律写 /tmp，不污染仓库

# ── 临时负向夹具（v3 新增：来源清单自证 / 版本词形缺口 / 自造假被引文件）──
SELF_LISTED_GHOST = """# 某品牌：来源清单自证负向夹具

> 版本 V1.0 ｜ 2026-09-19 ｜ 分析人：测试

## 执行摘要：结论先行

按《2026 假报告》的口径，行业单店月均营收为 13 万元（来源：《2026 假报告》【已核实】）。

## 附录 · 数据来源清单

- 《2026 假报告》，某机构，2026-01
"""

VER_WORDFORM_GHOST = """# 某品牌：版本词形缺口负向夹具

> 版本 V1.0 ｜ 2026-09-19 ｜ 分析人：测试

## 执行摘要：结论先行

品牌方方案 版本号 9.9 里写明门店效率提升 40%（来源：品牌方方案 版本号 9.9【品牌方自述】）。

## 附录 · 数据来源清单

- 《某机构 2026 年年度报告》，某机构投资者关系页，2026-03
"""

# 「来源清单条目自身不计入分母」夹具：正文全部是自证来源，来源清单 3 条
SRC_LIST_ONLY = """# 夹具：来源清单条目不应进分母

> 版本 V1.0 ｜ 2026-09-19 ｜ 分析人：测试

## 执行摘要：结论先行

第一，某品牌单店月均营收 13 万元（来源：本报告测算）。
第二，会员复购率 41%（来源：本报告测算）。
第三，门店数 8412 家（来源：本报告测算）。
第四，营收 148 亿元（来源：本报告测算）。
第五，毛利率 56%（来源：本报告测算）。
第六，流失率 38%（来源：本报告测算）。
第七，CAC 268 元（来源：本报告测算）。
第八，LTV 487 元（来源：本报告测算）。

## 附录 · 数据来源清单

- 《某机构 2026 年年度报告》，某机构投资者关系页，2026-03
- 《某协会 2026 年行业白皮书》，某协会，2026-02
- https://www.prnewswire.com/news/example-release
"""

FAKE_DEP = """# 假的「被引文件」（红队自造，用来给幻影版本号/章节洗白）

品牌方方案 版本号 v9.9

## 99.9 幻影章节

本文件由审计者自造，只为让 v9.9 与 99.9 看起来「存在」。
"""

PHANTOM_INJECT = (
    "\n## 九十九、注入的幻影引用（红队绕过 #1）\n\n"
    "品牌方方案 版本号 v9.9 与 §99.9 的拆法一致（来源：品牌方方案 v9.9【品牌方自述】）。\n")

# ── v4 信任根漏洞的演示夹具（与红队实测手工复现逐字一致）──
# 真稿里插一条幻影引用：本报告根本没有「方案 v9.9 修订说明」，附件 A.0 里的第 12 条口径也不存在
DEMO_PHANTOM_INJECT = "\n（来源：品牌方方案 v9.9 修订说明，见附件 A.0 的第 12 条口径…）\n"
# 被审者「顺手补交」的伪造源：只要它出现，v3 的比对就会「找到」v9.9 → 洗白
DEMO_FAKE_DEP = "# 假的「被引文件」\n\n版本记录：v9.9 修订说明\n"


def write_tmp(name, content):
    os.makedirs(TMP, exist_ok=True)
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def make_mutated_dep():
    """把真被引文件**改 1 个字**（保持同名）→ 触发「哈希不匹配」（v4-E）

    只改一处**正文散文**里的字：不动标题、版本号、章节号、附件号，
    确保「引用存在性」结论不变（hard 仍为 0），
    从而验证「哈希不匹配」这一环单独就能拦住状态 ①。
    """
    if not os.path.exists(LONG_DEP):
        return None
    lines = open(LONG_DEP, encoding="utf-8").read().splitlines()
    pick = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if len(re.findall(r"[\u4e00-\u9fff]", s)) < 15:
            continue
        if any(ch in s for ch in "#《》§|>％%0123456789"):
            continue
        if re.match(r"^[一二三四五六七八九十]+\s*[、.．]", s):
            continue
        pick = i
        break
    if pick is None:
        return None
    ln = lines[pick]
    ch = re.search(r"[\u4e00-\u9fff]", ln).group(0)
    if ch == "砚":
        return None
    lines[pick] = ln.replace(ch, "砚", 1)
    d = os.path.join(TMP, "e")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, os.path.basename(LONG_DEP))     # 同名！否则只会判「未登记」
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return p


def prepare_tmp():
    """造临时夹具；真稿不存在时返回 {}（相关用例显式 SKIP）"""
    out = {
        "self_listed": write_tmp("self_listed_ghost.md", SELF_LISTED_GHOST),
        "wordform": write_tmp("ver_wordform_ghost.md", VER_WORDFORM_GHOST),
        "src_only": write_tmp("src_list_only.md", SRC_LIST_ONLY),
        "fake_dep": write_tmp("fake_dep.md", FAKE_DEP),
    }
    if os.path.exists(LONG_REPORT):
        raw = open(LONG_REPORT, encoding="utf-8").read()
        marker = "\n## 一、核心问题"
        if marker in raw:
            out["phantom"] = write_tmp(
                "real_with_phantom.md", raw.replace(marker, PHANTOM_INJECT + marker, 1))
            out["demo_report"] = write_tmp(
                "real_with_demo_phantom.md",
                raw.replace(marker, DEMO_PHANTOM_INJECT + marker, 1))
        out["demo_fake_dep"] = write_tmp("demo_fake_dep.md", DEMO_FAKE_DEP)
        mut = make_mutated_dep()
        if mut:
            out["mutated_dep"] = mut
    return out


def tmp_cases(tmp):
    """E6 三态 + 绕过路径的回归断言（全部只在 /tmp 与真稿上跑）"""
    if not tmp:
        return []
    core = [
        # ── 绕过路径 ──
        ("E6 · 绕过#2 来源清单自证（幻影书目）不得通过",
         ["cite_resolve.py", tmp["self_listed"], "--dep", UNRELATED_DEP],
         1, ["待核验", "不通过"]),
        ("E6 · 绕过#3 版本词形「版本号 9.9」必须被抽出",
         ["cite_resolve.py", tmp["wordform"], "--dep", UNRELATED_DEP],
         1, ["版本 9.9", "硬错误（引用了不存在的东西）：1 处"]),
        ("E6 · 绕过#1 自造假被引文件不得洗白（审计器侧）",
         ["mbb_audit.py", tmp["phantom"], "--words", "6000", "--dep", tmp["fake_dep"]],
         1, ["阻断项", "未验证", "不可放行"]),
        # ── 误杀修复（状态 ③）──
        ("E6 · 审计者传错 --dep → 阻断，不打硬错误标签",
         ["cite_resolve.py", LONG_REPORT, "--dep", UNRELATED_DEP],
         1, ["未验证", "--dep", "不可放行"]),
        ("E6 · 审计者传错 --dep 时审计器仍给满分（不双重惩罚）",
         ["mbb_audit.py", LONG_REPORT, "--words", "6000", "--dep", UNRELATED_DEP],
         1, ["总分：100.0", "⚠️ 阻断项", "不可放行"]),
        ("E6 · 审计者路径打错 → 阻断，不打硬错误标签",
         ["cite_resolve.py", LONG_REPORT, "--dep", MISSING_DEP],
         1, ["未验证", "读取失败"]),
        # ── 状态 ①② 正向（v4：① 的准入必须带上「审计者独立持源 + registry 哈希」）──
        ("E6 · 真稿＋正确 --dep＋auditor 归属 → 已验证通过、0 硬错误",
         ["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP,
          "--dep-trust", "auditor", "--registry", REGISTRY],
         0, ["判定：通过", "硬错误（引用了不存在的东西）：0 处"]),
        ("E6 · 真稿审计 100 分可交付（auditor 归属）",
         ["mbb_audit.py", LONG_REPORT, "--words", "6000", "--dep", LONG_DEP,
          "--dep-trust", "auditor", "--registry", REGISTRY],
         0, ["总分：100.0", "可交付", "无硬错误，验证已完成。"]),
    ]
    return core


def trust_cases(tmp):
    """v4「信任根漏洞」的验收断言（A–E / fail-closed）

    返回 5 元组：(名称, 命令, 期望 exit, 必须出现的串, **禁止出现**的串)。
    禁止项用来卡「不许出现某个标签/结论」这类反向断言。
    """
    if not tmp or not os.path.exists(LONG_REPORT) or not os.path.exists(LONG_DEP):
        return []
    audit_A = ["--dep-trust", "auditor", "--registry", REGISTRY]
    return [
        # A 真稿＋真 dep＋auditor＋registry 已登记 → ① 已验证通过
        ("v4-A · 真稿＋auditor＋registry 已登记 → ① 已验证通过",
         ["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP] + audit_A,
         0, ["判定：通过", "硬错误（引用了不存在的东西）：0 处",
             "被引文件来源归属/哈希（状态 ① 的准入）", "审计者独立持源"], []),
        # B 不声明归属（默认 author，从严）→ ③ 未验证（阻断），不扣分、不打「硬错误」
        ("v4-B · 不声明归属 → ③ 未验证（阻断），全文无「硬错误」标签",
         ["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP],
         1, ["未验证（阻断）", "未声明归属", "判定：未验证", "不可放行"], ["硬错误"]),
        ("v4-B2 · 不声明归属：审计器仍给 100 分但阻断放行（不双重惩罚）",
         ["mbb_audit.py", LONG_REPORT, "--words", "6000", "--dep", LONG_DEP],
         1, ["总分：100.0", "⚠️ 阻断项（验证未完成，补齐后可放行）",
             "不可放行", "未声明归属", "[BLOCK]"], ["硬错误"]),
        # C 漏洞演示：真 dep ＋ 被审者自造的假 dep，不得被洗白成「通过」
        ("v4-C · 漏洞演示：真 dep＋假 dep＋auditor 不得洗白为「通过」",
         ["cite_resolve.py", tmp["demo_report"], "--dep", LONG_DEP,
          "--dep", tmp["demo_fake_dep"]] + audit_A,
         1, ["不可放行"], ["判定：通过", "可交付"]),
        # D 幻影引用（hard > 0）在任何归属下都判 ② 硬错误
        ("v4-D · auditor 归属下幻影引用仍判 ② 硬错误（任何归属下都成立）",
         ["cite_resolve.py", os.path.join(F, "ghost_cite.md"),
          "--dep", UNRELATED_DEP] + audit_A,
         1, ["硬错误（引用了不存在的东西）：4 处", "判定：不通过"], []),
        # E 真被引文件改 1 个字（同名）→ 哈希不匹配 → ③（附登记值与实际 sha 前缀）
        ("v4-E · 被引文件改一字 → ③ 哈希不匹配（列出实际 sha256 前 16 位）",
         ["cite_resolve.py", LONG_REPORT, "--dep", tmp["mutated_dep"]] + audit_A,
         1, ["未验证（阻断）", "哈希不匹配", "实际 sha256=",
             "a678ad179cdeb14e"], ["判定：通过"]),
        # fail-closed：registry 读不到时绝不许判 ①
        ("v4-failclosed · registry 缺失 → ③ 哈希未登记（不许判 ①）",
         ["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP,
          "--dep-trust", "auditor", "--registry", MISSING_REGISTRY],
         1, ["未验证（阻断）", "哈希未登记"], ["判定：通过"]),
    ]


def run(args):
    p = subprocess.run([PY] + args, cwd=HERE, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def run_json(args):
    """跑一条命令并把 --json 产物读回来（读不到时第三项为 None）"""
    with tempfile.TemporaryDirectory() as d:
        js = os.path.join(d, "out.json")
        code, out = run(list(args) + ["--json", js])
        try:
            with open(js, encoding="utf-8") as f:
                return code, out, json.load(f)
        except Exception:  # noqa: BLE001
            return code, out, None


def parse_total(out):
    m = re.search(r"总分：([\d.]+)\s*/\s*100", out)
    return float(m.group(1)) if m else None


def parse_sentence_count(out):
    m = re.search(r"含数字句\s*(\d+)", out)
    return int(m.group(1)) if m else None


def parse_hard_errors(out):
    """cite_resolve 的硬错误计数（『硬错误（引用了不存在的东西）：N 处』）"""
    m = re.search(r"硬错误（引用了不存在的东西）：(\d+)\s*处", out)
    return int(m.group(1)) if m else None


def inputs_exist(args):
    """夹具是否存在（相对路径按脚本目录解析）；不存在则显式 SKIP，不静默通过

    ALLOW_MISSING 里的路径是「**故意不存在**」的负向输入（模拟审计者路径打错），
    必须放行而不是被当成夹具缺失跳过。
    """
    for a in args:
        if not a.endswith((".md", ".txt")) or a in ALLOW_MISSING:
            continue
        p = a if os.path.isabs(a) else os.path.join(HERE, a)
        if not os.path.exists(p):
            return False
    return True


CASES = [
    ("议题树 · 生成",
     ["issue_tree.py", "--company", "测试公司", "--type", "b2c"],
     0, ["分支 1", "是否遗漏", "反证条件"]),
    ("议题树 · 校验通过",
     ["issue_tree.py", "--check", os.path.join(F, "good_tree.md")],
     0, ["判定：通过"]),
    ("议题树 · 拦下残缺树",
     ["issue_tree.py", "--check", os.path.join(F, "bad_tree.md")],
     1, ["不通过"]),
    ("故事线 · 合格稿通过",
     ["storyline.py", os.path.join(F, "good_report.md")],
     0, ["判定：通过"]),
    ("故事线 · 拦下主题词标题",
     ["storyline.py", os.path.join(F, "bad_report.md")],
     1, ["不通过", "主题词"]),
    ("故事线 · 拦下「数字假结论」标题",
     ["storyline.py", "--check-titles", os.path.join(F, "fake_titles.txt")],
     1, ["不通过"]),
    ("来源台账 · 合格稿通过",
     ["source_ledger.py", os.path.join(F, "good_report.md")],
     0, ["覆盖率"]),
    ("来源台账 · 拦下未核实/无来源",
     ["source_ledger.py", os.path.join(F, "bad_report.md")],
     1, ["未核实", "泛引用"]),
    ("交付审计 · 合格稿可交付",
     ["mbb_audit.py", os.path.join(F, "good_report.md"), "--words", "400"],
     0, ["可交付"]),
    ("交付审计 · 打回不合格稿",
     ["mbb_audit.py", os.path.join(F, "bad_report.md"), "--words", "400"],
     1, ["硬错误"]),
    ("交付审计 · 打回作弊稿",
     ["mbb_audit.py", os.path.join(F, "cheat_report.md"), "--words", "400"],
     1, ["硬错误", "自指来源"]),
    ("骨架 · 真实长稿不缺节", ["composer.py", "--check", os.path.join(F, "喵鲜日记-拆解报告.md")],
     0, ["结构完整"]),
    ("骨架 · 缺节被拦", ["composer.py", "--check", os.path.join(F, "bad_skeleton.md")],
     1, ["缺章", "判定：不合格"]),
    ("骨架 · 真稿不缺章不判过薄", ["composer.py", "--check", os.path.join(F, "喵鲜日记-拆解报告.md")],
     0, ["结构完整"]),
    ("门禁 · 一次跑完 7 项且真稿全绿",
     ["gate.py", os.path.join(F, "喵鲜日记-拆解报告.md"), "--words", "8000",
      "--dep", os.path.join(F, "虚构品牌-商业模式方案.md"), "--dep-trust", "auditor"],
     0, ["全部硬判通过"]),
    ("骨架 · 每个小点都带填空规格",
     ["composer.py", "--spec-audit", "全量分析"], 0, ["填空规格齐备"]),
    ("骨架 · 快档小点更少（生成更快）",
     ["composer.py", "--out", "/tmp/_kuaidang.md", "--tier", "全量分析", "--depth", "快档"],
     0, ["快档"]),
    ("骨架 · 小点内容过薄被拦", ["composer.py", "--check", os.path.join(F, "thin_sub.md")],
     1, ["内容过薄", "3.2"]),
    ("交付审计 · E6 拦下幻影引用",
     ["mbb_audit.py", os.path.join(F, "ghost_cite.md"), "--words", "10"],
     1, ["E6 引用可解析", "打回"]),
    ("Ghost Deck · 输出骨架",
     ["storyline.py", "--ghost"],
     0, ["Ghost Deck"]),
    ("图表规范 · 合格稿通过",
     ["chart_check.py", os.path.join(F, "good_report.md")],
     0, ["判定：通过"]),
    ("图表规范 · 拦下无图表清单",
     ["chart_check.py", os.path.join(F, "bad_report.md")],
     1, ["缺「图表清单」章节", "不通过"]),
    ("图表规范 · 模板可输出",
     ["chart_check.py", "--template"],
     0, ["图表清单"]),
    ("业态清单 · 可列出",
     ["issue_tree.py", "--types"],
     0, ["b2c", "b2b", "platform"]),
    ("引用可解析 · 合格稿通过",
     ["cite_resolve.py", os.path.join(F, "good_report.md")],
     0, ["判定：通过"]),
    ("引用可解析 · 拦下幻影引用",
     ["cite_resolve.py", os.path.join(F, "ghost_cite.md"),
      "--dep", os.path.join(HERE, "..", "references", "00-打法库.md")],
     1, ["硬错误（引用了不存在的东西）：4 处"]),
    ("引用可解析 · 真实长稿＋正确 --dep 不得误杀（auditor 归属）",
     ["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP,
      "--dep-trust", "auditor", "--registry", REGISTRY],
     0, ["硬错误（引用了不存在的东西）：0 处"]),
]

# ── 数值型断言（比字符串匹配更硬）──────────────────────────
def numeric_checks():
    results = []

    # ① 作弊稿不得达到及格线（红队实测过的绕过路径）
    code, out = run(["mbb_audit.py", os.path.join(F, "cheat_report.md"), "--words", "400"])
    total = parse_total(out)
    results.append(("作弊稿总分 < 60（实测 %s）" % total, total is not None and total < 60,
                    f"exit={code}"))

    # ② 合格稿必须 ≥85
    code, out = run(["mbb_audit.py", os.path.join(F, "good_report.md"), "--words", "400"])
    total = parse_total(out)
    results.append(("合格稿总分 ≥ 85（实测 %s）" % total, total is not None and total >= 85,
                    f"exit={code}"))

    # ③ 中文数字也要进「含数字句」分母（不许靠中文数字逃逸来源检查）
    code, out = run(["source_ledger.py", os.path.join(F, "bad_report.md")])
    n = parse_sentence_count(out)
    results.append(("中文数字句被计入分母（检出 %s 句）" % n, n is not None and n >= 3, ""))

    # ④ 硬错误不许误杀：安防行业报告提到「门禁」不得判内部泄漏
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "security_industry.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# 某安防企业分析\n\n> 版本 V1.0 ｜ 2026-09-19 ｜ 分析人：测试\n\n"
                    "## 执行摘要：门禁业务是主要增长来源\n\n"
                    "门禁系统出货量在 2025 年增长 18%（来源：公司 2025 年年度报告【已核实】）。\n")
        code, out = run(["mbb_audit.py", p, "--words", "10"])
        ok = "E4 无内部过程文档泄漏 — 泄漏词：[]" in out
        results.append(("「门禁」不再误判为内部泄漏", ok, ""))

    if not os.path.exists(LONG_REPORT):
        return results

    # ⑤ 状态 ③ 不得给报告扣 E6 分，也不得打「硬错误」标签（误杀修复的核心）
    code, out = run(["mbb_audit.py", LONG_REPORT, "--words", "6000", "--dep", UNRELATED_DEP])
    total = parse_total(out)
    results.append((
        "审计者传错 --dep：不扣分、无「硬错误」字样、判定阻断（实测 %s 分 / exit=%d）" % (total, code),
        code == 1 and total == 100.0 and "硬错误" not in out
        and "⚠️ 阻断项（验证未完成，补齐后可放行）" in out, ""))

    # ⑥ 状态 ② 幻影引用仍须打回，且仍打「硬错误」标签（不准靠三态洗白）
    code, out = run(["cite_resolve.py", os.path.join(F, "ghost_cite.md"),
                     "--dep", UNRELATED_DEP])
    results.append(("幻影引用仍判硬错误 4 处（实测 %s）" % parse_hard_errors(out),
                    code == 1 and parse_hard_errors(out) == 4, ""))

    # ⑦ 引用分母与 --dep 解耦、同参数可复现（原「283 vs 305」不可复现问题）
    #    v4：① 的准入要求归属+哈希，故「正向可比」的那一路带上 auditor/registry
    AUD = ["--dep-trust", "auditor", "--registry", REGISTRY]
    c1, _, j1 = run_json(["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP] + AUD)
    c2, _, j2 = run_json(["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP] + AUD)
    c3, _, j3 = run_json(["cite_resolve.py", LONG_REPORT])
    c4, _, j4 = run_json(["cite_resolve.py", LONG_REPORT, "--dep", UNRELATED_DEP])
    same = bool(j1 and j2) and (j1["total"], j1["rate"]) == (j2["total"], j2["rate"])
    decoupled = bool(j1 and j3 and j4) and j1["total"] == j3["total"] == j4["total"]
    tr = (j1["total"], round(j1["rate"], 4)) if j1 else None
    results.append(("同参数两次跑 total/rate 一致（%s）" % (tr,), same, ""))
    results.append(("total 不随 --dep 变化（正确/缺失/无关 dep 均为 %s）"
                    % (j1["total"] if j1 else None,), decoupled, ""))
    results.append(("状态 ③ 的 JSON：block=true 且 rate 记 0（fail-closed）",
                    bool(j4) and j4["block"] is True and j4["rate"] == 0.0
                    and c4 == 1 and c3 == 1, ""))

    # ⑧ 来源清单条目自身不进分母（否则「把书目抄一遍」就虚高）
    tmp = prepare_tmp()
    c5, _, j5 = run_json(["cite_resolve.py", tmp["src_only"], "--dep", tmp["fake_dep"]])
    results.append(("来源清单条目不计入分母（该夹具引用总数实测 %s）"
                    % (j5 and j5["total"]), bool(j5) and j5["total"] == 0, f"exit={c5}"))

    # ── v4：信任根加固的数值级断言 ──────────────────────
    cA, outA, jA = run_json(["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP] + AUD)
    reg_sha = ""
    try:
        reg = json.load(open(REGISTRY, encoding="utf-8"))
        reg_sha = str(reg["entries"][0]["sha256"]).lower()
    except Exception:  # noqa: BLE001
        reg_sha = ""
    dep_sha = ""
    if os.path.exists(LONG_DEP):
        dep_sha = hashlib.sha256(open(LONG_DEP, "rb").read()).hexdigest()
    results.append((
        "v4-A · ① 的准入：state=pass 且 dep 实际 sha256 == registry 登记值",
        bool(jA) and cA == 0 and jA.get("state") == "pass"
        and jA.get("dep_sha256", {}).get(os.path.basename(LONG_DEP)) == reg_sha
        and reg_sha == dep_sha, f"registry={reg_sha[:16]}…/实际={dep_sha[:16]}…"))

    cB, outB, jB = run_json(["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP])
    results.append((
        "v4-B · 不声明归属：state=block / block_kind=trust，且全文无「硬错误」",
        bool(jB) and cB == 1 and jB.get("state") == "block"
        and jB.get("block_kind") == "trust" and "硬错误" not in outB
        and any("未声明归属" in m for m in jB.get("trust_missing", [])), ""))

    cC, outC, jC = run_json(["cite_resolve.py", tmp["demo_report"], "--dep", LONG_DEP,
                             "--dep", tmp["demo_fake_dep"]] + AUD)
    results.append((
        "v4-C · 漏洞演示场景必须 ≠ ①（实测 state=%s / exit=%s）"
        % (jC and jC.get("state"), cC),
        bool(jC) and cC == 1 and jC.get("state") != "pass"
        and "判定：通过" not in outC, ""))

    cE, outE, jE = run_json(["cite_resolve.py", LONG_REPORT, "--dep", tmp["mutated_dep"]] + AUD)
    mut_sha = ""
    if os.path.exists(tmp["mutated_dep"]):
        mut_sha = hashlib.sha256(open(tmp["mutated_dep"], "rb").read()).hexdigest()
    results.append((
        "v4-E · 改一字：state=block 且文案含「哈希不匹配」+实际 sha 前缀 %s" % mut_sha[:16],
        bool(jE) and cE == 1 and jE.get("state") == "block"
        and "哈希不匹配" in outE and mut_sha and mut_sha[:16] in outE
        and mut_sha != dep_sha, ""))

    # G：真稿＋auditor 连跑两次，(总数, 可解析率, 判定) 必须一致
    g1c, g1o, g1j = run_json(["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP] + AUD)
    g2c, g2o, g3j = run_json(["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP] + AUD)

    def _verdict(o):
        m = re.search(r"判定：(\S+)", o)
        return m.group(1) if m else None

    g1 = (g1j and g1j["total"], g1j and round(g1j["rate"], 4), _verdict(g1o), g1c)
    g2 = (g3j and g3j["total"], g3j and round(g3j["rate"], 4), _verdict(g2o), g2c)
    results.append(("v4-G · auditor 归属连跑两次 (总数,可解析率,判定) 一致（%s）" % (g1,),
                    g1 == g2 and g1[0] is not None, ""))

    # fail-closed：registry 缺失时不许判 ①
    cF, outF, jF = run_json(["cite_resolve.py", LONG_REPORT, "--dep", LONG_DEP,
                             "--dep-trust", "auditor", "--registry", MISSING_REGISTRY])
    results.append((
        "v4-failclosed · registry 读不到 → 不得判 ①（state=block、含「哈希未登记」）",
        bool(jF) and cF == 1 and jF.get("state") == "block"
        and "哈希未登记" in outF and jF.get("verdict") != "通过", ""))
    return results


def main():
    if not os.path.exists(REGISTRY):
        print(f"[FAIL] registry 缺失：{REGISTRY}")
        print("→ v4 的「① 已验证通过」准入依赖哈希登记表，不许在没有它的情况下放行。")
        return 1

    tmp = prepare_tmp()
    all_cases = list(CASES) + tmp_cases(tmp) + trust_cases(tmp)
    cases = [c for c in all_cases if inputs_exist(c[1])]
    skipped = [c[0] for c in all_cases if not inputs_exist(c[1])]
    numeric = numeric_checks()

    print(f"【护栏冒烟测试】命令级 {len(cases)} 项 + 数值级 {len(numeric)} 项\n")
    failed = []
    for case in cases:
        name, args, want_code, want_strs = case[0], case[1], case[2], case[3]
        want_not = case[4] if len(case) > 4 else []      # v4：反向断言（不许出现）
        code, out = run(args)
        missing = [s for s in want_strs if s not in out]
        forbidden = [s for s in want_not if s in out]
        ok = (code == want_code) and not missing and not forbidden
        # 计数型断言：want_strs 写了「硬错误（…）：N 处」时，把解析出的数字再卡一道
        for s in want_strs:
            mm = re.search(r"硬错误（[^）]*）：(\d+)\s*处", s)
            if mm:
                got = parse_hard_errors(out)
                if got != int(mm.group(1)):
                    ok = False
                    missing.append(f"硬错误计数应为 {mm.group(1)} 处，实得 {got}")
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            failed.append(name)
            print(f"         期望 exit={want_code} 实得 exit={code}；缺失关键串：{missing}；"
                  f"不应出现却出现了：{forbidden}")
            for l in out.strip().splitlines()[-6:]:
                print(f"         | {l}")
    for name in skipped:
        print(f"  [SKIP] {name}（夹具不存在，未参与判定）")

    print()
    for name, ok, extra in numeric:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {extra}")
        if not ok:
            failed.append(name)

    total_cases = len(cases) + len(numeric)
    tail = f"（另有 {len(skipped)} 项因夹具缺失跳过）" if skipped else ""
    print(f"\n结果：{total_cases - len(failed)}/{total_cases} 通过{tail}")
    _write_assert_cache(total_cases)
    if failed:
        print("失败项：" + "、".join(failed))
        print("→ 护栏失效或误杀，必须修脚本，不许放宽判据。")
        return 1
    print("护栏有效：正向通过、负向被拦、作弊拿不到分、无误杀。")
    return 0


def _write_assert_cache(total):
    """把断言总数写进缓存 —— agent_brief.py 免重跑整套（省 ~8 秒）。
    判据：缓存只是**加速**，真相仍在本次实跑；smoke 一跑就刷新它。"""
    import json
    try:
        # ⚠️ 本脚本没 import io（历史遗留），必须用内置 open —— 否则 NameError 被 try 吞掉、
        #    缓存永远写不出来，而「agent_brief 显示 ?」看起来像没生成，实则是静默失败
        with open(os.path.join(HERE, ".assert_count"), "w", encoding="utf-8") as f:
            json.dump({"total": total, "at": __import__("datetime").datetime.now().isoformat(timespec="seconds")}, f)
    except Exception as e:
        print(f"（缓存写入失败，不影响测试结果：{e}）", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
