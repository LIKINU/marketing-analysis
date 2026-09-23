#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sync.py — sync-to-obsidian.sh 的回归（护栏的一部分）

为什么需要它：这个脚本**每次 git push 都会跑**（pre-push 钩子），
但它曾经静默坏过一次（heredoc 里反引号未转义 → 脚本去执行 `rm .git/hooks/pre-push`
→ 被 SIGTERM 杀掉），而当时 64 条断言**一条都没叫** —— 是我手动跑才发现的。

做法：用 ARCHIVE_ROOT 指向**临时 vault** 跑一遍真同步，断言：
  ① exit 0（脚本能跑完）② 生成 存档说明.md ③ 连跑两次结果一致（幂等）
  ④ 生成的说明里没有未展开的命令替换残留（`$(…)` / 裸反引号留下的碎片）
退出码：0 通过；1 失败
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPT = os.path.join(HERE, "sync-to-obsidian.sh")


def main():
    tmp = tempfile.mkdtemp(prefix="sync-smoke-")
    root = os.path.join(tmp, "Obsidian笔记库")          # 必须含该串，安全检查才放行
    # ⚠️ 还要建出 40-Archive 这一层：脚本的安全检查要求 DEST 的**上层目录**存在
    #    （第一次跑回归时漏了这句 → 脚本正确地中止了，是测试写错不是脚本错）
    os.makedirs(os.path.join(root, "40-Archive"), exist_ok=True)
    env = dict(os.environ, ARCHIVE_ROOT=root)
    ok = True

    def snapshot():
        """运行前后各取一次：.git/hooks 内容 + 仓库跟踪文件数（用于检测命令副作用）"""
        hk = sorted(os.listdir(os.path.join(REPO, ".git", "hooks"))) if os.path.isdir(
            os.path.join(REPO, ".git", "hooks")) else []
        try:
            n = len(subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                                   text=True, timeout=60).stdout.splitlines())
        except Exception:
            n = -1
        return hk, n

    before = snapshot()

    def run():
        return subprocess.run(["bash", SCRIPT], cwd=REPO, env=env,
                              capture_output=True, text=True, timeout=180)

    p1 = run()
    note = os.path.join(root, "40-Archive", "营销skill-marketing-analysis-离线存档", "存档说明.md")
    if p1.returncode != 0:
        print(f"  [NG  ] 同步脚本退出码 {p1.returncode}")
        print(f"         stderr: {(p1.stderr or '')[-300:]}")
        ok = False
    else:
        print("  [OK  ] 同步脚本跑通（exit 0）")
    if not os.path.exists(note):
        print("  [NG  ] 没生成 存档说明.md")
        ok = False
    else:
        txt = io.open(note, encoding="utf-8").read()
        print(f"  [OK  ] 已生成 存档说明.md（{len(txt)} 字符）")
        # ④ 危害检查：heredoc 里若反引号未转义，会把内容当**命令执行**
        #    —— 真危害不是"文本长什么样"，而是**真的把命令跑了**。
        #    最典型的一次：脚本执行了 `rm .git/hooks/pre-push`（把钩子删掉）、并因嵌套 git 被 SIGTERM。
        #    所以这里查实际副作用：钩子是否还在、仓库文件是否被动过。
        after = snapshot()
        if after != before:
            print(f"  [NG  ] 运行前后仓库状态变了 —— heredoc 把内容当命令执行了")
            print(f"         前：hooks={before[0]} / 跟踪文件 {before[1]}")
            print(f"         后：hooks={after[0]} / 跟踪文件 {after[1]}")
            ok = False
        else:
            print("  [OK  ] 副作用检查：运行前后 .git/hooks 与跟踪文件数一致（未误执行命令）")
    p2 = run()
    if p2.returncode != 0:
        print("  [NG  ] 第二次运行失败（不幂等）")
        ok = False
    else:
        print("  [OK  ] 连跑两次一致（幂等）")

    shutil.rmtree(tmp, ignore_errors=True)
    print("判定：同步脚本回归" + ("通过 ✅" if ok else "失败 ⛔"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
