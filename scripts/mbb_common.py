# -*- coding: utf-8 -*-
"""mbb_common.py — MBB/4A 审计的共用常量与判据函数（只此一处，改这里全局生效）

v2 · 2026-09-19 红队评审后加固：
  · 来源判据不再认「裸词来源」——必须能指向可核验主体（机构名/《报告》/URL/可信度标记），
    且排除自我指认（「来源：见附录」）与泛引用（「来源：公开」）。
  · 中文数字（八千家/九万元/百分之二十）也进「含数字句」分母，堵住「用中文数字逃逸来源检查」。
  · 结论句判定收紧：去掉「可/能/将/使/只/仅」等弱单字；数字必须带单位才算结论。
"""

import re

OK, NG, WARN = "OK", "NG", "WARN"

# ── 标题判定 ────────────────────────────────────────────────
TOPIC_WORDS = [
    "概览", "概述", "背景", "介绍", "现状", "情况", "分析", "意义",
    "总结", "说明", "综述", "研究", "回顾", "展望", "基本情况", "相关情况",
]

# 强结论动词（多字，可信）——弱单字（可/能/将/使/只/仅/应）已移除，避免「渠道能力分析」误判
CONCLUSION_VERBS = [
    "应为", "必须", "需要", "高于", "低于", "达到", "导致", "带来", "源于",
    "集中", "依赖", "下降", "上升", "领先", "落后", "拉动", "拖累", "决定",
    "归因", "表明", "意味着", "取决于", "跑赢", "跑输", "来自", "超过", "不足",
    "缺口", "拖住", "撑起", "卡在", "取舍", "放弃", "支撑", "回答", "指向",
    "而非", "不是", "唯一", "主要", "占到", "贡献",
]

# 「是/为」类系动词：只有在标题足够长（≥6 个中文字符）时才认，避免「品牌是谁」蒙混
COPULA = ["是", "为"]

# 数字必须带单位才算「结论句里的数字」，避免「市场概览 2025」蒙混
UNIT_NUM_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|倍|成|个百分点|万元|亿元|万|亿|元|人|家|个|天|月|年|次|点|条|分)"
)

# 中文数字 + 单位（用于分母，不用于结论句判定）
CN_UNIT_NUM_RE = re.compile(
    r"[一二三四五六七八九十百千万亿半两0-9]+(?:成|倍|个百分点|万元|亿元|万|亿|元|人|家|个|天|月|年|次)"
    r"|百分之[一二三四五六七八九十百千0-9]+"
)

# ── 来源判据（v2 加固）─────────────────────────────────────
CONFIDENCE = ["【已核实】", "【行业认知】", "【未核实】"]

# 可信度标记：直接算「有来源」
TRUST_MARKS = ["【已核实】", "【行业认知】"]

# 可核验主体：机构名 / 报告名 / 平台名 / URL
VERIFIABLE_HINTS = [
    "年报", "年度报告", "财报", "招股书", "白皮书", "公告", "官网", "统计公报", "国家统计局",
    "基准报告", "行业深度", "深度报告", "转引", "报道",
    "艾瑞", "易观", "QuestMobile", "Statista", "Nielsen", "Euromonitor", "CBNData",
    "艾媒", "SimilarWeb", "Sensor Tower", "天眼查", "企查查", "Wind", "同花顺",
    "媒体报道", "新闻报道", "第三方", "公开披露", "投资者关系", "访谈纪要", "调研",
    "本报告测算", "本报告整理", "本报告方法说明", "本报告分析", "测算",
]

# 「来源：」后面若只出现这些内容 → 视为不可核验（自我指认/泛引用）
FAKE_SOURCE_WORDS = [
    "见附录", "见前文", "同上", "略", "无", "网络", "公开资料", "公开", "不明",
    "待补", "百度", "据了解", "不详", "未知", "网上", "见下表", "见上文",
]

# 泛引用（不合格来源写法，硬错误）
VAGUE_SOURCES = [
    "来源：网络", "来源:网络", "据网络", "网上资料", "百度知道", "来源：公开资料",
    "来源：公开", "来源:公开", "据了解，", "据称", "有消息称", "来源：见附录",
    "来源：不详", "来源：未知",
]

# 内部过程文档泄漏（不得进交付稿）。注意：不用裸词「门禁」，避免误杀安防门禁行业报告
INTERNAL_LEAK = [
    "Agent 分工", "Agent分工", "多 Agent", "多Agent", "事实底稿", "裁决记录",
    "自检单", "门禁 13 项", "门禁清单", "施工说明", "内部文档", "本 skill",
    "skill 自检", "流程状态行", "任务规则表",
]

COMPLIANCE_WORDS = ["个人信息", "隐私", "同意", "AIGC", "AI 生成", "AI生成", "AI 参与", "AI 完成"]

# 未核实类标记（v3 加固：原来只认「【未核实】」，导致换标签即绕过）
UNVERIFIED_MARKS = ["【未核实】", "【未验证】", "【未经证实】", "【待补】", "【存疑】"]

# 自证来源（写在交付稿里的自我测算）——B1 用它计算「外部来源占比」，防止整篇自证
SELF_SOURCE_HINTS = [
    "本报告测算", "本报告整理", "本报告方法说明", "本报告分析", "本报告判断",
    "本报告提出", "本报告分类", "本报告建议", "本报告复核", "本报告自评",
]

# 不能算作「可查证条目」的引用方式（v3：附录来源清单不许用转引充数）
WEAK_CITE_WORDS = ["二手转引", "行业访谈转引", "未证实", "未查到", "待补", "据称", "据了解"]

HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$", re.M)
DIGIT_RE = re.compile(r"\d")
SENT_SPLIT_RE = re.compile(r"[。；;!?！？]")
CN_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def headings(text):
    """返回 [(level, title)]"""
    return [(len(m.group(1)), m.group(2).strip()) for m in HEADING_RE.finditer(text)]


def sections(text):
    """返回 [(title, level, body)]"""
    marks = list(HEADING_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(2).strip(), len(m.group(1)), text[start:end]))
    return out


def find_sections(text, keywords, max_level=3):
    """按关键词找章节，返回 [(title, level, body)]"""
    hits = []
    for title, level, body in sections(text):
        if level <= max_level and any(k in title for k in keywords):
            hits.append((title, level, body))
    return hits


def flat(text):
    t = re.sub(r"`{1,3}[^`]*`{1,3}", " ", text)
    t = re.sub(r"\|", " ", t)
    t = re.sub(r"[*_>#\-]{1,}", " ", t)
    return t


def has_number(s):
    """句子是否含数字（ASCII 或中文数字+单位）"""
    return bool(DIGIT_RE.search(s) or CN_UNIT_NUM_RE.search(s))


def numbered_sentences(text):
    """返回叙述性含数字句子 [(行号, 句子)]（ASCII 与中文数字都算）。

    跳过代码块、表格行、标题行（结构化内容另有检查）。
    """
    out, in_code = [], False
    for i, line in enumerate(text.splitlines(), 1):
        raw = line.strip()
        if raw.startswith("```"):
            in_code = not in_code
            continue
        if in_code or raw.startswith(("|", "#", ">", "`")):
            continue
        for s in SENT_SPLIT_RE.split(raw):
            s = s.strip()
            if len(CN_CHAR_RE.findall(s)) < 4:
                continue
            if has_number(s):
                out.append((i, s))
    return out


FAKE_TAIL_RE = re.compile(
    r"^(见附录|见前文|见上文|见下表|同上|略|无|待补|不详|未知|网络|公开资料|公开|网上|百度|据了解)"
)


def _tail_is_fake(tail):
    """「来源：」后面的内容是否不可核验。

    只在开头命中才判假 —— 避免把「来源：本报告测算，口径见附录」误杀
    （它开头是可核验的测算口径，末尾的「见附录」只是补充说明）。
    """
    return bool(FAKE_TAIL_RE.match(tail.strip()))


def has_source(s):
    """v2：来源必须可核验。

    通过条件（任一）：
      1. 带可信度标记（【已核实】/【行业认知】）
      2. 「来源：」后跟 ≥2 字，且**开头不是**自我指认/泛引用（见 FAKE_TAIL_RE）
      3. 命中可核验主体（机构/报告/平台/测算口径）
      4. 含 URL 或《…》报告名
    """
    if any(m in s for m in TRUST_MARKS):
        return True
    if re.search(r"https?://", s) or re.search(r"《[^》]{2,}》", s):
        return True
    m = re.search(r"来源\s*[:：]\s*([^）)。；\n]{1,40})", s)
    if m:
        tail = m.group(1).strip()
        if len(tail) >= 2 and not _tail_is_fake(tail):
            return True
    return any(h in s for h in VERIFIABLE_HINTS)


def is_fake_source(s):
    """自我指认/泛引用来源（例如「来源：见附录」「来源：网络」）"""
    m = re.search(r"来源\s*[:：]\s*([^）)。；\n]{0,40})", s)
    if m and _tail_is_fake(m.group(1)):
        return True
    return any(v in s for v in VAGUE_SOURCES)


def is_conclusion_title(title):
    """结论句判定 v2：数字须带单位；弱单字动词不算；系动词要求标题足够长"""
    t = title.strip()
    if UNIT_NUM_RE.search(t):
        return True
    if any(v in t for v in CONCLUSION_VERBS):
        return True
    if len(CN_CHAR_RE.findall(t)) >= 6 and any(c in t for c in COPULA):
        return True
    return False


def is_topic_title(title):
    """主题词标题（action title 的反面）"""
    if is_conclusion_title(title):
        return False
    return any(w in title for w in TOPIC_WORDS)


def has_placeholder(text):
    """占位符残留（量化目标写了「从 A 提到 B」这类未填值）"""
    return bool(re.search(r"从\s*A\s*(提|升)?到\s*B|<\s*填|【待补】|XXX|待填|TODO", text))


def count_leaks(text):
    return [w for w in INTERNAL_LEAK if w in text]


def body_word_count(text):
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]+", text))
    return cjk + latin
