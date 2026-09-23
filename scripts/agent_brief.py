#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_brief.py — 生成 AGENT-BRIEF.md（给 subagent 的单文件快照）

为什么有它：**每个 subagent 都是全新上下文**。没有这份简报，它会把整个仓库重读一遍；
有了它，一次读 ~10KB 就知道：这是什么、有多大、脚本怎么分工、判据是什么、有哪些坑。

数据全部**现场统计**（文件数、字数、脚本数、断言数），不手抄 —— 改了仓库跑一次即可同步。

用法：
    python scripts/agent_brief.py            # 生成/刷新 AGENT-BRIEF.md
    python scripts/agent_brief.py --check    # 只校验当前 AGENT-BRIEF.md 是否已过期（CI 用，过期退出 1）
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "AGENT-BRIEF.md")


def count_chars(paths):
    n = 0
    for p in paths:
        try:
            n += len(io.open(p, encoding="utf-8").read())
        except Exception:
            pass
    return n


def walk(ext=None, sub="references"):
    base = os.path.join(ROOT, sub)
    out = []
    for dp, dn, fn in os.walk(base):
        if "__pycache__" in dp:
            continue
        for f in fn:
            if ext is None or f.endswith(ext):
                out.append(os.path.join(dp, f))
    return out


def measure():
    refs = walk(".md", "references")
    scripts = walk(".py", "scripts")
    # 排除夹具目录里的非脚本
    scripts = [s for s in scripts if "/fixtures/" not in s]
    fx = walk(None, "scripts/fixtures")
    return {
        "refs_n": len(refs),
        "refs_chars": count_chars(refs),
        "cases_n": len([f for f in refs if "/cases/" in f]),
        "bm_n": len([f for f in refs if "/商业模式库/" in f]),
        "scripts_n": len(scripts),
        "fixtures_n": len(fx),
    }


def smoke_assertions():
    """读断言数缓存（由 smoke_test.py 跑完写入）。

    ⚠️ 历史：这里原本**现场重跑整套 smoke**，实测**每次 8.21 秒** —— 而本脚本是
    「派 subagent 前顺手生成」的高频动作，8 秒纯属浪费。改为读缓存后 ~0.01 秒。
    缓存缺失时返回「?」，**不为了一个数字付 8 秒**。
    """
    try:
        c = json.load(io.open(os.path.join(HERE, ".assert_count"), encoding="utf-8"))
        return c.get("total", "?")
    except Exception:
        return "?"


def build():
    m = measure()
    n_assert = smoke_assertions()
    k = lambda n: f"{n/10000:.1f} 万" if n >= 10000 else str(n)
    return f"""# AGENT-BRIEF · 给 agent 的单文件快照

> 本文件由 `scripts/agent_brief.py` **自动生成**，请勿手改（改了会被下次生成覆盖）。
> 派 subagent 时先给它这一份 —— 它读 1 份 ≈ 读整个仓库。

## 一、这是什么（30 秒）

**企业营销与商业模式分析器**：给一个企业名 → 出对标 MBB/4A 的分析报告（Markdown + Word）。
**只做拆解与解读，不出执行方案。** 唯一入口是 `SKILL.md`；本份是它的压缩版。

## 二、现在有多大（自动统计）

| 项 | 数量 |
|---|---|
| 参考档（`references/**.md`） | **{m['refs_n']}** 份 ｜约 **{k(m['refs_chars'])} 字符** |
| 其中行业案例档 | {m['cases_n']} 档 |
| 其中商业模式库 | {m['bm_n']} 份 |
| 脚本（`scripts/*.py`，不含夹具） | **{m['scripts_n']}** 支 |
| 回归夹具（`scripts/fixtures/`） | {m['fixtures_n']} 个 |
| 回归断言数（现场跑出） | **{n_assert}** 项 |

> ⚠️ **不要通读**。按 `SKILL.md` 的「知识库路由」表**查**；每份参考档开头有「自解释头」，先读 5 行再决定。

## 三、目录结构

```
README.md         仓库首页（这是什么/怎么装/怎么用）—— 给人看，不是给 agent 看
SKILL.md          唯一入口（定位/门禁/七步工作流/判据/路由表/纪律）
AGENTS.md         跨工具接入说明（各平台怎么配置、hook 模板）
AGENT-BRIEF.md    本份（自动生成）
LICENSE           MIT
assets/           交付模板.docx（Word 底稿）｜dep-registry.json（被引文件哈希登记）
scripts/          {m['scripts_n']} 支脚本 + fixtures/ 夹具 + sync-to-obsidian.sh
references/       {m['refs_n']} 份参考档（含 cases/ {m['cases_n']} 档、商业模式库 {m['bm_n']} 份）
```

## 四、脚本分工（按「什么时候跑」）

| 时机 | 脚本 | 不过的后果 |
|---|---|---|
| 第 1 步 | `issue_tree.py --check` | 议题树不 MECE／假设不可证伪 → 不许进下一步 |
| 第 3 步 | `storyline.py` | 标题不是结论句 → 打回 |
| 第 2/6 步 | `source_ledger.py --min 0.8` | 含数字句来源覆盖 <80% → 打回 |
| 画图后 | `chart_check.py` | 缺 SOURCE／口径／一图一结论 → 打回 |
| 有外部引用时 | `cite_resolve.py --dep …` | 幻影引用 = 硬错误；**未验证 = 阻断** |
| 第 6 步 | `mbb_audit.py --words N --dep …` | **27 项审计**；8 类硬错误或总分 <85 → 打回 |
| 改过脚本后 | `smoke_test.py` | {n_assert} 项回归必须全绿 |
| 出 Word | `assets/交付模板.docx` 为底稿 | 格式不符合 `references/18` → 必修 |

## 五、判据（不可绕过）

- **27 项审计 / 5 维度族**（A 结构 25 ・ B 证据与量化 25 ・ C 叙事 20 ・ D 压测 10 ・ E 治理 20）
- **8 类硬错误**：未核实数据泄漏 ・ 口径不自洽(B7) ・ 主题词标题 ・ 缺执行摘要 ・ 缺可查证来源清单 ・ 内部过程文档泄漏 ・ 合规披露缺失 ・ 引用不可解析(E6)
- **阻断项**：E6 未验证（缺 `--dep` ／ 路径无效 ／ 与被引文件对不上）→ 不扣分但不可放行
- **E6 三态**：① 已验证通过（需 `--dep-trust auditor` + `registry` 哈希匹配）② 幻影引用=硬错误 ③ 未验证=阻断
- **作弊稿必须被拒**（零分析但格式齐会被打到不合格）；**真稿不许被误杀**（反向验收内置在回归里）

## 六、硬约定（**不可违反**）

1. 门禁 8 项一次问全 →《任务规则表》→ 用户确认前不产出正文
2. 用户给定的结构 > 本 skill 默认骨架（逐字沿用，不重排）
3. 交付前原样输出「用户验收项 + scorecard 结论」，**自评不得高于脚本判定**
4. 交付稿简体；**内部过程文档不进交付稿**
5. 每轮回复第一行是《流程状态》行
6. 卡死：同一错误不重试 >2 次；跳步必须声明未校验

## 七、已知坑

1. **引用外部文件必须传 `--dep`**：漏传会把依赖型引用判成幻影（这是刻意的，逼审计者交底）
2. **E6「已验证通过」≠「引用真实」**：只等于「与审计者独立持有、且哈希已登记的源一致」；最终采信要人签字
3. **`--dep` 传错 ≠ 报告有缺陷**：会落到「阻断项」，分节显示，不要当成硬错误去改报告
4. **Word 不要手搓字体字号**：一律用 `assets/交付模板.docx` 作底稿、只填样式名
5. **商业模式库/知识库不要通读**：按路由表查；`references/商业模式库/README.md` 是它的索引
6. **知识库文档里出现的非本 skill 脚本名属历史素材表述**，只读不执行

## 八、当前状态

- 唯一实体位置：`~/Desktop/Marketing-skill/Marketing-Analysis/`（用户级 skill 目录以软链指过来）
- 交付格式：`assets/交付模板.docx`（正文宋体小四／行距 1.5／首行缩进 2 字；H1 黑体 14pt、H3 楷体 14pt、表 10pt 居中）
- 引用校验信任根：`assets/dep-registry.json`

## 九、给 agent 的三条规矩

1. **先读 `SKILL.md` 的三节**（定位与边界／工作流七步／知识库路由），**不要通读仓库**
2. **能跑代码就必须跑**：判据靠脚本，不靠自觉；脚本绿不等于交付达成，用户验收项要另行逐条核
3. **不确定就问，不要猜**：门禁、内容粒度、结构映射这类一旦定错就要重做的决策，先复述再动手
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验是否过期（过期退出 1）")
    a = ap.parse_args()
    doc = build()
    if a.check:
        try:
            cur = io.open(OUT, encoding="utf-8").read()
        except Exception:
            print("AGENT-BRIEF.md 不存在 → 需生成"); return 1
        # 忽略首行时间戳之类的噪声，比对正文
        if cur.strip() != doc.strip():
            print("AGENT-BRIEF.md 已过期 → 跑 `python scripts/agent_brief.py` 刷新"); return 1
        print("AGENT-BRIEF.md 与仓库一致 ✅"); return 0
    io.open(OUT, "w", encoding="utf-8").write(doc)
    print(f"已生成 {OUT}（{len(doc):,} 字符）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
