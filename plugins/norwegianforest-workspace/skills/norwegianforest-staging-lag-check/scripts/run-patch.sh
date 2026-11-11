#!/usr/bin/env bash
# 執行單一批次的 `npm run patch:staging`，並避開三個會「靜默失敗」的坑：
#   1. 程式用 readline.question 讀輸入，事先塞好多行會被丟掉（`printf y |` 會變成什麼都沒做）
#      → 用 FIFO 當 stdin，等提示出現才餵（OTP、y）。
#   2. 程式會用 pbcopy 把整包 patch 內容寫進使用者的剪貼簿
#      → PATH 最前面放一個什麼都不做的假 pbcopy。
#   3. 請求太大時伺服器回 413，但程式仍印「已成功更新表格」並以 0 結束
#      → 只認回應裡的 data.patchV2 清單，且筆數要等於表數。
# 只有版本與相依檢查都通過（log 沒有 ❌／⚠️，且出現「是否直接更新表格」提示）才會回答 y。
#
# 用法：run-patch.sh <批次標籤> <逗號分隔表名>
# 結束碼：0 寫入成功；1 寫入失敗（回應不是預期的 patchV2 清單）；2 中止（檢查未過或逾時，沒回答 y、沒寫入）。
# CHECK_ONLY=1：檢查通過時回答 n（只做版本、相依、⚠️ 檢查，不寫入），結束碼 0。
#   用在「相依群組超過請求上限、要改用 send-split.mjs 拆開送」的情況：先讓工具把整個群組檢查過一遍。
# 環境變數：
#   NF_WORKTREE       staging worktree 根目錄（預設 <主 repo>/.claude/worktrees/nf-staging-patch）
#   NF_PATCH_STATE    狀態與 log 目錄（預設 ${CLAUDE_JOB_DIR:-/tmp}/nf-staging-patch）
#   OTP_WAIT_SECONDS  等使用者提供 OTP 的秒數（預設 900）
# OTP 交握：staging 憑證過期時程式會自己寄 OTP。此時腳本印出 WAITING_OTP，並建立
#   $NF_PATCH_STATE/waiting-otp-<標籤>；呼叫端取得 6 位數驗證碼後寫入 $NF_PATCH_STATE/otp.txt 即可繼續。
#   憑證仍有效時完全不需要 OTP。
# 同一個 worktree 不可同時跑兩個批次（dist 與設定檔會互相覆蓋）。
set -uo pipefail

LABEL=${1:?用法：run-patch.sh <批次標籤> <逗號分隔表名>}
NAMES=${2:?用法：run-patch.sh <批次標籤> <逗號分隔表名>}
STATE=${NF_PATCH_STATE:-${CLAUDE_JOB_DIR:-/tmp}/nf-staging-patch}
if [ -z "${NF_WORKTREE:-}" ]; then
  MAIN=$(git worktree list --porcelain | awk '/^worktree /{print $2; exit}')
  NF_WORKTREE=$MAIN/.claude/worktrees/nf-staging-patch
fi

mkdir -p "$STATE/bin"
[ -x "$STATE/bin/pbcopy" ] || { printf '#!/bin/sh\ncat > /dev/null\n' > "$STATE/bin/pbcopy"; chmod +x "$STATE/bin/pbcopy"; }
LOG=$STATE/patch-$LABEL.log
FIFO=$STATE/stdin-$LABEL.fifo
rm -f "$FIFO" "$LOG" "$STATE/waiting-otp-$LABEL" "$STATE/otp.txt"
mkfifo "$FIFO"

# 持有 FIFO 的寫入端，避免程式讀到 EOF；結束時只清我自己啟動的程序
( sleep 3600 > "$FIFO" ) &
HOLD=$!
cleanup() {
  pkill -P "$HOLD" 2>/dev/null
  kill "$HOLD" 2>/dev/null
  rm -f "$FIFO" "$STATE/waiting-otp-$LABEL"
}
trap cleanup EXIT INT TERM

cd "$NF_WORKTREE/NorwegianForest" || { echo "[$LABEL] 找不到 worktree：$NF_WORKTREE" >&2; exit 2; }
PATH="$STATE/bin:$PATH" npm run patch:staging -- "$NAMES" < "$FIFO" > "$LOG" 2>&1 &
NPID=$!

# ============================================================
# Step 1: 等程式跑到提示、失敗或要 OTP（build 與初始化約 25 秒；等 OTP 的時間不計入逾時）
# ============================================================
OTP_DONE=0
TICKS=0
while true; do
  grep -q "是否直接更新表格" "$LOG" 2>/dev/null && break
  grep -q -E "❌|TypeError|JWT 取得失敗" "$LOG" 2>/dev/null && break
  kill -0 "$NPID" 2>/dev/null || break
  if [ "$OTP_DONE" = 0 ] && grep -q "正在取得一次性驗證碼" "$LOG" 2>/dev/null; then
    touch "$STATE/waiting-otp-$LABEL"
    echo "WAITING_OTP: staging 憑證需要新的 OTP（信件主旨「資料中台準備環境密碼信」）。請把 6 位數驗證碼寫入 $STATE/otp.txt"
    WAITED=0
    until [ -s "$STATE/otp.txt" ] || [ "$WAITED" -ge "${OTP_WAIT_SECONDS:-900}" ]; do
      sleep 1
      WAITED=$((WAITED + 1))
    done
    if [ ! -s "$STATE/otp.txt" ]; then
      echo "[$LABEL] ABORT：等不到 OTP，沒有寫入"
      kill "$NPID" 2>/dev/null
      exit 2
    fi
    printf '%s\n' "$(tr -d '[:space:]' < "$STATE/otp.txt")" > "$FIFO"
    rm -f "$STATE/otp.txt" "$STATE/waiting-otp-$LABEL"
    OTP_DONE=1
  fi
  sleep 1
  TICKS=$((TICKS + 1))
  if [ "$TICKS" -ge 600 ]; then
    echo "[$LABEL] ABORT：逾時，沒有寫入"
    kill "$NPID" 2>/dev/null
    exit 2
  fi
done

# ============================================================
# Step 2: 把關：提示出現且 log 沒有 ❌／⚠️ 才回答 y
#   ❌ 是版本或相依檢查失敗；⚠️ 是有人在最近一次 merge 之後更新過 staging 這張表，盲目覆蓋可能蓋掉別人的改動。
# ============================================================
ANSWER=y
[ "${CHECK_ONLY:-0}" = 1 ] && ANSWER=n
if grep -q "是否直接更新表格" "$LOG" && ! grep -q -E "❌|⚠️" "$LOG"; then
  echo "[$LABEL] 版本與相依檢查通過，回答 $ANSWER"
  printf '%s\n' "$ANSWER" > "$FIFO"
  wait "$NPID" 2>/dev/null
  if [ "$ANSWER" = n ]; then
    echo "[$LABEL] CHECK_OK：只做檢查，沒有寫入"
    exit 0
  fi
else
  echo "[$LABEL] ABORT：檢查未通過，沒有回答 y、沒有寫入。相關訊息："
  grep -E "❌|⚠️|Error" "$LOG" | head -20
  kill "$NPID" 2>/dev/null
  exit 2
fi

# ============================================================
# Step 3: 判定結果：只認 data.patchV2 清單，不信任「已成功更新表格」
# ============================================================
RESP=$(sed -n '/是否直接更新表格/,$p' "$LOG" | tr -d '\n')
EXPECT=$(printf '%s' "$NAMES" | tr ',' '\n' | grep -c .)
IDS=$(printf '%s' "$RESP" | sed -n 's/.*"patchV2":\[\([^]]*\)\].*/\1/p')
GOT=$(printf '%s' "$IDS" | tr ',' '\n' | grep -c .)
if [ -n "$IDS" ] && [ "$GOT" -eq "$EXPECT" ]; then
  echo "[$LABEL] RESULT: OK（寫入 ${GOT} 張，id：${IDS}）"
  exit 0
fi
echo "[$LABEL] RESULT: FAIL：回應不是預期的 patchV2 清單（程式印的「已成功更新表格」不可信）。回應前 300 字："
printf '%s\n' "$RESP" | cut -c1-300
exit 1
