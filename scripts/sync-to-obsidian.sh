#!/usr/bin/env bash
# ==========================================================================
# sync-to-obsidian.sh —— 把本 skill 同步到 Obsidian 离线存档
#
# 用途：手动执行，或挂到 git pre-push 上自动执行。
# 用法：bash scripts/sync-to-obsidian.sh
#
# 设计说明：
#   - rsync **镜像同步**（--delete）：源删掉的文件，存档里也删掉
#   - 排除 .git / .DS_Store / __pycache__（存档不需要版本历史与缓存）
#   - 每次同步后**重新生成 存档说明.md**，写入同步时间与实测规模
#   - 安全检查：目标路径必须在 Obsidian 笔记库内，否则中止（防 --delete 误删）
#   - ⚠️ 用 --delete-excluded：否则 --delete 默认不删被排除的项，旧件会赖着不走
# ==========================================================================
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$HOME/Desktop/Obsidian笔记库/40-Archive/营销skill-marketing-analysis-离线存档"

# ---------- 安全检查（防 --delete 误删）----------
if [[ "$DEST" != *"Obsidian笔记库"* ]]; then
    echo "❌ 目标路径异常，中止：$DEST" >&2; exit 1
fi
if [[ ! -d "$(dirname "$DEST")" ]]; then
    echo "❌ 上层目录不存在，中止：$(dirname "$DEST")" >&2; exit 1
fi
if [[ ! -f "$SRC/SKILL.md" || ! -d "$SRC/references" || ! -d "$SRC/scripts" ]]; then
    echo "❌ 来源路径异常（找不到 SKILL.md／references／scripts），中止：$SRC" >&2; exit 1
fi

mkdir -p "$DEST"

# ---------- 同步 ----------
rsync -a --delete --delete-excluded \
    --exclude='.git/' --exclude='.DS_Store' --exclude='__pycache__/' \
    "$SRC/" "$DEST/"

# ---------- 重新生成 存档说明.md ----------
n_files=$(find "$DEST" -type f -not -name '.DS_Store' | wc -l | tr -d ' ')
size=$(du -sh "$DEST" | cut -f1)
now=$(date '+%Y-%m-%d %H:%M')
n_refs=$(ls "$DEST/references"/*.md 2>/dev/null | wc -l | tr -d ' ')
n_cases=$(ls "$DEST/references/cases" 2>/dev/null | wc -l | tr -d ' ')
n_scripts=$(ls "$DEST/scripts"/*.py 2>/dev/null | wc -l | tr -d ' ')

cat > "$DEST/存档说明.md" <<EOF
# 营销分析 Skill 离线存档说明

> ⚙️ **本存档由 \`scripts/sync-to-obsidian.sh\` 同步** —— 无需手动维护。
> **最后同步**：$now ｜ **规模**：$n_files 个文件 / $size

**本地工作区（唯一源）**：\`$SRC/\`

---

## 同步机制

- 手动：\`cd ~/Desktop/Marketing-skill/Marketing-Analysis && bash scripts/sync-to-obsidian.sh\`
- 自动（可选，未安装）：在 git 仓库的 \`.git/hooks/pre-push\` 里呼叫本脚本
- 同步方式：rsync **镜像**（源删掉的文件这里也删掉，\`--delete-excluded\`）
- 排除项：\`.git\`（版本历史）、\`.DS_Store\`、\`__pycache__\`

## 内容

| 路径 | 内容 |
|---|---|
| \`SKILL.md\` | **主入口**：定位与边界 ＋ 门禁 8 项 ＋ 七步工作流 ＋ 27 项判据 ＋ 路由表 ＋ 纪律 |
| \`AGENTS.md\` | 跨工具接入手册（各平台怎么放／怎么触发／能力降级／hook 配置模板） |
| \`AGENT-BRIEF.md\` | 给 subagent 的单文件快照（由 \`scripts/agent_brief.py\` 自动生成） |
| \`references/\` | **${n_refs} 份编号文档**（含 \`cases/\` **${n_cases} 档**行业案例、\`商业模式库/\` 7 份 28.7 万字） |
| \`scripts/\` | **${n_scripts} 支 Python 脚本**（判据层）＋ \`fixtures/\` 回归夹具 |
| \`assets/\` | \`交付模板.docx\`（Word 排版底稿）＋ \`dep-registry.json\`（被引文件哈希登记） |

## 质量门禁（本 skill 的判据）

- **27 项审计**（5 维度族 / **8 类硬错误** ＋ 阻断项）→ 不过即打回
- **全部回归断言必须全绿**（含作弊稿、幻影引用、误杀回归；项数见 AGENT-BRIEF.md）
- **引用可解析性三态**：①已验证通过 ②幻影引用＝硬错误 ③未验证＝阻断
- Word 出稿必须以 \`assets/交付模板.docx\` 为底稿（正文宋体小四／行距 1.5／首行缩进 2 字）
EOF

echo "✅ 已同步到：$DEST"
echo "   文件 ${n_files} 个｜体积 ${size}｜references ${n_refs} 份（cases ${n_cases} 档）｜脚本 ${n_scripts} 支"
