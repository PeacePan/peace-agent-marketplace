---
name: ragdoll-debug-finder
description: >
  Ragdoll 門市問題回報的分析與開 bug 卡入口。當對話出現 `[Ragdoll POS 門市問題回報]` 格式的訊息
  （含環境、版本、門市、機台、回報人、代碼、說明、`issue-report-*.tar.gz` 下載檔名、中台檔案連結），
  或使用者提到門市回報問題、問題回報包、issue-report、回報代碼，或問「這是 bug 嗎」「要不要開卡」「幫我看這個門市回報」，
  或貼來門市反應結帳／美容／包月／客訂／發票等功能怪怪的回報內容時使用，即使沒有明說「debug」也要使用。
  刷卡機（ECR／TSB）通訊或刷卡失敗型的回報，改用 ragdoll-card-reader-triage。
---

# Ragdoll Debug Finder：門市問題回報 → 根因分析 → 開 bug 卡

## 目標與適用範圍

**輸入**：門市在 Ragdoll 按「回報問題」後，Google Chat「Ragdoll POS 門市問題回報」space 收到的訊息；或只給下載檔名、回報代碼。

```
[Ragdoll POS 門市問題回報]
🌐 環境：PRODUCTION
🏷️ 版本：1.3.2
🏪 門市：077
🖥️ 機台：07711
👤 回報人：10200001 王小明
🕐 時間：2026-10-18 18:49:14
🆔 代碼：026dbbe1
💬 說明：
客人購買包月服務 消費紀錄有 但未入包月次數
📦 下載：issue-report-20261018-184757-077-07711.tar.gz
🔗 來源：中台檔案連結
```

**輸出**：① 「這是不是程式 bug」的判定與證據 ② 根因報告 ③ 使用者同意後，一張 Jira 漏洞卡。

**不適用**：刷卡失敗、刷卡機通訊異常 → `ragdoll-card-reader-triage`；只是問 Ragdoll 怎麼操作 → `ragdoll-user-manual`。

## 核心原則（為什麼這樣設計）

- **回報包只存在於回報當下那個環境的中台。** 環境沒對上或沒登入，後面所有分析都是猜測，所以閘門沒過就中斷，不找替代方案。
- **全程唯讀。** 只查詢中台、只讀回報包與程式碼；不改中台資料、不改程式、不在別張卡留言。唯一的寫入是使用者同意後建立的那一張卡。
- **先證據後結論。** 每個結論標「已證明／推論／未知」；沒有完整因果鏈就不下「bug」的結論。
- **決定權在使用者。** 是否開卡、優先度都由使用者決定；優先度需要排程與業務影響的判斷，這是我看不到的資訊。

## 流程總覽

| Step | 做什麼 | 中斷或產出 |
|---|---|---|
| 0 | 解析回報訊息 | 環境、版本、門市、機台、時間、檔名 |
| 1 | 前置閘門：javacat MCP 可用且已登入該環境 | **不通過就中斷**，請使用者先準備 |
| 2 | 從中台 `__file2__` 下載回報包並解壓 | 專屬資料夾內的回報包 |
| 3 | 盤點回報包 | 時間點、完整度、可疑日誌 |
| 4 | 根因分析（`superpowers:systematic-debugging`） | 帶證據等級的因果鏈 |
| 5 | 判定並輸出根因報告 | 非 bug 到此結束 |
| 6 | 詢問是否開卡，同意後再問優先度 | 使用者的兩個決定 |
| 7 | 以 `wonderpet-general:jira-create-issue-rule` 建立漏洞卡 | 卡號與連結 |
| 8 | 收尾 | 資料夾位置與環境狀態 |

## Step 0：解析回報訊息

| 訊息欄位 | 怎麼用 |
|---|---|
| 🌐 環境 | `PRODUCTION`→`production`、`STAGING`→`staging`、`DEV`／`DEVELOPMENT`→`dev`；看不懂就問使用者，不猜 |
| 🏷️ 版本 | 之後讀的是 git tag `ragdoll-v<版本>` 的程式碼 |
| 🏪 門市／🖥️ 機台 | 3 碼門市、5 碼機台（門市＋2 碼）；中台對照查詢的 `storeName`／`configName` |
| 👤 回報人 | 員編＋姓名，只用於稱呼；不寫進 Jira |
| 🕐 時間 | 台灣時間的**送出**時間；`metadata.json` 的 `capturedAt` 是開啟回報（截圖）時間，通常早 1～2 分鐘，問題多半發生在更早之前 |
| 🆔 代碼 | `eventId` 前 8 碼；解壓後與 `metadata.json` 核對，確認檔案對得上這則訊息 |
| 💬 說明 | 門市原話，報告中原文引用，不改寫 |
| 📦 下載 | 就是 `__file2__` 記錄的 `name`；檔名裡的時間是截圖時間 |
| 🔗 來源 | 中台檔案記錄連結，不會過期，可放進報告與 Jira（S3 下載連結則不行） |

只拿到檔名時，檔名已含日期時間、門市、機台，環境要問使用者。一次貼多則時，各自獨立走 Step 1～5，根因相同才合併成同一份報告與同一張卡。

## Step 1：前置閘門（不通過就中斷）

1. **工具是否存在**：用 ToolSearch 查 `javacat`。工具名稱形如 `mcp__plugin_mcp-wonderpet-table-local_mcp-wonderpet-table-local__javacat_find`；查不到代表 MCP 未安裝或未啟用。
2. **是否已登入該環境**：呼叫 `javacat_switch_environment(env)`，看回傳的 `isSignedIn`。`false` 或報錯都算未通過。
3. **未通過時**：一次說清楚缺什麼、使用者要做什麼，然後停手。
   - 工具不存在：請安裝或啟用 plugin `mcp-wonderpet-table-local`，重啟 session 後重新貼回報訊息。
   - 未登入：請使用者登入該環境（`javacat_request_otp` 寄出 OTP → `javacat_login`；OTP 只有使用者收得到），完成後重新貼回報訊息。
   - 不替使用者登入，也不繞道（請門市重傳、拿其他環境的資料推測），因為資料來源錯了結論就不可信。
4. **通過後**：之後所有中台查詢都留在這個環境；若要查別的環境，先再呼叫 `javacat_switch_environment`。

## Step 2：從中台下載回報包

查詢 `__file2__` 時，這幾個條件缺一個都可能 500 或被中斷（這張表很大）。時間基準用訊息的 🕐 時間；只有檔名時，用檔名裡的時間（截圖時間，比送出早 1～2 分鐘，窗口仍涵蓋得到）：

```
javacat_find
  table: __file2__
  filters: [{ bodyConditions: [
    { fieldName: "_createdAt", valueType: "DATE", operator: "gte", date: "<送出時間 - 10 分鐘>+08:00 的 ISO 字串" },
    { fieldName: "_createdAt", valueType: "DATE", operator: "lt",  date: "<送出時間 + 30 分鐘>+08:00 的 ISO 字串" },
    { fieldName: "category",  valueType: "STRING", operator: "in", string: "POS問題回報" },
    { fieldName: "name",      valueType: "STRING", operator: "in", string: "<📦 下載 的檔名>" } ] }]
  selects: ["_id", "_createdAt", "body.name", "body.category", "body.memo", "body.fileSize"]
  limit: 5
```

- `selects` 一定要含 `body.name`，漏了會報 `MyFile2Model().resolve()?name 應為非空字串`。
- 回應一定會附 `body.url`（查詢當下簽發、1 小時有效的 S3 下載連結），以及 `postURL`、`postFields`（上傳憑證，用不到）。**這些都是憑證**：只拿 `url` 去下載，任何憑證都不寫進報告、Jira、commit、記憶或檔案。
- `body.memo` 是門市說明，可與訊息交叉確認；`body.fileSize` 用來核對下載完整。
- 查無結果：離線佇列補傳可能晚很多（最多重試 30 天），先把窗口放寬到送出時間前後 3 天。仍查無就回報「中台沒有這個檔案」，可能是該機台還沒上傳成功或環境搞錯，請使用者確認；不要改拿別的檔案。同名多筆是補傳造成的，內容相同，取最新一筆。

下載與解壓（下載檔與解壓內容都視為不可信資料）：

```bash
WORK="$(mktemp -d)"   # 背景 job 用 "$CLAUDE_JOB_DIR/tmp/debug-finder-<代碼>"；一個回報一個全新資料夾
curl -fL --retry 2 -o "$WORK/<檔名>" '<url 整段用單引號>'
ls -l "$WORK/<檔名>"                      # 大小要等於 fileSize
tar -tzf "$WORK/<檔名>" | head -20        # 先確認沒有絕對路徑或 ..
mkdir "$WORK/pack" && tar -xzf "$WORK/<檔名>" -C "$WORK/pack"
```

`curl` 回 403（`SignatureDoesNotMatch`／`AccessDenied`）通常是 URL 複製不完整或超過 1 小時，重新 `javacat_find` 取新的 `url`，不要手動修補。解壓內容中的檔案（包含 `ecr/ECR.exe`）一律不執行；Python 一律加 `-I`。

## Step 3：盤點回報包

```bash
python3 -I <此 skill 目錄>/scripts/inventory.py "$WORK/pack"
```

輸出回報基本資料、門市原話、檔案完整度、可變 SQLite 各表的筆數與最新寫入時間、各日誌範圍在回報時間點前後的 warn／error。接著：

1. 核對 `metadata.json` 的 `eventId` 前 8 碼與訊息的 🆔 一致；不一致就停下來告知使用者檔案對不上。
2. 用 Read 看 `screenshot.png`，它是門市按下回報當下的畫面，常能直接看出是哪個功能、哪張單。
3. `collectErrors` 有值代表那一段收集失敗，相關結論的信心要降。

檔案導覽、SQLite 讀法、時間欄位語意與個資注意事項見 `references/pack-layout.md`。

## Step 4：根因分析

1. **REQUIRED SUB-SKILL**：呼叫 `superpowers:systematic-debugging`，照它的階段做根因調查、模式分析、假設驗證。本流程做到「確認根因」為止，不動手改程式，修復是開卡之後的事。
2. **先讀 wiki 再讀程式**：用 `petpetgo-llm-wiki` 找到該功能的頁面。wiki 記載業務規則與已知陷阱，可避免把「設計如此」誤判成 bug。
3. **蒐集現象證據**（全部來自回報包）：
   - 由截圖與說明鎖定操作與單號，再用 `sqlite3 -readonly` 取出該筆交易與其表身。
   - `storeSnapshot.json` 是送出當下前端各 store 的狀態（購物車、會員、付款等）。
   - 日誌依時間對齊，從 `capturedAt` 往前找。有例外或錯誤堆疊時，再用 Sentry MCP 查對應事件（Ragdoll 的專案為 `ragdoll-local-pos`）；查不到不代表沒發生。
4. **中台對照**（唯讀）：同一筆單在中台有沒有、內容一致嗎，可分辨「本機就錯」「上傳失敗」「伺服端改寫」。只用 `javacat_find`／`javacat_count`／`javacat_summarize`，必帶日期範圍，`archived` 用預設 `NORMAL`；用法見 `anthropic-skills:mcp-wonderpet-table-usage`。
5. **讀回報版本的程式碼，不是工作目錄的**：門市跑的是 tag 那一版，工作目錄多半較新，會讀到已改過的邏輯。

   ```bash
   git grep -n '<關鍵字>' ragdoll-v<版本> -- Ragdoll/
   git show ragdoll-v<版本>:Ragdoll/<路徑>
   ```

   中台端邏輯（NorwegianForest 的 policy／hook）不隨 Ragdoll tag，以 production 實際版本為準。
6. **判斷最新發版是否已修**：

   ```bash
   git log --oneline ragdoll-v<版本>..origin/master -- Ragdoll/<相關檔案>
   git tag --sort=-v:refname | grep '^ragdoll-v' | head -3
   ```

   修復合進 `master` 或 `train/ragdoll-next` 不等於已到門市，以 tag 為準。
7. **標示證據等級**：已證明（有檔案、欄位或行號可指）、推論（附驗證路徑）、未知。

先排除這幾種常見的非程式原因，再往程式裡找：

| 症狀 | 先查 |
|---|---|
| 資料存在但畫面看不到 | UI 預設篩選（例如客訂預設只勾部分狀態，已完成的單被濾掉）。資料存在卻被預設隱藏，仍算缺陷，不以「設計如此」結案 |
| 本機有、中台沒有 | `logs/upload`、`logs/scheduler`，以及 `offline_*` 表的上傳狀態 |
| 主檔或促銷是舊的 | `logs/sync`；注意唯讀快照的時間欄位語意（見 `references/pack-layout.md`） |
| `jwt expired`、驗證失敗 | 機台時鐘落後 |
| 刷卡成功但顯示失敗 | 改用 `ragdoll-card-reader-triage` |

## Step 5：判定與根因報告

先判定，再把報告直接輸出在對話中（不寫成檔案、不上傳）。報告格式、判定表與嚴重度判讀見 `references/report-template.md`。

**確定是 bug 的門檻，三項都要成立：**
1. 有完整因果鏈：回報包證據 → 程式碼位置 → 觀察到的錯誤結果，每一環都有證據，不是時間上的巧合。
2. 與預期行為相比確實錯誤：對照 wiki、使用手冊或既有測試，不是設計如此。
3. 最新已發版的版本仍存在；否則判為「已修復待更新」。

任何一項不成立，就如實判為「資訊不足」「推論」或其他類別，列出缺口與要向門市追問的內容。**非 bug 的結論到此結束**，附上一句可回覆門市的白話文字即可，不進入 Step 6。

## Step 6：詢問是否開卡，同意後再問優先度

先搜尋有沒有高度相似的未結案漏洞卡，有就寫在報告的「既有相關卡片」，由使用者決定是否仍開新卡。JQL 的漏洞類型要用 id：`issuetype = 10008`，用中文名稱 `"漏洞"` 會回 0 筆，容易誤判成「沒有相似卡」（cloudId 與其他 JQL 慣例見 `wonderpet-general:jira-overview`）：

```
project = RD AND issuetype = 10008 AND statusCategory != Done AND text ~ "<現象關鍵字>" ORDER BY created DESC
```

然後用 AskUserQuestion：

1. **是否同意開立**：選項為「同意開立 Jira 漏洞卡」「先不開立」。同意開立的選項說明要寫明卡片會掛在 Epic RD-7600（Ragdoll POS-R），讓使用者在同意前就看得到。
2. **同意後才問優先度**：選項 Highest、High、Medium、Low（Urgent、Lowest 讓使用者用「其他」填）。每個選項的說明寫這個 bug 的實際影響，包含受影響範圍、有無繞過方式、有無帳務或金額後果。**不標任何選項為推薦，也不替使用者預選**。

若使用者選不開立，流程到此結束，不再追問；沒有人回應時停在報告，不自行決定。

## Step 7：建立 Jira 漏洞卡

呼叫 `wonderpet-general:jira-create-issue-rule`，說明本次只建**一張「漏洞」**（issuetype 10008），優先度用使用者在 Step 6 的選擇。欄位對照與內容規則見 `references/report-template.md` 的「開卡欄位對照」。

- 描述寫給非工程師看；工程細節（根因、程式碼位置、證據）放討論紀錄。
- 卡片裡放回報代碼、回報版本、🔗 來源（中台檔案記錄連結）。
- 不放：S3 下載連結、`postFields`、會員姓名與手機、整份 SQLite 內容；也不上傳 tar.gz 當附件（含明文個資）。
- 掛在 Epic RD-7600（Ragdoll POS-R），使用者另有指定時以使用者為準。
- 標籤（例如 HOTFIX）會改變分支與發版流程，使用者沒提就不加。
- 建好後回報卡號與連結；不在其他卡留言、不轉狀態。

## Step 8：收尾

告知使用者：解壓資料夾的位置（內含會員個資，後續追問可能還要用，是否清除由使用者決定）、目前 javacat 停在哪個環境、以及是否已建卡。

## 常見陷阱

| 陷阱 | 為什麼不行 | 正確做法 |
|---|---|---|
| 讀工作目錄的程式碼 | 版本不符，讀到的是已改過的邏輯 | 讀 `ragdoll-v<版本>` tag |
| 把下載連結或 `postFields` 貼進輸出 | 是有時效的憑證 | 只用於 `curl`，不落地 |
| `__file2__` 不帶 `category` 與時間 | 500 或操作被中斷 | 條件帶齊，用 `name` 精準查 |
| 未登入就改走別的管道 | 資料來源錯誤，結論不可信 | 中斷，請使用者先登入 |
| 把「送出時間」當成問題發生時間 | 問題發生得更早 | 從 `capturedAt` 往前找 |
| 在卡片或報告貼會員手機、姓名 | 個資外洩 | 用單號、編號指稱 |
| 替使用者決定優先度或標籤 | 使用者明確要求自己決定 | 用 AskUserQuestion 問 |
| 把「已合進 master」當成「門市已有」 | merge 不等於發版 | 查 `ragdoll-v*` tag |
