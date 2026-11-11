#!/usr/bin/env bash
# patch 工作收尾：移除 worktree 設定檔中的 staging 登入憑證、清掉殘留的 FIFO 與 OTP 檔。
# 加 --remove-worktree 會連 staging worktree 一起移除（worktree 內沒有任何要保留的東西時才用；
# 之後若還要補 patch，重新建立並重新取得 OTP 即可）。
#
# 用法：cleanup.sh [--remove-worktree]
# 環境變數：NF_WORKTREE、NF_PATCH_STATE（同 run-patch.sh）
set -uo pipefail

MAIN=$(git worktree list --porcelain | awk '/^worktree /{print $2; exit}')
WT=${NF_WORKTREE:-$MAIN/.claude/worktrees/nf-staging-patch}
STATE=${NF_PATCH_STATE:-${CLAUDE_JOB_DIR:-/tmp}/nf-staging-patch}

rm -f "$STATE"/stdin-*.fifo "$STATE"/waiting-otp-* "$STATE/otp.txt"
echo "已清掉殘留的 FIFO 與 OTP 檔（log、lag.tsv、plan.json 保留在 ${STATE}）"

ENVF=$WT/NorwegianForest/tables/.table.patch.env
if [ -f "$ENVF" ]; then
  node -e '
    const fs = require("fs");
    const env = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
    if (env.auth) delete env.auth.staging;
    fs.writeFileSync(process.argv[1], JSON.stringify(env));
  ' "$ENVF" && echo "已移除 .table.patch.env 內的 staging 登入憑證"
fi

if [ "${1:-}" = "--remove-worktree" ]; then
  git -C "$MAIN" worktree remove "$WT" && echo "已移除 worktree：$WT" || echo "worktree 沒有被移除（可能有未追蹤檔案），請手動確認：$WT"
fi
