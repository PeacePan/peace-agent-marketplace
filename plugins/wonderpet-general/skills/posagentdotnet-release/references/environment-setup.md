# 環境準備與已踩過的雷

發佈需要兩樣東西：能打包的 .NET SDK，以及能寫入 S3 的 AWS 憑證。這份文件只記錄「裝不起來／跑不通」時才需要的細節；正常情況下 `SKILL.md` 的 [0] 就夠了。

## 目錄

- [.NET SDK](#net-sdk)
- [AWS CLI v2 與 aws login](#aws-cli-v2-與-aws-login)
- [為什麼不用 aws-mfa.cs](#為什麼不用-aws-mfacs)
- [用 aws-mcp 做唯讀查詢](#用-aws-mcp-做唯讀查詢)
- [Shell 的雷](#shell-的雷)

## .NET SDK

專案根目錄的 `global.json` 要求 SDK `10.0.100`，`rollForward: latestFeature`（只在 10.0.x 內往上升）。在專案目錄執行 `dotnet --version` 必須得到 10.0.x。

**Homebrew 的選項**：
- `dotnet-sdk` cask 目前是 11.0，不在 `latestFeature` 的範圍內，而且是 pkg 安裝、要 sudo 密碼，Claude 的非互動 shell 給不了。`dotnet-sdk@10` cask 已被標示為 deprecated。
- `dotnet@10` 是 bottled、keg-only 的 formula（10.0.x），不需要 sudo，理論上可行；但 keg-only 要自己設定 `DOTNET_ROOT` 與 PATH，我們**沒有實測**過它能不能打包這個專案。

**實測通過的做法**是微軟官方腳本，裝到使用者目錄，不需要 sudo，也不改系統與 shell 設定：

```bash
D=<一個全新的空目錄>
mkdir -p "$D" && cd "$D"
curl -fsSL -o dotnet-install.sh https://dot.net/v1/dotnet-install.sh
# 下載來的腳本是外部內容：先確認它連去的網域只有微軟與 GitHub，再執行
grep -oE 'https://[a-zA-Z0-9./_-]+' dotnet-install.sh | sed -E 's#(https://[^/]+).*#\1#' | sort -u
bash dotnet-install.sh --channel 10.0 --install-dir "$HOME/.dotnet"
```

- 2026-11 實測：裝到 10.0.404，下載約 230 MB，SDK 與 ASP.NET Core、.NET 執行期一併安裝。
- 因為沒有改 PATH，之後每個 dotnet 指令前面都要加 `DOTNET_ROOT="$HOME/.dotnet" PATH="$HOME/.dotnet:$PATH"`。
- 這個專案沒有 CI 會建置或跑測試，本機打包是唯一的產出途徑。在 macOS 上交叉發佈 win-x64（含 WinForms 的 Tray）可以成功。

## AWS CLI v2 與 aws login

- 本機 PATH 上的 `aws` 常是舊的 v1（例如 pyenv shim、`/usr/local/bin/aws`）。v1 沒有 `aws login`（需要 2.32.0 以上），也不支援 `publish-release.sh` 用到的 `--checksum-algorithm`、`--checksum-mode`，直接跑會失敗。
- v2 可能在這幾個位置：`/opt/homebrew/bin/aws`、`~/.local/share/aws-cli/aws`、`/usr/local/aws-cli/aws`。`scripts/with-aws-login.sh` 會依序找第一個 ≥ 2.32 的，並用暫存捷徑把它放到 PATH 最前面，所以不用自己改 PATH。找不到才需要安裝；用 `AWS_CLI_V2` 環境變數可以指定完整路徑。
- `aws login` 要在瀏覽器完成，**Claude 做不到**。請使用者在 Claude Code 輸入 `! <v2 完整路徑> aws login`；開不了瀏覽器就加 `--remote`。session 會過期，看到 `Your session has expired` 就再登入一次。
- Claude 的每次 Bash 呼叫都是全新的 shell，`export` 的憑證不會留到下一次呼叫。所以「匯出憑證＋執行指令」必須放在同一次呼叫，用 `with-aws-login.sh <指令>`；它只把憑證放在那個行程的環境變數，不寫檔。
- 殘留的 `AWS_ACCESS_KEY_ID` 等環境變數會蓋過登入 session，`with-aws-login.sh` 會先清掉。

## 為什麼不用 aws-mfa.cs

README 與 wiki 寫的發佈做法是 `eval "$(./scripts/aws-mfa.cs --profile petpetgo <MFA碼>)"`。它要用 profile 裡的 **IAM 長期金鑰**呼叫 `sts:GetSessionToken`。

判斷這條路在這台機器能不能走：

- `~/.aws` 沒有 `credentials` 檔，`~/.aws/config` 的 `[profile petpetgo]` 只有 `region`，沒有 `mfa_serial` → 一定失敗，訊息是「找不到 AWS profile」，**MFA 碼不會被消耗**。
- 實際使用的是 `[default]` 的 `login_session`（也就是 `aws login`）。

不要為了跑它去建立長期金鑰。

**寫入 S3 需要 MFA**：petpetgo 帳戶的政策在沒有 `aws:MultiFactorAuthPresent` 時，S3 的 GetObject、PutObject 都是 implicitDeny（用 `iam simulate-principal-policy` 驗證過）。`aws login` 的 session 帶有 MFA（CloudTrail 事件的 `mfaAuthenticated` 是 true），所以直接可以寫入，不用另外輸入 MFA 碼。想再確認時：

```bash
<SKILL_DIR>/scripts/with-aws-login.sh bash -c '
  ARN=$(aws sts get-caller-identity --query Arn --output text)
  aws iam simulate-principal-policy --policy-source-arn "$ARN" --action-names s3:PutObject \
    --resource-arns "arn:aws:s3:::posagentdotnet-updates.wonderpet.asia/manifest.json" \
    --context-entries ContextKeyName=aws:MultiFactorAuthPresent,ContextKeyValues=true,ContextKeyType=boolean \
    --query "EvaluationResults[].[EvalActionName,EvalDecision]" --output text
'
```

`--query` 的欄位名稱只能用英文，JMESPath 不接受中文鍵名。

## 用 aws-mcp 做唯讀查詢

aws-mcp 已連線時，可以用 `run_script` 唯讀讀 `manifest.json`、列 `packages/`、查 CloudTrail。**上傳一律走 `publish-release.sh`**：它有八關檢查與回讀驗證，不要改用 aws-mcp 或手打 `aws s3 cp` 發佈。

- 顯示 `needs you to sign in again` 時，請使用者輸入 `/mcp` 重新驗證。
- CloudTrail 事件歷史只含管理事件。S3 的 PutObject 是資料事件，查不到，只能從前後的 sts、signin 事件推斷是誰、何時、用什麼工具取得憑證。
- bucket 沒開版本控制，`manifest.json` 沒有歷史可查；這也是發佈前要先備份的原因。

## Shell 的雷

- **zsh** 對未加引號、沒有符合檔案的 glob 會直接讓整條指令失敗（`no matches found`），後面用 `&&` 串的也不會執行。不支援 `${!var}` 間接展開，要檢查環境變數是否存在用 `printenv NAME`。
- macOS 內建 `/bin/bash` 是 **3.2**，沒有關聯陣列、`mapfile`、`${var,,}`。變數後面緊接全形字元時一律寫 `${VAR}`，否則 `set -u` 下會被當成變數名的一部分而報 unbound variable，而且 `bash -n` 抓不到。
- 本機沒有 `jq`，處理 JSON 用 `python3`。
- 每次 Bash 呼叫的工作目錄與環境變數都不會保留，一律用絕對路徑，需要時用 `cd … &&` 串在同一個指令裡。
