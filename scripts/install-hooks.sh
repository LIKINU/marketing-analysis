#!/usr/bin/env bash
# ==========================================================================
# install-hooks.sh —— 把 scripts/hooks/ 下的钩子装进 .git/hooks/
#
# 为什么需要它：`.git/` 不进版本控制，clone 到新机器后钩子就没了。
#   本脚本让「装钩子」成为一条可复现的命令，而不是靠人记。
#
# 装什么：
#   pre-push → `git push` 前自动把本 skill 同步到 Obsidian 离线存档
#              （实际同步由 scripts/sync-to-obsidian.sh 完成；失败不阻塞 push）
#
# 用法：bash scripts/install-hooks.sh
# ==========================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/scripts/hooks"
DST="$REPO/.git/hooks"

if [ ! -d "$DST" ]; then
    echo "❌ 找不到 $DST —— 这里不是 git 仓库？" >&2
    exit 1
fi
if [ ! -d "$SRC" ]; then
    echo "❌ 找不到 $SRC" >&2
    exit 1
fi

n=0
for f in "$SRC"/*; do
    [ -f "$f" ] || continue
    name="$(basename "$f")"
    cp "$f" "$DST/$name"
    chmod +x "$DST/$name"
    echo "  ✅ 已安装钩子：$name"
    n=$((n + 1))
done
echo
echo "共安装 $n 个钩子 → 之后每次 git push 会自动同步到 Obsidian 离线存档。"
echo "卸载：rm $DST/pre-push"
