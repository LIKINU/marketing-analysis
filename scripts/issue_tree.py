#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""issue_tree.py — 生成 / 校验 MECE 议题树与假设（MBB 第一步：先出树，再动手）

用法:
  python issue_tree.py --company "蜜雪冰城" --type b2c > tree.md   # 生成议题树骨架
  python issue_tree.py --check tree.md                            # 校验已有议题树
  python issue_tree.py --types                                    # 看支持的业态

判据（对应差距分析 D1/D2/D3）:
  · 顶层分支数必须 3±2（MECE 可管理性）
  · 每个末级分支必须是一句「可被证伪的断言」，且写明反证条件
  · 必须含「是否遗漏」的显式检查句
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mbb_common import headings, read_text  # noqa: E402

FALSIFY_HINTS = ["推翻", "证伪", "反证", "若不成立", "若不", "如果为假", "什么数据会否定"]
MISS_CHECK_HINTS = ["是否遗漏", "有没有漏", "遗漏检查", "其他可能", "是否有其他"]

TREES = {
    "b2c": {
        "label": "B2C 消费品 / 连锁 / 线上品牌",
        "question": "为什么 {c} 的{metric}没能跑赢行业，钱漏在哪一层？",
        "branches": [
            ("流量与获客", ["曝光是否够（声量份额 vs 市场份额是否背离）",
                            "进店/点击效率是否低于同类",
                            "拉新单位成本是否在恶化"]),
            ("转化与客单", ["货盘结构是否拖住客单（低毛利品占比）",
                            "价格带是否与目标人群支付意愿错位",
                            "渠道内转化漏斗哪一环断裂"]),
            ("复购与留存", ["复购率与行业基准的缺口有多大",
                            "老客贡献占比是否过低",
                            "私域/会员机制是否真的在运转"]),
            ("成本与单位经济", ["单客获取成本 vs 单客毛利是否为正",
                                "履约与退换货成本占比",
                                "营销费用率是否高于同行"]),
        ],
    },
    "b2b": {
        "label": "B2B / 工业品 / 企业服务",
        "question": "为什么 {c} 的{metric}增长停滞，卡在客户旅程的哪一段？",
        "branches": [
            ("市场与线索", ["目标客户画像是否过宽（ICP 不清）",
                            "线索量 vs 有效线索率",
                            "获客渠道结构是否单一"]),
            ("销售转化", ["销售周期长度 vs 同行",
                          "赢单率与丢单原因分布",
                          "报价与竞品价格带位置"]),
            ("交付与留存", ["续约率 / 复购率与行业基准差",
                            "客户使用深度（激活率）",
                            "交付毛利是否被定制拖垮"]),
            ("品牌与信任资产", ["行业认知度与决策人触达情况",
                                "案例与背书资产是否可用",
                                "渠道伙伴网络覆盖"]),
        ],
    },
    "platform": {
        "label": "平台 / 互联网 / 内容",
        "question": "为什么 {c} 的{metric}增速落后于同类平台，飞轮哪一环转得慢？",
        "branches": [
            ("供给端", ["供给规模与密度",
                        "供给质量（供给侧留存/评分）",
                        "供给获取成本"]),
            ("需求端", ["新客获取成本与留存曲线",
                        "活跃频次与时长",
                        "需求侧结构（地域/人群覆盖）"]),
            ("匹配与变现", ["匹配效率（转化率/履约率）",
                            "变现率（ARPU/佣金/广告加载）",
                            "补贴依赖度"]),
            ("生态与规模效应", ["网络效应强度（跨边弹性）",
                                "内容/数据资产的复用程度",
                                "监管与合规约束"]),
        ],
    },
}


def build_tree(company, btype, metric):
    cfg = TREES[btype]
    L = []
    L.append("# 议题树与假设台账（Day-1 版）\n")
    L.append("> 用法：这一页必须在写正文之前产出；正文每一章的结论都要回指它证实/证伪了哪一支。\n")
    L.append(f"## 一、核心问题（Governing Question）\n")
    L.append(f"**{cfg['question'].format(c=company, metric=metric)}**\n")
    L.append("- 量化目标：<填：例如 12 个月内把 X 从 A 提到 B>")
    L.append("- 时限：<填>")
    L.append("- 不解决会怎样：<填：一句话给出代价>\n")
    L.append("## 二、MECE 分解（营收恒等式自检）\n")
    L.append("`营收 = 流量 × 转化率 × 客单 × 复购`　→ 四因子互斥且穷尽；下面四个分支分别对应四因子的主要缺口。\n")
    L.append("**是否遗漏检查**：除上述分支外，是否存在政策/技术替代/渠道结构性变化等外部断裂点？（若有，新增第五分支并说明为何不与前四支重叠）\n")
    L.append("## 三、分支与子问题\n")
    for i, (name, subs) in enumerate(cfg["branches"], 1):
        L.append(f"### 分支 {i}｜{name}\n")
        L.append(f"**假设（可被证伪的断言）**：<填：例如「{name}的缺口主要来自 X，因为 Y」>")
        L.append(f"**反证条件**：<填：什么数据出现，这条假设就作废>")
        L.append(f"**若假设成立，结论是**：<填>")
        L.append("")
        for j, s in enumerate(subs, 1):
            L.append(f"- 子问题 {i}.{j}：{s}")
            L.append(f"  - 要什么数据：<填>")
            L.append(f"  - 去哪拿：<填：年报/行业报告/平台公开数据/第三方数据库>")
            L.append(f"  - 什么结果说明什么：<填>")
        L.append("")
    L.append("## 四、假设台账\n")
    L.append("| # | 假设 | 验证方式 | 若为假，结论改为 | 状态 |")
    L.append("|---|---|---|---|---|")
    L.append("| H1 | <填> | <填> | <填> | 待验证 |")
    L.append("| H2 | <填> | <填> | <填> | 待验证 |")
    L.append("| H3 | <填> | <填> | <填> | 待验证 |\n")
    L.append("## 五、被证伪假设记录（必须留档）\n")
    L.append("| # | 原假设 | 被什么数据推翻 | 对结论的影响 |")
    L.append("|---|---|---|---|")
    L.append("| — | <填> | <填> | <填> |\n")
    return "\n".join(L)


def check_tree(path, min_fail=0):
    text = read_text(path)
    hs = headings(text)
    top, sub = [], []
    for lvl, title in hs:
        if lvl == 2:
            top.append(title)
        elif lvl == 3:
            sub.append(title)

    branch_lvl2 = [t for t in top if re.search(r"分支|Branch", t)]
    n = len(branch_lvl2) or len([t for t in sub if re.search(r"分支", t)])
    falsify = sum(1 for h in FALSIFY_HINTS if h in text)
    misscheck = [h for h in MISS_CHECK_HINTS if h in text]
    has_ledger = bool(re.search(r"假设台账", text))
    has_falsified = bool(re.search(r"被证伪|证伪假设|推翻的假设", text))
    has_question = bool(re.search(r"核心问题|Governing", text))

    items = [
        ("核心问题存在", has_question, "有独立段落写明 governing question"),
        ("顶层分支 3±2", 1 <= n <= 5, f"实际检出 {n} 支（应为 2–5，3 最佳）"),
        ("反证条件齐备", falsify >= 3, f"命中「推翻/证伪/若不成立」类表述 {falsify} 处（需 ≥3）"),
        ("遗漏检查句存在", bool(misscheck), f"命中：{misscheck[:2] or '无'}"),
        ("假设台账存在", has_ledger, "需含「假设|验证方式|若为假结论改为」三列"),
        ("被证伪记录存在", has_falsified, "被推翻的假设必须留档，不允许只留成功项"),
    ]

    print("【议题树校验】", os.path.basename(path))
    ok_all = True
    for name, ok, note in items:
        print(f"  [{'OK' if ok else 'NG'}] {name} — {note}")
        ok_all = ok_all and ok
    print(f"\n判定：{'通过（可进入事实检索阶段）' if ok_all else '不通过——议题树不合格，不允许开写正文'}")
    return 0 if ok_all else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default="<公司>")
    ap.add_argument("--type", dest="btype", default="b2c", choices=list(TREES.keys()))
    ap.add_argument("--metric", default="营收与利润")
    ap.add_argument("--check", help="校验已有议题树文件")
    ap.add_argument("--types", action="store_true")
    a = ap.parse_args()

    if a.types:
        for k, v in TREES.items():
            print(f"  {k:9s} {v['label']}")
        return 0
    if a.check:
        return check_tree(a.check)
    print(build_tree(a.company, a.btype, a.metric))
    return 0


if __name__ == "__main__":
    sys.exit(main())
