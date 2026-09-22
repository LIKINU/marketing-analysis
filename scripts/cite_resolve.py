#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cite_resolve.py — 引用可解析性：把交付稿里的每个引用拿去「存在性核验」

P0 背景：德勤因 14 处虚假引用退款、毕马威 45 条引用仅 5 条准确而撤稿 ——
「引用不可追溯」是国际上唯一被公开惩罚过的红线。现有审计只查「有没有写来源」，
查不出「引用了不存在的版本号/章节」（实测发生过：正文引用被引文件里根本不存在的
「方案 v1.1 修订说明」）。本脚本补这一格：逐个引用问「这东西真的存在吗」。

抽取五类引用：
  1 URL（http/https）
  2 《书名/报告名》（法规/证照/标准类名称不算书目，见 LAW_SUFFIX）
  3 版本号（v1.0 / V2 / 版本 1.1 / 第二版 / 最新修订版 / 1.1 修订说明）
  4 章节·附件（§8.2 / §三 / 附件 A.0 / 第 12 章；「第 12 周」是周次，抽取后忽略）
  5 显式来源标注（来源：…、【已核实】、【行业认知】、【品牌方自述】）

校验规则（v2，红队加固）：
  A URL      —— 须在同一文档「来源清单」章节内出现；仅见于正文 → WARN
  B 《书名》 —— 须在来源清单章节里找到同名条目；否则 NG（幻影书目）
               法规/条例/办法/许可证/标准/准则/规范类名称不参与书目核验
  C 被引文件 —— 版本号 / §章节 / 附件 引用，须在「本报告自身章节 ∪ --dep 依赖文件」里
               真实存在；否则 NG（硬错误 = 幻影引用）
  D 自证来源 —— 本报告测算/整理/方法说明/查证记录…（含自指章节「§8.4 第 3 条」），
               单独计数，不参与通过判定

v2 修掉的绕过（红队实测）：
  · 删除「同一行挂一本来源清单内的书目即豁免」——幻影引用不能靠同行贴一本真书目洗白。
    仅当显式标注「外部来源：X」且 X 不是依赖文件时才降级 WARN，且降级项仍留在分母里。
  · 版本号识别补中文/无 v 表述（第二版／最新修订版／1.1 修订说明），但**仅当同行出现
    被引文件名时才作为引用**（否则「最新版本」这类普通词会被误当引用）。
  · 来源清单白名单收紧：只认文档后 30%、且标题含 来源清单/数据来源/参考文献/参考资料
    的 ≥2 级标题；仅含「附录」的标题不算，H1 不算（防止把幻影书目抄进自己的附录）。
  · 不传 --dep 时，出现「被引文件名 + 版本/章节」形态直接判硬错误（依赖型引用无从核验）。
  · --min 下限锁 0.5。
  · 依赖文件里的**否定句**不算「存在」：本文件写的「只有 v1.0 与 v1.1，不存在 v1.2
    或任何『修订说明』独立文档」，不能让正文的 v1.2 /「v1.1 修订说明」借它洗白
    （否定从句先做等长空白化，再做版本号与版本后缀核验）。

v2 消掉的误杀（红队实测）：
  · dep_has_section 兼收 # 标题、**2.9 成本结构** 行内加粗编号、行首 2.9 编号、
    附件 A.0、中文编号 一、二、。
  · 法规/证照名带《》不再判幻影书目。
  · 机构报告章节（「东北证券深度报告 §3.2」）降级 WARN，不再判死。
  · 自指章节（「来源：本报告测算（§8.4 第 3 条）」）归自证类，不判。

不联网：URL 只判断「是否被本文件的来源清单收录」，不发请求。

────────────────────────────────────────────────────────────
v3 · 2026-09-19 独立验证后重做语义：**判据是三态，不是两态**

核心原则：**判据的结论依赖审计者输入时，绝不能把「审计者的错误」算成「报告的红线」。**

  ① 已验证 · 通过      --dep 提供且全部可读，hard == 0 且 rate ≥ --min
  ② 已验证 · 不通过    --dep 可读，hard > 0（幻影引用）→ 报告的硬错误
  ③ 未验证（阻断）      报告有依赖型引用但未提供 --dep；--dep 路径不存在/读取失败；
                       或报告声明的被引文件名与 --dep 对不上
                       → 不是报告的硬错误，但列入阻断项、不可放行（exit 1），
                         且 rate 记 0.0 并置 block=true（fail-closed，避免下游误读）

v3 修掉的绕过：
  · 自造被引文件洗白：拿一份假「被引文件」当 --dep，让幻影版本号/章节在里面「存在」。
    → 前置一致性检查：报告声明的被引文件名（《书名号》形式）必须与 --dep 之一对得上，
      否则走状态 ③（阻断），不再产出「硬错误」也不放行。
  · 来源清单自证：把幻影书目抄进报告自己的来源清单 → 原判「来源清单有同名条目」即 OK。
    → 改为：仅由报告自身来源清单自证、且无法与 --dep 内容或具名可查证域名对应的《书目》，
      记 **待核验（PEND）**，不计入 resolved 分子，使 rate 下降而不是虚高。
  · 词形缺口：「品牌方方案 版本号 9.9」（无 v、无「修订说明」后缀）原来抽不出来。
    → 版本判据改为「版本/版 + 紧邻编号」，见 VER_NUM_RE / VER_CN_RE。

v3 消掉的误杀：
  · 审计者传错 --dep（指向无关文件或不存在路径）原来被算成报告的 100 处硬错误 → 打回。
    → 改判状态 ③「未验证（阻断）」：exit 1 但不扣 E6 分、不打「硬错误」标签。
  · 引用分母随 --dep 变化（283 vs 305）→ 抽取与 dep 完全解耦，total 只由报告本身决定。
  · 来源清单条目自身进分母造成系统性虚高 → 来源清单章节内的条目不计入分母。

────────────────────────────────────────────────────────────
v4 · 2026-09-19 堵住「信任根漏洞」：**被审者不能自己出题自己判卷**

v3 之后仍有一条洗白路径：`--dep` 是**跑检查的人交进来的**。被审者只要在真被引文件之外
再补一份「假被引文件」（里面写着幻影版本号 v9.9 / 幻影章节），v3 的存在性比对就会在
假文件里「找到」这些幻影引用 → hard 0 → 判「通过」。检查因此变成自己出题自己判卷。

v4 的核心原则（不改 v3 的三态设计，只**收紧**状态 ① 的门槛）：
  **机械检查只能比对，不能建立真相。所以只有「审计者独立持源 + 哈希可核」时，
    才允许说「已验证通过」。**

新增两个参数：
  --dep-trust {auditor,author}   声明本次 --dep 文件的来源归属，**默认 author（从严）**
                                 author  = 由被审者（报告作者）提供
                                 auditor = 审计者独立取得
  --registry <path>              被引文件哈希登记表（机器可读），
                                 默认 <skill>/assets/dep-registry.json

三态判定（v4）：
  ② 已验证·不通过（幻影引用）  dep 可读 且 hard > 0
                             → 报告硬错误、打回。**任何归属下都成立**：
                               引用对不上就是缺陷，与谁交的源无关。
  ① 已验证·通过              dep 可读、hard == 0、rate ≥ 门槛，**且**
                             · 全部 --dep 都声明为 --dep-trust auditor，**且**
                             · 每个 dep 的 sha256 都能在 registry 里匹配到同名条目
                             → 计满分。
  ③ 未验证（阻断）            其余一切情况（未声明 auditor／哈希未登记／哈希不匹配／
                             路径无效／未传 dep）→ 阻断放行、**不扣报告分**，
                             文案必须**指明缺哪一项**并列出实际 sha256 前 16 位。

  关键：**即使 hard == 0，只要归属或哈希这一环不成立，就必须落到 ③ 而不能判 ①。**
  （rate < 门槛 属报告自身的缺陷，与来源归属无关，仍按「不通过」打回。）

用法:
  python cite_resolve.py report.md
  python cite_resolve.py report.md --dep outputs/品牌方方案.md --dep outputs/喵鲜日记-议题树.md
  python cite_resolve.py report.md --dep X.md --dep-trust auditor --registry assets/dep-registry.json
  python cite_resolve.py report.md --min 0.9 --json cite.json

退出码: 状态 ① → 0；状态 ② / ③ → 1
"""

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mbb_common import (  # noqa: E402
    HEADING_RE, NG, OK, WARN, SELF_SOURCE_HINTS, TRUST_MARKS, headings, read_text,
)

# ── 抽取正则 ────────────────────────────────────────────────
URL_RE = re.compile(r"https?://[^\s)\）\]】>」》\"'，。；、]+")
BOOK_RE = re.compile(r"《([^》\n]{2,60})》")

# 第三态用到的标记：待核验（不计入 resolved 分子，也不算硬错误）
PEND = "PEND"

# 占位 / 不可离线核验的主机名（具名可查证域名的反面）
PLACEHOLDER_HOST_RE = re.compile(
    r"^(?:example\.(?:com|org|net|edu)|test\.(?:com|org|net)|localhost|invalid|"
    r"本机|www\.example\.(?:com|org|net)|\d{1,3}(?:\.\d{1,3}){3})$", re.I)

# 版本号：v1.0 / V2 / 版本 1.1 / 版本号 1.1 / 版 1.1 / 第二版 / 第 9.9 版 / 最新修订版 / 1.1 修订说明
# v3 词形放宽：判据基于「版本/版 + 紧邻编号」，不再只认 `v` 或「修订说明」后缀
VER_V_RE = re.compile(r"(?<![A-Za-z0-9])[vV](\d+(?:\.\d+)*)")
VER_CN_RE = re.compile(r"(?:版本|版)\s*号?\s*[vV]?\s*(\d+(?:\.\d+)+)")
VER_NUM_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)+)\s*(?:版|修订说明|修订稿|修订版|修订)")
VER_ORD_RE = re.compile(r"第\s*(\d+(?:\.\d+)*|[一二三四五六七八九十百]+)\s*版")
VER_LABEL_RE = re.compile(
    r"(?:最新|最近|首次|二次|三次)?"
    r"(?:修订版|修订说明|修订稿|试行版|试行稿|正式版|定稿版|终版|最终版|初稿|草稿)")
# 版本后缀前面已经跟了版本号 → 后缀不是独立版本
VER_PRE_RE = re.compile(r"(?:[vV]\d+(?:\.\d+)*|\d+(?:\.\d+)+|版本)\s*$")

SEC_RE = re.compile(r"§\s*(\d+(?:\.\d+)*|[一二三四五六七八九十]+)")
ATTACH_RE = re.compile(r"附件\s*([A-Za-z]\.?\d+(?:\.\d+)*|\d+(?:\.\d+)*)")
CHAPTER_RE = re.compile(r"第\s*(\d+)\s*[章节]")
WEEK_RE = re.compile(r"第\s*\d+\s*周")                             # 周次不算章节 → 忽略
SRC_RE = re.compile(r"来源\s*[:：]\s*([^）)\n；;]{1,60})")

SRC_MARKS = list(TRUST_MARKS) + ["【品牌方自述】"]
UNVERIFIED_MARKS = ["【未核实】", "【未验证】", "【未经证实】"]

# 来源主体不可核验（自我指认/泛引用）——source_ledger 已判硬错误，这里只降级为 WARN
GENERIC_SOURCES = [
    "见附录", "见前文", "见上文", "见下表", "同上", "略", "待补", "不详", "未知",
    "网络", "公开资料", "公开", "网上", "百度", "据了解", "无",
]

# ── 来源清单章节（A/B 两类判定依据）· 收紧 ──────────────────
# 只认这四个关键词；「附录」单独出现不算（附录常被用来塞幻影书目）
SRC_SECTION_RE = re.compile(r"来源清单|数据来源|参考文献|参考资料")
SRC_TAIL_RATIO = 0.7          # 只在文档后 30% 内认来源清单

# ── 法规/证照/标准类《…》：不是「书目」，不参与幻影书目判定 ──
LAW_SUFFIX = (
    "法", "条例", "办法", "许可证", "标准", "准则", "规范", "规定", "细则",
    "指引", "意见", "通知", "公告", "守则", "公约", "大纲",
)

# 文档自身的版本声明（不是引用，不进引用集合）
SELF_VER_HEADS = [
    "版本", "变更记录", "修订记录", "修订历史", "变更历史",
    "更新记录", "文档信息", "文档控制",
]

# ── 「被引文件名」识别（用于判断版本/章节是否属于某个被引文件）──
DOC_TAIL = (r"(?:方案|报告|白皮书|蓝皮书|说明书|手册|计划书|计划|清单|台账|纪要|提案"
            r"|年鉴|年报|招股书|目录)")
PLAIN_DOC_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9·・]{0,20}" + DOC_TAIL)
SELF_DOC_PREFIX = (
    "本报告", "本方案", "该报告", "该方案", "本稿", "本文", "上述报告", "上述方案",
    "这份报告", "这份方案", "本拆解",
)
# 过泛、不能单独作为「被引文件名」的尾巴
DOC_STOP = {
    "报告", "年报", "白皮书", "蓝皮书", "说明书", "手册", "计划", "清单", "台账",
    "纪要", "提案", "年鉴", "招股书", "目录", "计划书",
}

# 显式外部来源标注 / 紧邻的机构报告署名（两者都只能降 WARN）
# 「外部来源：X」只覆盖 X 自身范围内的引用，不覆盖同一行的其它引用
EXT_MARK_RE = re.compile(r"外部(?:来源|资料|数据|引用)\s*[:：]\s*([^）)\n；;，,。、：:]{1,40})")
EXT_DOCTYPE_RE = re.compile(
    r"(?:深度报告|研究报告|研报|行业报告|年度报告|年报|白皮书|蓝皮书|招股说明书"
    r"|招股书|统计公报|财报|公告|调研纪要|访谈纪要|行业深度)\s*$")
EXT_WINDOW = 24

MIN_FLOOR = 0.5               # --min 下限锁

# ── v4：来源归属 + 哈希登记（决定「是否允许说已验证通过」）────────
# 默认 registry：<skill>/assets/dep-registry.json（本脚本在 <skill>/scripts/ 下）
DEFAULT_REGISTRY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "dep-registry.json")

DEP_TRUST_CHOICES = ("auditor", "author")
DEP_TRUST_DEFAULT = "author"        # 从严：不声明即视为「被审者提供」
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def sha256_file(path):
    """文件的 SHA-256（十六进制小写）——与 `shasum -a 256` 同值"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def load_registry(path):
    """读哈希登记表 → (名字→sha256 字典, 错误说明或 '')

    名字用 basename 的**小写**做键。同名条目取第一条。
    结构无效 / 读不到时返回空表 + 错误说明（**绝不当作「通过」**）。
    """
    if not path:
        return {}, "未指定 registry 路径"
    if not os.path.exists(path):
        return {}, f"registry 文件不存在（{path}）"
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return {}, f"registry 无法解析（{e}）"
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return {}, "registry 结构无效（缺 entries 数组）"
    out = {}
    for e in data["entries"]:
        if not isinstance(e, dict):
            continue
        fn = str(e.get("file", "")).strip()
        if not fn:
            continue
        out.setdefault(os.path.basename(fn).lower(), str(e.get("sha256", "")).strip().lower())
    return out, ""


def dep_trust_status(dep_paths, dep_trust, registry_path):
    """本次 --dep 的「归属 + 哈希」是否成立 → dict

    ok       : 是否允许把状态判成 ①（已验证·通过）
    missing  : 缺失项文案列表（每条都以「未声明归属／哈希未登记／哈希不匹配 …」开头）
    actual   : {basename: 实际 sha256 或 ''}
    registry_error : registry 读不到时的说明（'' 表示正常）

    没有 --dep 时本检查是空操作（没有源可核，不因缺归属而阻断）。
    """
    entries, reg_err = load_registry(registry_path)
    actual, missing = {}, []
    for p in dep_paths:
        base = os.path.basename(p)
        try:
            actual[base] = sha256_file(p)
        except OSError:
            actual[base] = ""
    if dep_paths and dep_trust != "auditor":
        missing.append(
            "未声明归属：本次 --dep 未声明为审计者独立取得（--dep-trust 当前为 "
            f"'{dep_trust}'，默认 author＝由被审者提供）——被审者可同时交上伪造源，"
            "检查就成了自己出题自己判卷")
    for p in dep_paths:
        base = os.path.basename(p)
        sh = actual.get(base, "")
        if not sh:
            missing.append(f"哈希未登记：{base} 不可读，无法计算 sha256")
            continue
        reg = entries.get(base.lower())
        if reg is None:
            tail = f"；registry 读取异常：{reg_err}" if reg_err else ""
            missing.append(
                f"哈希未登记：{base} 不在 registry（{registry_path}）里"
                f"；实际 sha256={sh[:16]}…{tail}")
        elif not SHA256_RE.fullmatch(reg):
            missing.append(
                f"哈希未登记：{base} 的 registry 条目 sha256 字段无效"
                f"（{reg or '空'}）；实际 sha256={sh[:16]}…")
        elif reg != sh:
            missing.append(
                f"哈希不匹配：{base} 登记值 sha256={reg[:16]}… "
                f"≠ 实际 sha256={sh[:16]}…")
    return {"ok": not missing, "missing": missing, "actual": actual,
            "registry_error": reg_err}


# 依赖文件里的否定句：「本文件只有 v1.0 与 v1.1，不存在 v1.2 或任何『修订说明』独立文档」——
# 否定语境里的版本号/版本后缀**不算存在**，否则幻影版本号能借这句自我洗白。
NEG_CLAUSE_RE = re.compile(r"(?:不存在|并没有|没有|不含|未出现|从未)[^。；\n]{0,28}")


def _blank_negations(text):
    """把否定从句替换成等长空白（保长度，正则位置不变）"""
    return NEG_CLAUSE_RE.sub(lambda m: " " * len(m.group(0)), text)


def _label_after(text, end):
    """版本号后面紧跟的版本后缀（「v9.9 修订说明」→ 修订说明）"""
    seg = re.sub(r"^[\s*【]", "", text[end:end + 12])
    m = VER_LABEL_RE.match(seg)
    return m.group(0) if m else ""


def _label_core(name):
    """去掉「最新/最近/…」前缀后的版本后缀本体"""
    return re.sub(r"^(?:最新|最近|首次|二次|三次)", "", name.strip())


def _norm_ver(tok):
    t = tok.strip().lower()
    if t.startswith("v"):
        t = t[1:]
    return t.replace(" ", "")


def _is_self_ver_title(title):
    tt = re.sub(r"^[0-9一二三四五六七八九十]+\s*[、\.．)）]\s*", "", title.strip())
    return any(tt.startswith(w) or (tt.endswith(w) and len(tt) <= 8) for w in SELF_VER_HEADS)


def section_ranges(text):
    """[(标题, 层级, 起始行, 结束行)]（行号从 1 起；范围含子章节）"""
    marks = list(HEADING_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        lvl = len(m.group(1))
        end = len(text)
        for j in range(i + 1, len(marks)):
            if len(marks[j].group(1)) <= lvl:
                end = marks[j].start()
                break
        out.append((m.group(2).strip(), lvl,
                    text.count("\n", 0, m.start()) + 1,
                    text.count("\n", 0, end) + 1))
    return out


def self_version_lines(text):
    """文档自述版本所在行（头部元信息 + 「版本/变更记录」章节）——不算引用"""
    hits = set()
    lines = text.splitlines()
    for i, ln in enumerate(lines[:12], 1):
        if ln.lstrip().startswith(">") and "版本" in ln:
            hits.add(i)
    for title, lvl, s, e in section_ranges(text):
        if lvl <= 3 and _is_self_ver_title(title):
            hits.update(range(s, e + 1))
    return hits


def src_line_set(text):
    """(来源清单覆盖的行号集合, 命中的标题列表)

    收紧后的判据：**文档后 30%** 且标题含 来源清单|数据来源|参考文献|参考资料 的
    ≥2 级标题。H1 不算；只含「附录」的标题不算。
    """
    lines, titles = set(), []
    total = len(text.splitlines())
    cutoff = total * SRC_TAIL_RATIO
    for title, lvl, s, e in section_ranges(text):
        if lvl < 2 or not SRC_SECTION_RE.search(title):
            continue
        if s < cutoff:
            continue
        lines.update(range(s, e + 1))
        titles.append(title)
    return lines, titles


def is_law_book(name):
    """法规/证照/标准类《…》——不是书目，不判幻影书目"""
    n = name.strip()
    if any(k in n for k in ("报告", "白皮书", "蓝皮书", "年鉴", "指数", "数据")):
        return False
    return n.endswith(LAW_SUFFIX)


# ── v3：URL 可查证性 / 来源清单自证 / 前置一致性检查 ────────
def _url_host(u):
    m = re.match(r"https?://([^/?#]+)", u)
    if not m:
        return ""
    h = m.group(1).rsplit("@", 1)[-1].split(":")[0].strip(".").lower()
    return h


def is_verifiable_url(u):
    """具名可查证域名——占位域名 / localhost / 裸 IP / 无点主机名一律不算"""
    h = _url_host(u)
    if not h or PLACEHOLDER_HOST_RE.match(h):
        return False
    parts = h.split(".")
    if len(parts) < 2 or not re.fullmatch(r"[a-z]{2,}", parts[-1]):
        return False
    return True


def _in_listed(name, listed):
    """该《书名》是否出现在报告自身的来源清单里"""
    return name in listed or (len(name) >= 4 and any(name in b for b in listed))


def _norm_in(name, blob):
    """标准化后是否出现在 --dep 的正文里（blob 已去空白、已抹否定从句）"""
    n = re.sub(r"\s+", "", name)
    return len(n) >= 2 and n in blob


def _listed_entry_has_verifiable_url(name, lines, src_lines):
    """来源清单里提到该书目的那一行，是否附了具名可查证域名"""
    for ln in src_lines:
        if not (0 < ln <= len(lines)) or name not in lines[ln - 1]:
            continue
        for m in URL_RE.finditer(lines[ln - 1]):
            if is_verifiable_url(m.group(0)):
                return True
    return False


DECL_DEP_RE = re.compile(
    r"(?:被引文件|引用文件|依赖文件|拆解对象|分析对象|输入文件|参考文件|底稿文件)"
    r"\s*[:：]\s*([^\n]{0,90})")


def declared_dep_docs(text, cites):
    """报告显式声明的「被引文件」（只取《书名号》形式，可被机械比对）

    两类声明：
      (a) 元信息/正文里的「拆解对象：…《X》」「被引文件：…《X》」
      (b) 紧贴出现在版本号 / 章节号引用之前的《X》（如「《X》 §3.2」「《X》 v1.1」）

    纯简称（如「品牌方方案」）**不参与比对**：它无法与文件名机械对齐，
    强行比对会把「正确的 --dep」误判成「对不上」。
    """
    names = []
    for m in DECL_DEP_RE.finditer(text):
        for b in BOOK_RE.finditer(m.group(1)):
            names.append(b.group(1).strip())
    toks_cache = {}
    for ln, kind, _node, _label, line, pos, _suffix in cites:
        if kind not in ("VER", "SEC"):
            continue
        if ln not in toks_cache:
            toks_cache[ln] = doc_tokens(line)
        for t in toks_cache[ln]:
            if t[2] and _tight_before(pos, t) and not is_law_book(t[1]):
                names.append(t[1].strip())
    out = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


def versions_in(text):
    """文本里出现的全部版本号（v3 词形：v9.9 / 版本号 9.9 / 版 9.9 / 第 9.9 版 / 9.9 修订说明）"""
    out = set()
    for rx in (VER_V_RE, VER_CN_RE, VER_NUM_RE):
        for m in rx.finditer(text):
            out.add(_norm_ver(m.group(1)))
    return out


# ── 依赖文件「章节索引」：不只认 # 标题 ─────────────────────
LEAD_NUM_RE = re.compile(
    r"^(?:§\s*|附件\s*)?"
    r"([A-Za-z]\.\d+(?:\.\d+)*|\d+\.\d+(?:\.\d+)*|[一二三四五六七八九十]+\s*[、\.．])\s*")


def _absorb(idx, s):
    """从一行标题/加粗编号行里抽出章节号（2.9 / 8.4 / A.0 / 一）"""
    t = re.sub(r"^#{1,6}\s*", "", s.strip())
    t = re.sub(r"^\*\*|\*\*$", "", t).strip()
    m = LEAD_NUM_RE.match(t)
    if not m:
        return
    num = m.group(1).rstrip("、.． ").strip()
    if num:
        idx.add(num.replace(" ", ""))


def section_index(text):
    """文档里的全部章节号集合（# 标题 + 行内加粗编号 + 行首编号 + 附件编号）"""
    idx = set()
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if re.match(r"^#{1,6}\s", s):
            _absorb(idx, s)
            continue
        m = re.fullmatch(r"\*\*(.+?)\*\*[：:]?", s)
        if m:
            _absorb(idx, m.group(1))
            continue
        if re.match(r"^(?:\*\*|附件\s*|§\s*)", s):
            _absorb(idx, s)
    return idx


def dep_has_section(node, sections):
    """章节号是否存在于给定章节索引。

    v2 起索引不再只来自 `#` 标题（原来只读 headings()，把 `**2.9 成本结构**`
    这类行内加粗编号的真实章节全判成幻影）——索引由 section_index() 统一产出：
    `#`/`##` 标题、`**2.9 成本结构**`、行首 `2.9 `、`附件 A.0`、中文编号 `一、二、`。
    `sections` 可以是依赖文件索引、本报告自身索引，或两者并集。
    """
    n = node
    for pre in ("§", "附件"):
        if n.startswith(pre):
            n = n[len(pre):]
    n = n.replace(" ", "")
    if not n:
        return True
    if n in sections:
        return True
    m = re.fullmatch(r"([A-Za-z])\.?(\d+(?:\.\d+)*)", n)
    if m:
        return f"{m.group(1)}.{m.group(2)}" in sections or f"{m.group(1)}{m.group(2)}" in sections
    return False


def doc_tokens(line):
    """行内「被引文件名」候选 → [(起点, 名称, 是否《…》)]"""
    toks = []
    for m in BOOK_RE.finditer(line):
        name = m.group(1).strip()
        if name:
            toks.append((m.start(), name, True))
    for m in PLAIN_DOC_RE.finditer(line):
        name = m.group(0).strip()
        if len(name) < 2 or name in DOC_STOP:
            continue
        if name.startswith(SELF_DOC_PREFIX):
            continue
        toks.append((m.start(), name, False))
    toks.sort()
    return toks


def _nearest_doc(toks, pos):
    left = [t for t in toks if t[0] < pos]
    if left:
        return max(left, key=lambda t: t[0])
    right = [t for t in toks if t[0] > pos]
    if right:
        return min(right, key=lambda t: t[0])
    return None


def _tight_before(pos, tok):
    """被引文件名是否紧贴在该 token 前面（如「深度报告 §3.2」）"""
    return 0 < pos - tok[0] <= len(tok[1]) + EXT_WINDOW


def _ext_attr_before(line, pos):
    """§ 前面紧邻的是「机构报告」而不是本依赖文件 → 离线无法核验

    容忍书名号与「的/里的/中的」「见/参见」等连接成分，
    以覆盖「东北证券《宠物食品行业深度》 里的 §3.2」这类写法。
    """
    w = line[max(0, pos - EXT_WINDOW):pos]
    for _ in range(3):
        w = re.sub(r"[\s]+$", "", w)
        w = re.sub(r"(?:的|里的|中的|见|参见|另见)$", "", w)
        w = re.sub(r"[》」】\)）]+$", "", w)
    return bool(EXT_DOCTYPE_RE.search(w))


def _is_dep_doc(name, aliases):
    n = name.replace(" ", "")
    for a in aliases:
        an = a.replace(" ", "")
        if len(an) >= 4 and an in n:
            return True
        if len(n) >= 4 and n in an:
            return True
    return False


def _is_self_source(tail):
    return tail.startswith("本报告") or any(h in tail for h in SELF_SOURCE_HINTS)


def _looks_ref(tail):
    """来源尾巴里已经含了可单独校验的引用（URL/《》/版本/章节）→ 不再重复计 SRC"""
    return bool(URL_RE.search(tail) or BOOK_RE.search(tail)
                or VER_V_RE.search(tail) or VER_CN_RE.search(tail)
                or VER_NUM_RE.search(tail) or VER_ORD_RE.search(tail)
                or VER_LABEL_RE.search(tail)
                or SEC_RE.search(tail) or ATTACH_RE.search(tail))


def extract(text, self_lines, rep_sections, src_lines):
    """返回 (引用列表, D 类自证列表, 被忽略的周次引用数)

    引用 = (行号, 类别, 节点标识, 展示名, 原文行, 节点在行内的列号, 版本后缀)

    v3：**抽取与 --dep 完全解耦**（total 不再随 --dep 变化）——
      · 「自带来源提示词 + 章节在本报告内存在」的自指章节，抽取阶段即归 D 类，不因 dep 缺失而回灌分母；
      · 来源清单章节内的条目自身不计入分母（否则「把书目抄一遍」就能虚高可解析率）。
    """
    cites, seen = [], set()
    self_src, self_seen, week_ignored = [], set(), 0
    in_code = False

    def add(ln, kind, node, label, line, pos, suffix=""):
        key = (ln, kind, node)
        if key not in seen:
            seen.add(key)
            cites.append((ln, kind, node, label, line, pos, suffix))

    for ln, raw in enumerate(text.splitlines(), 1):
        if raw.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or not raw.strip():
            continue
        line = raw.strip()
        # 等长掩码：既挡掉 URL 内部的《》/§，又不打乱后续 token 的列号
        masked = URL_RE.sub(lambda m: " " * len(m.group(0)), line)
        week_ignored += len(WEEK_RE.findall(masked))

        # 来源清单条目自身不计入分母
        if ln in src_lines:
            continue

        is_self_ver = ln in self_lines
        toks = doc_tokens(line)

        for m in URL_RE.finditer(line):
            add(ln, "URL", m.group(0), m.group(0), line, m.start())
        for m in BOOK_RE.finditer(masked):
            t = m.group(1).strip()
            add(ln, "BOOK", t, f"《{t}》", line, m.start())
        # 版本号只在「同行出现了被引文件名」时才算引用（否则「最新版本」这类普通词会误报）
        if not is_self_ver and toks:
            for m in VER_V_RE.finditer(masked):
                t = _norm_ver(m.group(1))
                add(ln, "VER", t, f"版本 v{t}", line, m.start(),
                    _label_after(masked, m.end(1)))
            for m in VER_CN_RE.finditer(masked):
                t = _norm_ver(m.group(1))
                add(ln, "VER", t, f"版本 {t}", line, m.start(),
                    _label_after(masked, m.end(1)))
            ord_spans = []
            for m in VER_ORD_RE.finditer(masked):
                t = f"第{m.group(1)}版"
                add(ln, "VER", t, t, line, m.start())
                ord_spans.append((m.start(), m.end()))
            for m in VER_NUM_RE.finditer(masked):
                # 「第 9.9 版」已由 VER_ORD 收录，避免同一处重复计
                if any(s <= m.start() < e for s, e in ord_spans):
                    continue
                t = _norm_ver(m.group(1))
                add(ln, "VER", t, f"版本 {t}", line, m.start(),
                    _label_after(masked, m.end(1)))
            for m in VER_LABEL_RE.finditer(masked):
                t = m.group(0)
                # 「v9.9 修订说明」「1.1 修订说明」里的后缀不是独立版本，避免同一处重复计
                if VER_PRE_RE.search(masked[max(0, m.start() - 10):m.start()]):
                    continue
                add(ln, "VER", t, t, line, m.start())
        if not is_self_ver:
            for m in SEC_RE.finditer(masked):
                t = m.group(1)
                node = f"§{t}"
                # 自指章节（如「来源：本报告测算（§8.4 第 3 条）」）→ 归自证类，与 dep 无关
                if any(h in line for h in SELF_SOURCE_HINTS) \
                        and dep_has_section(node, rep_sections):
                    key = (ln, node)
                    if key not in self_seen:
                        self_seen.add(key)
                        self_src.append((ln, f"自证章节 {node}"))
                    continue
                add(ln, "SEC", node, node, line, m.start())
            for m in ATTACH_RE.finditer(masked):
                t = m.group(1).replace(" ", "")
                add(ln, "SEC", f"附件{t}", f"附件 {t}", line, m.start())
            for m in CHAPTER_RE.finditer(masked):
                t = m.group(1)
                add(ln, "SEC", f"第{t}章", f"第 {t} 章", line, m.start())

        for mk in SRC_MARKS + UNVERIFIED_MARKS:
            if mk in line:
                add(ln, "MARK", mk, mk, line, line.find(mk))

        for m in SRC_RE.finditer(masked):
            tail = m.group(1).strip()
            if _is_self_source(tail):
                key = (ln, tail.split("，")[0].strip()[:16])
                if key not in self_seen:
                    self_seen.add(key)
                    self_src.append((ln, tail))
            elif not _looks_ref(tail):
                add(ln, "SRC", tail, f"来源：{tail}", line, m.start())

        for h in SELF_SOURCE_HINTS:
            if h in masked:
                key = (ln, h)
                if key not in self_seen:
                    self_seen.add(key)
                    self_src.append((ln, h))
    return cites, self_src, week_ignored


def _block_result(text, cites, self_src, week_ignored, src_lines, src_titles,
                  dep_names, dep_errors, dep_ok, listed, declared,
                  block_reason, block_items, trust, registry_path,
                  block_kind="input"):
    """状态 ③「未验证（阻断）」的统一返回形态（fail-closed：rate 记 0、block=true）

    ③ 的两种来源共用同一形态，差别只在 block_reason / block_items（缺哪一项）：
      · block_kind="input"  审计者输入无效（路径不存在／未传 dep／与声明对不上）
      · block_kind="trust"  归属或哈希这一环不成立（**即使 hard == 0 也不许判 ①**）
    """
    rows = [(PEND, ln, label, "未验证：" + block_reason)
            for ln, _k, _n, label, _l, _p, _s in cites]
    total = len(rows)
    return {
        "text": text, "rows": rows, "total": total, "resolved": 0,
        "ng": 0, "warn": 0, "pend": total, "unresolved": total, "hard": 0,
        "rate": 0.0, "self_src": self_src, "week_ignored": week_ignored,
        "src_lines": src_lines, "src_titles": src_titles, "deps": dep_names,
        "dep_errors": dep_errors, "dep_ok": dep_ok, "listed": listed,
        "verified": False, "block": True, "block_reason": block_reason,
        "block_items": list(block_items), "declared_deps": declared,
        "state": "block", "block_kind": block_kind, "trust": trust,
        "registry": registry_path, "dep_sha256": dict(trust.get("actual", {})),
    }


def dep_index(dep_paths):
    """读依赖文件 →

    (版本号集合, 章节号集合, 文件名列表, 别名单, 归一化正面全文, 读取失败列表)

    版本号与版本后缀都从「抹掉否定从句」后的文本里取：
    「本文件只有 v1.0 与 v1.1，不存在 v1.2」不得让 v1.2 变成「存在」。
    """
    vers, sections, names, aliases, chunks, errors = set(), set(), [], [], [], []
    for p in dep_paths:
        try:
            t = read_text(p)
        except OSError as e:
            errors.append((p, str(e)))
            continue
        pos = _blank_negations(t)
        base = os.path.basename(p)
        stem = os.path.splitext(base)[0]
        names.append(base)
        aliases.extend([base, stem])
        hs = headings(t)
        if hs:
            aliases.append(hs[0][1].strip())          # H1 标题也算被引名（正文常用标题而非文件名）
        vers |= versions_in(pos)
        sections |= section_index(t)
        chunks.append(pos)
    return vers, sections, names, aliases, re.sub(r"\s+", "", "".join(chunks)), errors


def scan(path, dep_paths, dep_trust=DEP_TRUST_DEFAULT,
         registry_path=DEFAULT_REGISTRY, min_rate=0.9):
    """三态判定 → 结果字典

    v4 的关键改动只在**状态 ① 的准入**：
      · hard > 0                        → ②（幻影引用，任何归属下都成立）
      · hard == 0 且 rate ≥ 门槛         → 仅当「全部 dep 声明 auditor」且
                                          「每个 dep 的 sha256 在 registry 匹配同名条目」
                                          才判 ①；否则判 ③（阻断，指明缺哪一项）
      · hard == 0 且 rate < 门槛         → 「不通过」（报告自身缺陷，与来源归属无关）
    """
    text = read_text(path)
    lines = text.splitlines()
    self_lines = self_version_lines(text)

    src_lines, src_titles = src_line_set(text)
    listed = set()
    for ln in src_lines:
        if 0 < ln <= len(lines):
            for m in BOOK_RE.finditer(lines[ln - 1]):
                listed.add(m.group(1).strip())

    rep_sections = section_index(text)
    dep_vers, dep_sections, dep_names, dep_aliases, dep_text, dep_errors = dep_index(dep_paths)
    dep_ok = bool(dep_paths) and not dep_errors
    all_sections = rep_sections | dep_sections

    # 「归属 + 哈希」这一环：只有它能决定「是否允许说已验证通过」（v4）
    trust = dep_trust_status(dep_paths, dep_trust, registry_path)

    # 抽取与 --dep 完全解耦：total 只由报告本身决定，同参数同结果
    cites, self_src, week_ignored = extract(text, self_lines, rep_sections, src_lines)
    dep_cites = [c for c in cites if c[1] in ("VER", "SEC")]
    declared = declared_dep_docs(text, cites)

    # ── 前置一致性检查（状态 ③ 的判据一：审计者输入无效）─────
    # 判据的结论依赖审计者输入时，绝不把「审计者的错误」算成「报告的红线」。
    verified, block_reason = True, ""
    if dep_errors:
        verified = False
        block_reason = ("--dep 路径不存在或读取失败（"
                        + "、".join(p for p, _ in dep_errors) + "）")
    elif not dep_paths and dep_cites:
        verified = False
        block_reason = "报告含依赖型引用（版本号/章节号）但未提供 --dep"
    elif declared and not any(_is_dep_doc(d, dep_aliases) for d in declared):
        verified = False
        block_reason = "--dep 与报告声明的被引文件对不上"

    if not verified:
        return _block_result(
            text, cites, self_src, week_ignored, src_lines, src_titles,
            dep_names, dep_errors, dep_ok, listed, declared,
            block_reason, [], trust, registry_path)

    toks_cache = {}

    rows = []
    for ln, kind, node, label, line, pos, suffix in cites:
        mark, reason = OK, ""
        toks = toks_cache.get(ln)
        if toks is None:
            toks = doc_tokens(line)
            toks_cache[ln] = toks

        if kind == "URL":
            # 来源清单条目自身已不计入分母 → 走到这里的 URL 都在正文
            if is_verifiable_url(node):
                reason = "具名可查证域名"
            else:
                mark, reason = PEND, "待核验：占位/不可查证域名，离线无法核验"

        elif kind == "BOOK":
            if is_law_book(node):
                reason = "法规/证照/标准类名称，不计入书目核验"
            elif _is_dep_doc(node, dep_aliases) or _norm_in(node, dep_text):
                reason = "被引文件（--dep）已佐证该书目"
            elif _in_listed(node, listed):
                # 自证防线：自己抄进来源清单不算数
                if _listed_entry_has_verifiable_url(node, lines, src_lines):
                    reason = "来源清单条目附具名可查证域名"
                else:
                    mark, reason = PEND, (
                        "待核验：该书目仅由报告自身来源清单自证，"
                        "未与 --dep 内容或具名可查证域名对应")
            else:
                mark, reason = NG, "来源清单未收录该书目（幻影书目）"

        elif kind == "VER":
            doc = _nearest_doc(toks, pos)
            if doc and doc[2] and _tight_before(pos, doc) and not _is_dep_doc(doc[1], dep_aliases):
                if _in_listed(doc[1], listed):
                    mark, reason = WARN, f"外部来源《{doc[1]}》的版本号，无网络可核验"
                else:
                    mark, reason = NG, f"被引文件《{doc[1]}》未见于依赖文件（幻影被引文件）"
            else:
                numeric = bool(re.fullmatch(r"\d+(?:\.\d+)*", node))
                if numeric:
                    has_ver = node in dep_vers
                    # 「方案 v1.1 修订说明」：版本号存在还不够，这个「修订说明」也得真的存在
                    has_suf = (not suffix) or (suffix in dep_text)
                    if has_ver and has_suf:
                        reason = "依赖文件已出现该版本号"
                    elif not has_ver:
                        mark, reason = NG, "依赖文件未出现该版本号"
                    else:
                        mark, reason = NG, f"依赖文件未出现该版本表述（{suffix}）"
                else:
                    core = _label_core(node)
                    if node.replace(" ", "") in dep_text or core in dep_text:
                        reason = "依赖文件已出现该版本表述"
                    else:
                        mark, reason = NG, "依赖文件未出现该版本表述"

        elif kind == "SEC":
            doc = _nearest_doc(toks, pos)
            ext = EXT_MARK_RE.search(line)
            if ext and ext.start() <= pos <= ext.end() \
                    and not _is_dep_doc(ext.group(1).strip(), dep_aliases):
                mark, reason = WARN, f"显式标注外部来源（{ext.group(1).strip()[:20]}），无网络可核验"
            elif doc and doc[2] and _tight_before(pos, doc) and _in_listed(doc[1], listed) \
                    and not _is_dep_doc(doc[1], dep_aliases):
                mark, reason = WARN, f"外部来源《{doc[1]}》的章节，无网络可核验"
            elif _ext_attr_before(line, pos):
                mark, reason = WARN, "同行引用了外部机构报告，章节无法离线核验"
            elif dep_has_section(node, all_sections):
                reason = ("本报告自证章节" if dep_has_section(node, rep_sections)
                          else "依赖文件已存在该章节")
            else:
                mark, reason = NG, "依赖文件与本报告均未出现该章节编号"

        elif kind == "SRC":
            if any(node.startswith(g) for g in GENERIC_SOURCES):
                mark, reason = WARN, "来源主体不可核验（自我指认/泛引用）"
            else:
                reason = "来源主体具名"

        elif kind == "MARK":
            if node in UNVERIFIED_MARKS:
                mark, reason = WARN, "标注为未核实（数据不得进交付稿）"
            else:
                reason = "可信度标记"

        rows.append((mark, ln, label, reason))

    total = len(rows)
    ok_n = sum(1 for x in rows if x[0] == OK)
    ng_n = sum(1 for x in rows if x[0] == NG)
    warn_n = sum(1 for x in rows if x[0] == WARN)
    pend_n = sum(1 for x in rows if x[0] == PEND)
    rate = (ok_n / total) if total else 1.0

    # ── v4：状态 ① 的准入只由「归属 + 哈希」决定 ────────────
    # 已核验出幻影引用 → ②：引用对不上就是报告的缺陷，与谁交的源无关（任何归属下都成立）。
    if ng_n > 0:
        state = "hard"
    elif rate < min_rate:
        # 可解析率不达标属报告自身缺陷，与来源归属无关 → 不通过（不打「未验证」）
        state = "low"
    elif not trust["ok"]:
        # **即使 hard == 0**：归属或哈希这一环不成立 → 必须落 ③，不许判 ①。
        return _block_result(
            text, cites, self_src, week_ignored, src_lines, src_titles,
            dep_names, dep_errors, dep_ok, listed, declared,
            "被引文件来源归属与哈希未核实——机械检查只能比对、不能建立真相，"
            "只有「审计者独立持源（--dep-trust auditor）+ registry 哈希可核」"
            "时才允许判「已验证通过」",
            trust["missing"], trust, registry_path, "trust")
    else:
        state = "pass"

    return {
        "text": text, "rows": rows, "total": total, "resolved": ok_n,
        "ng": ng_n, "warn": warn_n, "pend": pend_n,
        "unresolved": ng_n + warn_n + pend_n, "hard": ng_n,
        "rate": rate, "self_src": self_src, "week_ignored": week_ignored,
        "src_lines": src_lines, "src_titles": src_titles, "deps": dep_names,
        "dep_errors": dep_errors, "dep_ok": dep_ok, "listed": listed,
        "verified": True, "block": False, "block_reason": "",
        "block_items": [], "declared_deps": declared,
        "state": state, "trust": trust, "registry": registry_path,
        "dep_sha256": trust["actual"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--dep", action="append", default=[],
                    help="依赖文件（可多次）。被引文件的版本号/章节必须在其中真实存在")
    ap.add_argument("--dep-trust", choices=DEP_TRUST_CHOICES, default=DEP_TRUST_DEFAULT,
                    help="本次 --dep 的来源归属：auditor=审计者独立取得；"
                         "author=由被审者提供（默认，从严）。只有全部 dep 声明 auditor "
                         "且哈希经 registry 核对，才允许判「已验证通过」")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY,
                    help=f"被引文件哈希登记表（默认 {DEFAULT_REGISTRY}）")
    ap.add_argument("--min", type=float, default=0.9, help="引用覆盖率门槛（默认 0.9，下限锁 0.5）")
    ap.add_argument("--json", help="导出 json 报告")
    a = ap.parse_args()

    if a.min < MIN_FLOOR:
        print(f"（提示）--min 下限锁 {MIN_FLOOR}，已将 {a.min} 调整为 {MIN_FLOOR}")
        a.min = MIN_FLOOR
    if a.min > 1.0:
        a.min = 1.0

    r = scan(a.path, a.dep, a.dep_trust, a.registry, a.min)
    ok = False

    print(f"【引用可解析性】{os.path.basename(a.path)}")

    if r["block"]:
        # ── 状态 ③：未验证（阻断）——不是报告的红线 ──
        trust_kind = r.get("block_kind") == "trust"
        print("\n⚠️  未验证（阻断）：" + r["block_reason"])
        for it in r.get("block_items", []):
            print("   · " + it)
        if r["declared_deps"]:
            print("   报告声明的被引文件：" + "、".join(f"《{n}》" for n in r["declared_deps"]))
        if r["deps"]:
            print("   本次 --dep：" + "、".join(r["deps"]))
        elif r["dep_errors"]:
            print("   本次 --dep："
                  + "、".join(p for p, _ in r["dep_errors"]) + "（路径无效/读取失败）")
        else:
            print("   本次 --dep：（未提供）")
        print(f"   本次 --dep-trust：{a.dep_trust}"
              f"（auditor＝审计者独立持源；author＝由被审者提供）"
              f"；registry：{a.registry}")
        if trust_kind:
            print("   各 --dep 实际 sha256：")
            for b, sh in sorted(r.get("dep_sha256", {}).items()):
                print(f"     · {b}  sha256={sh[:16] + '…' if sh else '（不可读）'}")
            print("   → 这是「**验证未完成**」，不是「报告的缺陷」："
                  "机械检查只能比对、不能建立真相。")
            print("   → 未声明归属／哈希未登记／哈希不匹配时，**不允许**判「已验证通过」；"
                  "请由审计者独立取得被引文件（--dep-trust auditor）"
                  "并在 registry 里登记其 sha256 后重跑。")
            print(f"\n已抽出引用 {r['total']} 条（未验证，不参与判定）")
        else:
            print("   → 这是「**验证未完成**」，不是「报告的缺陷」：判据结论依赖审计者输入，"
                  "不能把审计者的输入错误算成报告的红线。")
            print("   → 不做任何引用核验；请补齐/更正 --dep（须与报告声明的被引文件对得上）后重跑。")
            print(f"\n已抽出引用 {r['total']} 条（未核验，不参与判定）")
        if r["self_src"]:
            print(f"D 类自证来源 {len(r['self_src'])} 处；已忽略周次引用 {r['week_ignored']} 处")
        print("\n判定：未验证（不可放行）—— 补齐被引文件后重跑")
        verdict = "未验证"
    else:
        bad = [x for x in r["rows"] if x[0] != OK]
        print(f"引用总数 {r['total']} ｜ 可解析 {r['resolved']} ｜ "
              f"不可解析 {r['unresolved']}（其中硬错误 {r['hard']}、待核验 {r['pend']}）\n")

        print("── 不可解析清单 ──")
        if not bad:
            print("  （无）")
        for mark, ln, label, reason in bad:
            print(f"  [{mark:<4}] L{ln} {label} → {reason}")

        print("\n── 覆盖三要素检查 ──")
        src_titles = r["src_titles"]
        print(f"  [{'OK' if src_titles else 'NG':<4}] 来源清单章节：{len(src_titles)} 个"
              f"{'（' + '、'.join(src_titles[:3]) + '）' if src_titles else '（缺来源清单，B/A 两类无法判定）'}"
              f"（判据：文档后 30% ＋ 标题含 来源清单/数据来源/参考文献/参考资料）")
        print(f"  [{'OK' if r['rate'] >= a.min else 'NG':<4}] 引用可解析率："
              f"{r['rate']:.0%}（门槛 {a.min:.0%}）")
        print(f"  [{'OK' if r['hard'] == 0 else 'NG':<4}] 硬错误（引用了不存在的东西）：{r['hard']} 处")
        if r["pend"]:
            print(f"  [PEND] 待核验（来源清单自证，不计入可解析分子）：{r['pend']} 处")
        if r["deps"]:
            dep_msg = "依赖文件 " + str(len(r["deps"])) + " 个：" + "、".join(r["deps"])
        else:
            dep_msg = "未传 --dep（本报告无依赖型引用，无需核验）"
        print(f"  （{dep_msg}"
              f"；D 类自证来源 {len(r['self_src'])} 处，不参与判定"
              f"；已忽略周次引用 {r['week_ignored']} 处）")
        if r["deps"]:
            sha_txt = "、".join(f"{b}:{sh[:16]}…" if sh else f"{b}:（不可读）"
                                for b, sh in sorted(r["dep_sha256"].items()))
            print(f"  [{'OK' if r.get('state') == 'pass' else 'NG':<4}] "
                  f"被引文件来源归属/哈希（状态 ① 的准入）：--dep-trust={a.dep_trust}"
                  f"（{'审计者独立持源' if a.dep_trust == 'auditor' else '由被审者提供'}）"
                  f"；registry={a.registry}；实际 sha256：{sha_txt}")

        ok = (r["hard"] == 0) and (r["rate"] >= a.min)
        if ok:
            tail = ("引用全部可解析，无幻影引用" if r["rate"] >= 1.0
                    else f"无幻影引用，可解析率 {r['rate']:.0%} 达标"
                         f"（{r['pend']} 处待核验不计入分子）")
            print(f"\n判定：通过（{tail}）")
        else:
            why = []
            if r["hard"]:
                why.append(f"{r['hard']} 处硬错误（幻影引用）")
            if r["rate"] < a.min:
                why.append(f"可解析率 {r['rate']:.0%} < 门槛 {a.min:.0%}")
            print("\n判定：不通过——" + "，".join(why) + "，禁止定稿")
        verdict = "通过" if ok else "不通过"

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({
                "file": a.path, "total": r["total"], "resolved": r["resolved"],
                "unresolved": r["unresolved"], "hard": r["hard"], "ng": r["ng"],
                "warn": r["warn"], "pend": r["pend"], "rate": round(r["rate"], 4),
                "min": a.min, "verdict": verdict, "deps": r["deps"],
                "verified": r["verified"], "block": r["block"],
                "block_reason": r["block_reason"], "declared_deps": r["declared_deps"],
                "dep_errors": [{"path": p, "error": e} for p, e in r["dep_errors"]],
                "src_sections": r["src_titles"],
                "self_sources": len(r["self_src"]), "week_ignored": r["week_ignored"],
                # v4：状态 + 归属/哈希（① 的准入证据）
                "state": r.get("state", ""), "block_kind": r.get("block_kind", ""),
                "dep_trust": a.dep_trust, "registry": a.registry,
                "dep_sha256": r.get("dep_sha256", {}),
                "trust_missing": r.get("block_items", []),
                "items": [{"line": ln, "mark": m, "ref": lb, "reason": rs}
                          for m, ln, lb, rs in r["rows"]],
            }, f, ensure_ascii=False, indent=2)
        print(f"\n报告已导出：{a.json}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
