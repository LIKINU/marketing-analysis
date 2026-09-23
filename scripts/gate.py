#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate.py — 一次跑完全部交付判据（把 6–7 次工具往返压成 1 次）

为什么有它：
    第 6 步原本要**逐条敲 6 条命令**（issue_tree / storyline / source_ledger / chart_check /
    cite_resolve / mbb_audit + composer --check）。在 agent 里**每条命令 = 一次工具往返**，
    往返本身要等模型推理 —— 于是「校验」比「写稿」还磨人。
    本脚本把 7 支判据**串成一次调用**，只回一屏汇总。

用法：
    python scripts/gate.py 报告.md
    python scripts/gate.py 报告.md --dep 被引文件.md --words 8000
    python scripts/gate.py 报告.md --dep a.md --dep b.md --quick     # quick=跳过 mbb_audit 的引用校验

判据分级（与 SKILL 一致）：
    硬判（不过 → exit 1）：议题树 / 标题 / 来源覆盖 / 图表规范 / 引用可解析 / 骨架完整性 / 27 项审计
    提示（不影响退出码）：报告里以「[WARN]」显示
退出码：0 全绿；1 有硬判不过；2 执行错误
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(args, timeout=180):
    p = subprocess.run([PY] + args, cwd=HERE, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def last_meaningful(out):
    """取最后一行有信息量的输出（判据脚本都把结论放最后）"""
    for ln in reversed([x.strip() for x in out.splitlines() if x.strip()]):
        if ln.startswith(("判定：", "结果：", "【")):
            return ln
    return (out.strip().splitlines() or ["（无输出）"])[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--dep", action="append", default=[])
    ap.add_argument("--words", type=int, default=6000)
    ap.add_argument("--min-chars", type=int, default=120)
    # 历史快照豁免（新增章节后旧稿必然缺；显式传，不偷偷放宽）
    ap.add_argument("--allow-missing", default="", help="豁免的章节 sid（逗号分隔）")
    # E6 的准入条件必须能透传：漏了它，审计会落「阻断（未验证）」而不是「已验证通过」
    ap.add_argument("--dep-trust", choices=["auditor", "author"], default="author")
    ap.add_argument("--registry", default=os.path.join(os.path.dirname(HERE), "assets", "dep-registry.json"))
    a = ap.parse_args()

    R = os.path.abspath(a.report)
    if not os.path.exists(R):
        print(f"❌ 找不到报告：{R}")
        return 2

    # ⚠️ 子进程的 cwd 是 scripts/，而调用方传的往往是「相对 skill 根」的路径
    #    （如 scripts/fixtures/x.md）→ 必须转绝对路径，否则被解析成 scripts/scripts/… → 落「未验证」
    dep_args = []
    for d in a.dep:
        dep_args += ["--dep", os.path.abspath(d)]
    trust_args = ["--dep-trust", a.dep_trust, "--registry", a.registry]

    checks = [
        ("议题树 MECE/可证伪", ["issue_tree.py", "--check", R], True),
        ("标题＝结论句", ["storyline.py", R], True),
        ("来源覆盖率 ≥80%", ["source_ledger.py", R, "--min", "0.8"], True),
        ("图表规范", ["chart_check.py", R], True),
        # ⚠️ cite_resolve 同样要收信任参数：漏传 → 落「未验证」而非「已验证通过」（E6 准入）
        ("引用可解析（幻影＝硬错误）", ["cite_resolve.py", R] + dep_args + trust_args, True),
        ("骨架完整 + 小点不薄", ["composer.py", "--check", R, "--min-chars", str(a.min_chars)]
         + (["--allow-missing", a.allow_missing] if a.allow_missing else []), True),
        # 第 8 项：能不能**直接给客户**（占位符/注记/内部残留/结构齐备）——与内容质量无关，是交付形态
        ("交付就绪（可直接给客户）", ["deliver_check.py", R] + (["--words", str(a.words)] if a.words else []), True),
        ("27 项交付审计", ["mbb_audit.py", R, "--words", str(a.words)] + dep_args + trust_args, True),
    ]

    print("=" * 72)
    print(f"交付门禁 · 一次跑完 {len(checks)} 项｜{os.path.basename(R)}")
    print("=" * 72)
    hard_fail, warn = [], []
    for name, args, is_hard in checks:
        try:
            rc, out = run(args)
        except Exception as e:                       # noqa: BLE001
            print(f"  [ERR ] {name}：执行异常 {e}")
            hard_fail.append(name)
            continue
        mark = "OK  " if rc == 0 else "NG  "
        if rc != 0 and is_hard:
            hard_fail.append(name)
        print(f"  [{mark}] {name:<24} {last_meaningful(out)[:52]}")
        for ln in out.splitlines():
            if ln.strip().startswith("[WARN]"):
                warn.append(f"{name} → {ln.strip()[6:].strip()[:60]}")
    print("-" * 72)
    if warn:
        print(f"⚠️ 提示 {len(warn)} 条（不影响放行）：")
        for w in warn[:8]:
            print(f"   · {w}")
        if len(warn) > 8:
            print(f"   …另有 {len(warn) - 8} 条")
    if hard_fail:
        print(f"⛔ 硬判不过 {len(hard_fail)} 项：{'、'.join(hard_fail)}")
        print("判定：不可交付（先修上面 NG 项，再重跑本命令）")
        return 1
    print("✅ 全部硬判通过")
    print("判定：可交付（仍需按《任务规则表》核对用户自定义验收项 —— 脚本绿 ≠ 交付达成）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
