#!/usr/bin/env bash
# 以 `aws login` 的登入 session 作為憑證，執行一個指令。
#
# 用法：
#   with-aws-login.sh --check             驗證登入身分與憑證到期時間
#   with-aws-login.sh <指令> [參數...]     在已匯入憑證、且 PATH 前端為 AWS CLI v2 的環境執行指令
#
# 為什麼需要它：
#   - 本機 PATH 上的 aws 常是舊的 v1：沒有 `aws login`，也不支援 publish-release.sh 用到的
#     --checksum-algorithm／--checksum-mode，所以要把 v2 擺到 PATH 最前面。
#   - Claude 的每次 Bash 工具呼叫都是全新的 shell，export 的憑證不會留到下一次呼叫，
#     「匯出憑證＋執行指令」必須在同一個指令內完成。
#   - 憑證只存在這個行程的環境變數，不寫檔；結束後隨行程消失。
#   - 登入 session 過期時要由使用者在瀏覽器重新登入，Claude 無法代勞，腳本會印出該下的指令。
#
# 可用環境變數：
#   AWS_CLI_V2   指定 AWS CLI v2 的完整路徑（未指定時依序找 Homebrew、使用者目錄、官方 pkg 的位置）
#
# 結束代碼：被執行指令的結束代碼；找不到 v2、取不到憑證、用法錯誤一律回 2。
# 相容 macOS 內建的 bash 3.2：不用關聯陣列、mapfile、${var,,} 這類新語法。
set -euo pipefail

usage() {
  echo "用法：$0 --check | <指令> [參數...]" >&2
}

# 依序找出第一個版本 >= 2.32 的 AWS CLI（`aws login` 從 2.32.0 才有）。
find_aws_v2() {
  local candidate output version major minor
  for candidate in "${AWS_CLI_V2:-}" /opt/homebrew/bin/aws "${HOME}/.local/share/aws-cli/aws" /usr/local/aws-cli/aws; do
    [[ -n "${candidate}" && -x "${candidate}" ]] || continue
    output=$("${candidate}" --version 2>&1) || continue
    version=${output#aws-cli/}
    version=${version%% *}
    major=${version%%.*}
    minor=${version#*.}
    minor=${minor%%.*}
    [[ "${major}" =~ ^[0-9]+$ && "${minor}" =~ ^[0-9]+$ ]] || continue
    if (( major > 2 || (major == 2 && minor >= 32) )); then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

if [[ $# -eq 0 ]]; then
  usage
  exit 2
fi

if ! AWS_BIN=$(find_aws_v2); then
  echo "✗ 找不到 AWS CLI v2（需 2.32.0 以上）。請安裝後重試，或用 AWS_CLI_V2 指定完整路徑。" >&2
  exit 2
fi

# 只放一個名為 aws 的捷徑到 PATH 最前面：後面的指令（例如 publish-release.sh）呼叫 aws 時
# 一定是 v2，又不會因為整個目錄前置而蓋掉其他工具。
SHIM_DIR=$(mktemp -d)
trap 'rm -rf "${SHIM_DIR}"' EXIT
ln -s "${AWS_BIN}" "${SHIM_DIR}/aws"
export PATH="${SHIM_DIR}:${PATH}"

# 殘留的環境變數會蓋過登入 session，先清掉。
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_CREDENTIAL_EXPIRATION AWS_PROFILE AWS_DEFAULT_PROFILE

if ! CREDS=$("${AWS_BIN}" configure export-credentials --format env); then
  echo "✗ 取不到登入憑證，session 可能已過期。請使用者在 Claude Code 輸入下列指令重新登入" >&2
  echo "  （需要瀏覽器；開不了瀏覽器就在最後加 --remote）：" >&2
  echo "    ! ${AWS_BIN} login" >&2
  exit 2
fi

# eval 之前先確認輸出只有 export AWS_* 這類行，避免執行到非預期內容；空輸出也一併拒絕。
if printf '%s\n' "${CREDS}" | grep -qvE '^export AWS_[A-Z_]+='; then
  echo "✗ export-credentials 的輸出格式不符預期，已拒絕載入。" >&2
  exit 2
fi
eval "${CREDS}"
unset CREDS

if [[ "$1" == "--check" ]]; then
  "${AWS_BIN}" --version
  CALLER=$(aws sts get-caller-identity --query Arn --output text)
  echo "身分：${CALLER}"
  echo "憑證到期：${AWS_CREDENTIAL_EXPIRATION:-（未提供）}"
  exit 0
fi

"$@"
