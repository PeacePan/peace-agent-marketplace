#!/usr/bin/env bash
# 建立（或更新）用來 patch staging 的隔離 worktree。
#
# 為什麼用 worktree：不去切換使用者主 checkout 的分支（他們常在同一個目錄跑自己的 dev）；
# 而且本機的 staging/norwegianforest 常落後遠端數十個 commit，一律以遠端最新為準。
# bin/table.sh 只允許在 staging/* 分支 patch staging，所以 worktree 必須停在 staging/norwegianforest。
#
# 用法：prepare-worktree.sh --user <JavaCat 員編> --email <email>
# 環境變數：
#   NF_WORKTREE     worktree 路徑（預設 <主 repo>/.claude/worktrees/nf-staging-patch）
#   NF_PATCH_STATE  狀態與 log 目錄（預設 ${CLAUDE_JOB_DIR:-/tmp}/nf-staging-patch）
# 冪等：重跑只會 fast-forward 並補齊缺少的項目。需在 petpetgo repo 內（主 checkout 或任一 worktree）執行，僅支援 macOS。
set -euo pipefail

USER_ID=""
EMAIL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_ID=$2; shift 2 ;;
    --email) EMAIL=$2; shift 2 ;;
    *) echo "未知參數：$1" >&2; exit 1 ;;
  esac
done
if [ -z "$USER_ID" ] || [ -z "$EMAIL" ]; then
  echo "用法：prepare-worktree.sh --user <JavaCat 員編> --email <email>" >&2
  exit 1
fi

MAIN=$(git worktree list --porcelain | awk '/^worktree /{print $2; exit}')
WT=${NF_WORKTREE:-$MAIN/.claude/worktrees/nf-staging-patch}
BRANCH=staging/norwegianforest
STATE=${NF_PATCH_STATE:-${CLAUDE_JOB_DIR:-/tmp}/nf-staging-patch}
mkdir -p "$STATE"

echo "== 1. fetch 遠端 $BRANCH =="
git -C "$MAIN" fetch origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"

echo "== 2. worktree =="
if [ -d "$WT" ]; then
  [ "$(git -C "$WT" rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || { echo "既有 worktree 不在 ${BRANCH}：${WT}" >&2; exit 1; }
  [ -z "$(git -C "$WT" status --porcelain)" ] || { echo "既有 worktree 有未提交的變更，請先處理：$WT" >&2; exit 1; }
elif git -C "$MAIN" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git -C "$MAIN" worktree add "$WT" "$BRANCH"
else
  git -C "$MAIN" worktree add -b "$BRANCH" "$WT" "origin/$BRANCH"
fi
git -C "$WT" merge --ff-only "origin/$BRANCH"

echo "== 3. 安裝依賴（已有 node_modules 就略過）=="
for d in NorwegianForest JavaCat; do
  [ -d "$WT/$d/node_modules" ] || (cd "$WT/$d" && npm ci --no-audit --no-fund --loglevel=error)
done

echo "== 4. build（patch:staging 自己也會 build；這裡先建好，讓 plan-patch.mjs 的 print 可用）=="
(cd "$WT/NorwegianForest" && npm run build > "$STATE/build.log" 2>&1) || { tail -20 "$STATE/build.log"; exit 1; }
tail -1 "$STATE/build.log"

echo "== 5. patch 設定檔（只放員編與 email，不放 token）=="
ENVF=$WT/NorwegianForest/tables/.table.patch.env
[ -f "$ENVF" ] || printf '{"userId":"%s","email":"%s","auth":{},"lastPatchedAt":{}}' "$USER_ID" "$EMAIL" > "$ENVF"
git -C "$WT" check-ignore -q NorwegianForest/tables/.table.patch.env || echo "警告：.table.patch.env 沒被 .gitignore 排除，不要 commit 它" >&2

echo "== 完成 =="
echo "分支：$(git -C "$WT" rev-parse --abbrev-ref HEAD) @ $(git -C "$WT" rev-parse --short HEAD)"
echo "NF_WORKTREE=$WT"
