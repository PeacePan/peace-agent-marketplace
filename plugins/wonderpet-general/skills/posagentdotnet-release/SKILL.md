---
name: posagentdotnet-release
description: POSAgentDotNet（OldEnglish 的 .NET 門市地端代理程式，門市俗稱「小綠點」）發佈新版到 S3 的完整流程：打包（make-release.sh）、設定灰度（全部門市，或只限定某幾間門市先試裝的白名單，例如 POS0039FTEST）、用 aws login 取得 AWS 寫入憑證（不是 aws-mfa.cs）、dry-run 摘要確認、publish-release.sh 上傳、等門市機更新完成、再把線上 manifest 換回原版的暫時解法。涵蓋環境準備（.NET SDK 10、AWS CLI v2）、每個步驟的把關點與已踩過的雷。只要使用者提到發佈／上版／部署／推送 POSAgentDotNet 或小綠點的新版、Online Update、manifest、make-release／publish-release、「讓某間門市先裝這版」「只開放給 POS0039FTEST」「把 manifest 換回去」「退回 1.0.2」，或問 POSAgentDotNet 怎麼上線到門市，都應優先使用此 skill，即使沒有明說 S3。不適用於 Ragdoll、SyncAgent 等其他專案的發版，也不適用於門市第一次裝機用的 Windows 安裝包。
---

# POSAgentDotNet 發佈（Online Update 上線）

把 `OldEnglish/POSAgentDotNet` 的新版本送到門市。先建立三個觀念，後面的每一道把關都從這裡來：

- **發佈 = 把更新包 zip 與 `manifest.json` 傳到 S3**，門市機約每小時自己來拉一次 manifest，符合條件才下載，店員按「要更新」才會替換。
- **S3 上只有一份 `manifest.json`（最新版指標）**，每次發佈都會覆寫它。「只限某間門市」只是 manifest 裡的一條規則，不是另一個 bucket；覆寫後所有門市下一輪檢查都看得到它。
- **更新包 zip 一經上傳就不可變**（同版號、不同內容會被腳本擋下），所以版本號用掉就是用掉了。

文中的 `<SKILL_DIR>` 是載入本 skill 時顯示的 Base directory；`<版本>` 是三段式版號 `x.y.z`。使用者已經給的資訊（版本、門市代號、更新說明、機台已確認可安裝）直接採用，不要重複確認；只有下面兩道 GATE 不可省略。

## 先決定發佈模式

| 模式 | 什麼時候用 | manifest 的 rollout | 發佈後 |
|---|---|---|---|
| **A 限定門市試裝（白名單）** | 新版要先在特定門市驗證，例如 `POS0039FTEST` | `stores: ["POS0039FTEST"]`、`percent: 100` | 機台更新完成後，把 manifest 換回原版（暫時解法，見 [6]） |
| **B 全量** | 驗證完畢，或一般發版 | `stores: null`、`percent: 100`（`make-release.sh` 預設） | 不用換回；要強制更新才另用 `force-release.sh` |

版號：三段 `x.y.z`，來源是 `Directory.Build.props` 的 `<Version>`。必須大於線上 manifest 的版本，且不能與 S3 `packages/` 內已存在、內容不同的 zip 同號。從尚未合併的分支發佈時，這個版號就被占用了，確認沒有別的分支要用同一號。

## 流程總覽

```
[0 PRE-FLIGHT]  環境（dotnet 10、AWS CLI v2＋aws login）＋ 唯讀查線上現況
      │
[1 BUILD]       make-release.sh <版本> "<更新說明>"  → dist/release/<版本>/
      │
[2 ROLLOUT]     模式 A：set-rollout.py --stores <門市>　　模式 B：不用改
      │
[3 DRY-RUN]     publish-release.sh <版本> --dry-run（只讀、不上傳）
      │
[GATE 1]        把摘要給使用者看，等明確的「發佈」
      │
[4 PUBLISH]     publish-release.sh <版本> --yes ＋ 立刻留存「發佈前的 manifest」
      │
[5 OBSERVE]     模式 A：等機台抓到並更新，確認 currentVersion = 新版
      │
[GATE 2]        模式 A：使用者確認機台已更新完成，才可換回
      │
[6 RESTORE]     模式 A：還原 manifest 並逐位元組回讀比對
      │
[7 REPORT]      回報線上最終狀態、保留的產物、未驗證事項
```

## [0] PRE-FLIGHT

1. **環境**（細節與雷見 `references/environment-setup.md`）：
   - 在專案目錄執行 `dotnet --version` 要得到 10.0.x；沒有就照 reference 用官方腳本裝到 `~/.dotnet`（brew 的 `dotnet-sdk` cask 是 11 且要 sudo，不符合）。裝在 `~/.dotnet` 時，之後每個 dotnet 指令前面都要加 `DOTNET_ROOT="$HOME/.dotnet" PATH="$HOME/.dotnet:$PATH"`。
   - 執行 `<SKILL_DIR>/scripts/with-aws-login.sh --check`，會顯示 AWS CLI 版本、登入身分與憑證到期時間。失敗代表 `aws login` 的 session 過期，**請使用者**輸入腳本印出的 `! <v2 完整路徑> aws login`（要在瀏覽器完成，Claude 無法代勞）。
   - 不要走 README／wiki 寫的 `aws-mfa.cs`：它需要 IAM 長期金鑰，多數機器沒有，原因與驗證方式見 reference。
2. **唯讀查線上現況**：`<SKILL_DIR>/scripts/with-aws-login.sh ./scripts/show-release.sh`（或 aws-mcp 唯讀）。記下線上版本、rollout、forceAfter，這是模式 A 之後要換回的內容，也用來判斷覆寫 manifest 會影響誰。線上 manifest 的版本低於 `packages/` 內最高版本不代表異常，往往是上一次試裝後換回的結果。
3. **工作目錄**：`<repo>/OldEnglish/POSAgentDotNet`（在 worktree 就用那個 worktree）。確認 `git status` 乾淨、HEAD 是要發佈的 commit，記下 `git rev-parse --short HEAD`，最後回報時交代：打包內容就是當下的工作樹，專案沒有 CI 會建置。

## [1] BUILD

```bash
cd <repo>/OldEnglish/POSAgentDotNet
DOTNET_ROOT="$HOME/.dotnet" PATH="$HOME/.dotnet:$PATH" ./scripts/make-release.sh <版本> "<更新說明>"
```

- 更新說明會原樣顯示在門市的「有新版」對話框，要寫門市人員看得懂的一句話；換行寫 `\n`。使用者給了文字就逐字使用，不要自行潤飾或加版號。
- 預設是 framework-dependent（約 2 MB）：機台必須已裝 **ASP.NET Core Runtime 10** 與 **.NET Desktop Runtime 10**，沒裝的機台更新後服務起不來，會自動回滾，且該版本被永久列入那台的壞版本名單。測試機請使用者確認過；全量發佈前提醒一次。`--self-contained`（約 118 MB）只有使用者要求才用。
- 產出在 `dist/release/<版本>/`，已被 `.gitignore` 忽略，不會弄髒分支。**保留到這個版本全量發佈完成為止**：重新打包的 zip 內容通常不同，SHA-256 對不上腳本會拒絕，屆時只能換新版號。

## [2] ROLLOUT

模式 A：

```bash
python3 <SKILL_DIR>/scripts/set-rollout.py dist/release/<版本>/manifest.json --stores POS0039FTEST
```

- 門市代號必須等於機台 `appsettings.json` 的 `Update:StoreId`（比對不分大小寫）。`StoreId` 預設是空的，空的機台遇到有灰度規則的版本一律跳過，更新不會發生。`/update/status` 不回報 StoreId，無法遠端驗證，所以要請使用者確認；使用者已經確認過就不要再問。
- 不要設 `forceAfter`，試裝要讓店員自己按「要更新」。

模式 B：不改。使用者明確要求強制更新時，才改走 `./scripts/force-release.sh <版本> [時點]`（它會改寫 manifest 並自行轉呼叫 `publish-release.sh`）。

## [3] DRY-RUN

```bash
<SKILL_DIR>/scripts/with-aws-login.sh ./scripts/publish-release.sh <版本> --dry-run
```

做完全部檢查（更新包必要檔案與禁入檔案、manifest 欄位、SHA-256 與大小、S3 現況），印出摘要與將執行的指令，不上傳。`manifest.json` 的 notes 還是樣板、版本包已存在但內容不同、SHA-256 對不上，都會在這裡被擋下，處置見文末的表。

## GATE 1：發佈前確認

把 dry-run 摘要的這幾項逐項貼給使用者：版本變化（線上現行 → 新版）、更新說明、灰度、強制時點、SHA-256、目標 bucket。然後問「要發佈嗎？」，**等使用者明確同意發佈才進行**。先前對整個流程的同意，不等於對這份摘要的同意。

這是對全門市可見的 production 操作，覆寫 `manifest.json` 之後所有門市下一輪檢查都會看到，所以這道關不能由我自己放行。

## [4] PUBLISH

```bash
<SKILL_DIR>/scripts/with-aws-login.sh ./scripts/publish-release.sh <版本> --yes
cp dist/release/<版本>/manifest.prev.json dist/release/<版本>/manifest.before-publish.json
```

- `--yes` 只能在使用者已於對話中同意（GATE 1）之後使用。腳本的互動確認原本是給人的最後一道關，非互動環境沒有 TTY，由 GATE 1 取代它。
- **第二行要立刻執行**：`publish-release.sh` 每次執行（包含 `--dry-run`、包含發佈之後再跑）都會用「當下線上的 manifest」覆寫 `manifest.prev.json`。發佈後如果又跑一次，備份就變成新版自己，換回時會換錯。**發佈之後不要再跑 `publish-release.sh`**；還原一律用 `manifest.before-publish.json`。
- 腳本順序是先傳更新包、後覆寫 manifest，最後回讀驗證 SHA-256 與版本。任何一步失敗它會印出回退指令，先把輸出給使用者看，不要自行重試上傳。
- 成功後告訴使用者：線上現在是什麼、門市多久會看到、模式 A 換回的條件。

## [5] OBSERVE（模式 A）

- 機台約每小時（±10 分）檢查一次。可對機台打 `POST http://<機台>:9001/update/check` 立刻觸發檢查，`GET /update/status` 看 `state`、`currentVersion`、`availableVersion`，機台沒反應時先看 `lastCheckAt`、`lastError`。店員會看到 Tray 跳出「有新版」，按「要更新」才會替換。
- Claude 通常連不到門市機。請使用者查看並回報；使用者說「已安裝成功」就視為達成，回報時註明這是依使用者回報、未能親自驗證。
- 機台沒跳更新時先查：`Update:StoreId` 與白名單不符或是空的、新版不比機台現版新、該版本在機台的壞版本名單、還沒到下一輪檢查。詳見 `references/rollout-mechanics.md`。

## GATE 2：換回之前

**使用者確認機台 `currentVersion` 已是新版**（至少店員已按「要更新」進入替換），才可以換回。太早換回的後果：機台已下載好新版但還沒按更新時，下一輪檢查會因為 manifest 已是舊版而把「可更新」狀態清掉，更新入口消失，只能再發一次。機制與原始碼位置見 `references/rollout-mechanics.md`。

## [6] RESTORE（模式 A）

先確認備份是對的：

```bash
python3 -c 'import json;d=json.load(open("dist/release/<版本>/manifest.before-publish.json"));print(d["version"], d["rollout"], d["forceAfter"])'
```

版本必須等於 [0] 記下的線上版本，rollout 不能是這次的白名單。確認後還原並比對：

```bash
<SKILL_DIR>/scripts/with-aws-login.sh bash -c '
  set -euo pipefail
  REL=dist/release/<版本>
  aws --region ap-northeast-1 s3api put-object --bucket posagentdotnet-updates.wonderpet.asia --key manifest.json \
    --body "${REL}/manifest.before-publish.json" --content-type application/json \
    --cache-control no-cache --checksum-algorithm SHA256 >/dev/null
  aws --region ap-northeast-1 s3api get-object --bucket posagentdotnet-updates.wonderpet.asia --key manifest.json \
    "${REL}/manifest.verify.json" >/dev/null
  if cmp "${REL}/manifest.before-publish.json" "${REL}/manifest.verify.json"; then
    echo "✓ 線上 manifest 與發佈前逐位元組相同"
  else
    echo "✗ 線上 manifest 與備份不一致" >&2; exit 1
  fi
  rm -f "${REL}/manifest.verify.json"
'
```

- 這個動作是專案負責人說明的暫時解法：灰度發佈有一個 bug，新展店安裝較舊版本時會無法更新，所以發佈後要把 manifest 換回原版。這個說法來自專案負責人，我們沒有在原始碼驗證根因。因此白名單版掛在線上的時間越短越好。專案日後修掉這個問題，這一步就可以拿掉，到時請先向專案負責人確認。
- 換回後，試裝機已是新版，之後它檢查到「manifest 版本不比現版新」只會顯示已是最新，不會被降版。
- 更新包 zip 留在 S3 不動，日後全量發佈時重用。

## [7] REPORT

回報這些：線上 manifest 最終狀態（版本、rollout、forceAfter）、S3 上留下的更新包、本機 `dist/release/<版本>/` 位置與保留原因、發佈的 commit SHA、哪些是依使用者回報而沒有親自驗證、後續要做什麼（例如全量發佈要把 rollout 改回 `--all` 並沿用同一份 zip）。

## 常見狀況與處置

| 狀況 | 原因 | 處置 |
|---|---|---|
| dry-run 說 notes 還是樣板 | `make-release.sh` 沒帶更新說明 | 重跑 `make-release.sh` 並帶說明（會重新產生 manifest，要再設一次 rollout） |
| 說 `packages/…zip` 已存在但內容不同 | 這個版號已被用過 | 換新版號重新打包 |
| manifest 的 sha256 與 zip 不符 | zip 或 manifest 被改過 | 重跑 `make-release.sh` |
| 憑證無效／已過期 | `aws login` session 過期 | 請使用者 `! <v2 路徑> aws login` |
| `PermanentRedirect`、不認得 `--checksum-algorithm` | 用到舊的 AWS CLI v1 | 一律透過 `with-aws-login.sh` |
| 發佈後發現不該發，且尚無機台更新 | | 照 [6] 用 `manifest.before-publish.json` 還原指標 |
| 機台已更新後要退版 | manifest 版本 ≤ 機台現版就不更新 | 不能重發舊版號，也不能重發壞版本；要以更高版號打包舊程式碼，再用 `force-release.sh` |

## 參考

- `references/environment-setup.md`：.NET SDK、AWS CLI v2、`aws login` 與各種環境雷
- `references/rollout-mechanics.md`：manifest 結構、灰度判定、更新狀態機、換回時機的原始碼依據
- 設計背景：用 `petpetgo-llm-wiki` 查 `oldenglish/posagentdotnet-ops-deployment`、`posagentdotnet-online-update-design`、`posagentdotnet-update-runtime`。其中以 `aws-mfa.cs` 取得憑證的做法，在沒有長期金鑰的機器上不適用，以本 skill 為準。
