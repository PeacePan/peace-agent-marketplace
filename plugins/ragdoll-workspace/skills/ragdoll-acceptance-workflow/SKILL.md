---
name: ragdoll-acceptance-workflow
description: >
  Ragdoll POS-R（Jira Epic RD-7600）實機驗收的標準作業流程。定義依賴檢查、確認
  驗收的程式碼版本與環境、業務前置狀態檢查、驗收範圍界定（父系 Epic 必須是
  RD-7600）、驗收條件擷取（customfield_10030，markdown 或 ADF）、修復內容理解
  （diff-first）、測試資料盤點與實機操作、資料缺口時的模擬資料法與論證法、三態
  判定與報告格式、使用者明確要求時的 Jira 留言與截圖流程、驗收後環境清理，以及
  「預設只回報留言草稿、不自行留言 Jira」的規則。當使用者要求對某張 POS-R
  ticket 做實機驗收時使用。
---

# Ragdoll POS-R 實機驗收 SOP

## 適用範圍

只適用於父系 Epic 是 **RD-7600（POS-R）** 的 Jira ticket。驗收的是「使用者明確指定的單一 ticket」，不是「給一個 Epic、自動列出所有子卡逐一驗收」。

## 速覽

| Step | 做什麼 |
|---|---|
| 0a | 工具依賴檢查；**無條件**確認驗收的程式碼版本（0a-2），備好 worktree 與 dev |
| 0b | 業務前置狀態（開帳／登入／環境一致性），依條件性質分類，必要時自己建立前提 |
| 1–2 | 範圍界定（父系 Epic ＝ RD-7600）、解析驗收條件 |
| 3 | diff-first：先看清修復改了什麼，並跑 PR 自己的測試 |
| 4 | 找操作方式（手冊 → wiki → 程式碼） |
| 5 | 盤點測試資料、實機操作、截圖存證 |
| 6 | 三態判定＋證據等級，回報；預設不留言 |
| 6b | 僅在使用者明確要求時：選圖、上傳、留言 |
| 7 | 使用者表示驗收完成後清理環境 |

**授權分界**：

| 可自行做（不必問） | 須使用者明確同意 | 一律不做 |
|---|---|---|
| 自建 worktree、clone `node_modules`、起 dev；登入員編；跨日未關帳時關帳 → 開帳（Step 0b）；dev 中台**唯讀**查詢；記憶體 fixture（純記憶體、驗完還原）；唯讀對話框 | Jira 留言與上傳附件（Step 6b）；commit／push／開 PR；完成結帳／付款（會建 dev 銷售單、開錢櫃、可能出紙）；寫入 dev 中台資料；停掉**非自己** worktree 的行程 | 直接改寫本機共用 DB 的資料列；production 查詢或寫入；為了收尾去點「取消銷售」「後付款」等破壞性按鈕 |

---

## Step 0a：工具依賴檢查（MUST，缺任何一項就停止）

| 檢查項 | 方法 | 缺失時的訊息 |
|---|---|---|
| `wonderpet-general:jira-overview` skill | 用 `Skill` 載入 | 「缺少 wonderpet-general plugin（找不到 jira-overview skill），請先安裝」 |
| `ragdoll-runtime-debugging-usage` skill | 用 `Skill` 載入 | 「缺少 ragdoll-runtime-debugging plugin（找不到 skill 說明），請先安裝」 |
| `ragdoll-electron` MCP | 呼叫 `get_electron_window_info` | 工具不存在 → 「缺少 ragdoll-runtime-debugging plugin，請先安裝」。工具存在但找不到 app／port＝Ragdoll 尚未啟動：**不要停下來請使用者啟動**，進 Step 0a-2 自行啟動後再檢查一次 |
| `ragdoll-sqlite-mutable`／`ragdoll-sqlite-readonly` MCP | 各呼叫一次 `list_tables` | 區分「未安裝」與「DB 檔不存在（Ragdoll 未啟動過，0a-2 啟動後再查；或 `RAGDOLL_TARGET_ENV` 指到錯的環境）」 |

**已實測——委派給 subagent 時的工具授權落差**：委派 `ragdoll-workspace:ragdoll-acceptance-qa` 時，該次實際拿到的工具只有 `Read`／`Skill`／`SubagentHandback`，不含上表任何 MCP，Step 0a 連第一項都跑不完。這不是「未安裝」，是授權範圍比 agent 定義更嚴。遇到時：不重試同一次委派、不嘗試幫 subagent 擴權，改由 **orchestrator 自己的 session 直接接手整套 SOP**（用 `ToolSearch` 確認自己有這些 MCP 工具）。

**選用依賴**：
- `ragdoll-workspace:ragdoll-user-manual`：存在，但涵蓋有限（美容模式等尚待補），見 Step 4。
- `mcp-wonderpet-table-local`（javacat）：驗收需要真實會員／月卡／優惠券等中台資料時才用。本地唯讀 DB **不含**會員資料（Ragdoll 對會員一律打遠端 GraphQL，設計上不落地）。

### Step 0a-2：確認驗收的程式碼版本，備好環境（無條件執行）

**不論 Ragdoll 是否已在跑都要做**。工具檢查全過不代表視窗跑的是有修復的程式碼——已實測：檢查時 Ragdoll 已在跑，但那是主 checkout 的 `master`，根本不含修復，是看行程 cwd 才發現。

1. **找分支與 PR**：Jira `customfield_10033`（分支名稱）常是空的 → 用 GitHub 搜 PR（`search_pull_requests`：`RD-xxxx repo:petpetgo/petpetgo`），或 `git branch -r --list '*RD-xxxx*'`。記下 PR 的 `state`／`base`／head sha／是否 draft。
2. **決定在哪驗**：
   - PR 已 merge（進 `release/ragdoll`，或已 cascade 到 `train/ragdoll-next`）→ 含該 commit 的 checkout 即可（`git merge-base --is-ancestor <PR head> <checkout HEAD>` 確認）。
   - PR 仍 open → 修復只存在 PR 分支，**MUST** 跑 PR 分支；驗 `train/ragdoll-next` 或 `master` 驗不到修復。
3. **檢查已在跑的 Ragdoll 是哪份程式碼**：
   ```bash
   lsof -nP -iTCP:3100 -sTCP:LISTEN      # 取 PID
   lsof -a -p <PID> -d cwd -Fn           # 看 cwd
   ```
   cwd 的 HEAD 不含修復 → 這個視窗不能當證據。**不要強殺**（可能是使用者自己的視窗）；3100／9222 被占用時，請使用者關閉，或確認是殘留後再處理。
4. **建 worktree**：預設用 `--detach`——開發 session 通常已佔用同一分支，直接 `git worktree add <路徑> <分支>` 會失敗；detach 也不會產生本機分支：
   ```bash
   git fetch origin <分支>
   git worktree add --detach .claude/worktrees/RD-xxxx-accept origin/<分支>
   ```
   再用 `EnterWorktree({path: "<絕對路徑>"})` 切進去隔離。**MUST NOT** 用 `EnterWorktree({name})`——它只會從 HEAD 新建分支，無法 checkout 既有遠端分支。
5. **`node_modules`**（Turbopack 拒絕 symlink，必須是真實目錄）：
   - 優先從別的驗收 worktree 做 APFS clone：`cp -cR <來源>/Ragdoll/node_modules <新>/Ragdoll/node_modules`（約 17 秒）。**前提**：`git diff <來源 HEAD> <目標 HEAD> -- Ragdoll/package.json Ragdoll/package-lock.json` 只差 app 自己的 `version`。
   - 否則 `npm ci`，用 `run_in_background` 並輪詢 log，不要用 `sleep` 卡住 turn。
6. **起 dev**：對 `npm run dev` **本身**設 `run_in_background`（輸出導到檔案）；**不要**自己在指令裡再包 `&`——外層會立刻結束、通知誤導，`TaskStop` 也停不掉真正的行程。起手前先 `pwd`（cwd 已在 `Ragdoll/` 時再 `cd Ragdoll` 會失敗）。`dev.sh` 會先跑 lint，有 lint 錯就不啟動。
   已知風險（RD-8275 驗收記錄）：`dev.sh` 對**共用**本機 DB 做 schema push，分支 schema 與上次執行的不同時，可能刪掉別分支的欄位。
7. **就緒判定與留證**：3100、9222 皆 LISTEN，且 Next 與 Electron 行程的 cwd 都是這個 worktree（`lsof` 兩行輸出留進報告）。

回頭重跑 Step 0a 的 electron／sqlite 檢查，全部通過才進 Step 0b。

---

## Step 0b：業務前置狀態確認（用來正確分類結果，不是無條件擋在 Step 4 之前）

`/checkout` 對「未開帳」「未登入銷售員」有全面攔截（`next/app/checkout/page.tsx` 的 `isCheckoutDisabled`／`guardCheckout`）。**但 MUST NOT 把它們當無條件前置門檻**：不少驗收條件本身就在描述這些邊界狀態下的行為（例如 RD-8153「尚未開帳時點擊『銷售查詢(退換貨)』→ 按鈕可點擊並顯示提示」）。

進 Step 4 前，逐條先讀懂每條條件描述的情境：

1. **條件本身在測「未開帳／未登入／跨日未關帳」** → 不要先開帳或登入，直接在邊界狀態下操作並判定 ✅／❌。**不得**以環境未就緒為由改標「無法驗證」。
2. **條件是正常流程的一部分** → 需要環境就緒，前提由**自己建立**（見下）。只有「自己也建不起來」才標 ⚠️ 無法驗證（寫明卡在哪一步），不要標 ❌。
3. **環境一致性**（每條都要確認一次）：`ragdoll-sqlite-*` 查到的是否為預期環境（`RAGDOLL_TARGET_ENV`，預設 `development`，須在啟動 Claude Code **之前**設定，事後改無效）。對不上就停止並回報，請使用者確認。

### 自己建立前提：登入與「關帳 → 開帳」

在**自建的隔離 dev 環境**（`RAGDOLL_TARGET_ENV=development`、測試門市）裡，登入員編與開帳可自行做、不必問。但要清楚真實副作用：

- 本機 DB 是**整台機器共用**（`~/Library/Application Support/Electron/data/<env>/`），不依 worktree 隔離，常有前幾天殘留的未關帳日結。
- 「關帳」「開帳」會**寫共用 DB 並上傳 dev 中台日結**；被關掉的常是使用者本人前一天的日結，無法復原（只能再開新帳）。

偵測跨日未關帳：

```sql
SELECT name, accounting_date, squared_at, upload_status FROM offline_pos_report ORDER BY rowid DESC LIMIT 3
```

`squared_at IS NULL` 且 `accounting_date`（epoch ms）早於今天＝**跨日未關帳**。畫面徵兆：掃商品 toast「已超過營業時間，請先至功能選單重新開帳」，功能選單「開帳」灰、「關帳」可點。

規則：
- **今天已開帳** → 直接用，不要關帳重開。
- **跨日未關帳** → 功能選單「關帳」→「確認關帳」→「立即開帳」→「確認開帳」（預設 12300／0）。若跳「中台仍有未關閉日結單」二次確認，用 `[role="alertdialog"] button:last-of-type` 按確認，別用 `click_by_text('確認')`（會與「確認開帳」搶）。
- **報告 MUST 揭露**：關掉哪一筆（單號、筆數、金額）、新開哪一筆（單號），列入「環境副作用」。
- **收尾不關今日的帳**（開帳中是機台上班日的正常狀態，見 Step 7）。
- **員編由使用者提供**，不要猜、不要改本地 `user` 表。輸入是數字鍵盤，做法見 `references/electron-tool-pitfalls.md`。
- **禁止**為了製造情境直接改寫共用 DB 的資料列（改別人的銷售單、改 `user` 表的 disabled…），會影響同機的其他 session。需要邊界資料走 Step 6 的模擬資料法或論證法。

---

## Step 1：驗收範圍界定（POS-R = RD-7600 校驗，含邊界情況）

1. 使用者給卡號（例 `RD-8153`）。若就是 `RD-7600` → 停止並回報「RD-7600（POS-R）本身是 Epic，請指定其底下的具體 ticket」。
2. 用 Atlassian MCP 的 `getJiraIssue`（依環境是 `mcp__plugin_atlassian_atlassian__getJiraIssue` 或 `mcp__claude_ai_Atlassian__getJiraIssue`，擇一）**一次抓齊**，cloudId `f338306a-4b54-421e-9209-2e9f451c67f7`：
   `fields: ["summary","issuetype","parent","status","labels","description","customfield_10030","customfield_10033","customfield_10057","customfield_10059","customfield_10060","customfield_10061"]`
   （依序是：驗收條件、分支名稱、規格〔任務〕、正確行為〔漏洞〕、使用者故事、規格〔故事〕）。呼叫失敗 → 停止並回報「查無 `<卡號>` 或沒有讀取權限」。
3. **沒有 `parent`** → 停止並回報「⚠️ 無法確認範圍：此卡沒有父系 Epic」。這與「明確不屬於」不同，不可當拒絕（避免對資料缺失的卡片產生使用者無法覆寫的假陰性）。
4. `parent.key === "RD-7600"` → 繼續。
5. 否則看 `parent.fields.issuetype.name`：
   - 不是「大型工作」（代表這是 Subtask，`parent` 是它的父 Task）→ 對 `parent.key` 再查一次，只遞迴這一次（最多往上兩層），重複步驟 3–5。
   - 是「大型工作」但 key 不是 `RD-7600` → **明確拒絕**：「此卡的父系 Epic 是 `<key>`（`<summary>`），不是 POS-R（RD-7600），本 skill 無法驗收」。

---

## Step 2：解析驗收條件（`customfield_10030`）

先判斷格式再抽取。

### 格式 A：markdown 字串（Atlassian plugin 的常見回傳）

```markdown
### 正常情境
- [ ] 清單新增「購買包月門市」欄，…
### 邊界條件
- [ ] …
```

- 每個 `- `／`* `／`1. `（含 `- [ ]`、`- [x]`）清單項目是一條獨立條件；**忽略勾選狀態**（只代表 Jira 上被手動勾過）。
- `#` 開頭的行是**分組標題**，不是條件，可當報告分組名；條件編號依出現順序連續編號。
- 縮排的延續行屬同一條；沒有清單、只有段落時，每個空行分隔的段落是一條。
- 一條條件內用「；」串了多項檢查，仍算一條，但逐項判定、逐項寫依據，有一項不符整條 ❌。
- 結尾常夾零寬字元（如 U+200C）等雜訊，去除前後空白。

### 格式 B：ADF（備用）

`content` 可能是以下任一種，**三種都要能解析**：

1. `taskList`：每個 `taskItem` 是一條，忽略 `attrs.state`。
2. `bulletList`／`orderedList`：每個 `listItem` 是一條（`listItem.content` 通常是 `paragraph`，`text` 在 `paragraph.content`，比 `taskList` 多一層）。
3. 頂層 `paragraph`：每個是一條。

一律適用：在邊界內遞迴收集 `text` 串成該條文字；**`hardBreak` 也是條件邊界**（作者常用 Shift+Enter 在同一個段落塞多條）；去除前後空白。

### 通用規則

- **解析出 0 條** → **MUST 停止並回報**「無法從 `customfield_10030` 解析出任何驗收條件，請確認該卡是否已填寫驗收條件」。**MUST NOT** 從規格、正確行為、使用者故事等欄位發明新的獨立驗收條件編號，那些不是判定 ✅／❌ 的正式依據。
- **但 MUST 完整讀其他欄位**，依卡片類型：

  | 卡片類型 | 一併完整閱讀 |
  |---|---|
  | 任務 | `description`、`customfield_10057`（規格）——欄位順序、畫面細節常只寫在規格 |
  | 漏洞 | `description`、`customfield_10059`（正確行為） |
  | 故事 | `description`、`customfield_10060`（使用者故事）、`customfield_10061`（規格） |

  這些欄位常提到「驗收條件清單沒單獨列出的路徑或細節」（曾漏驗第三條根因路徑；RD-8427 的欄位順序與「移除購買日／到期日」只寫在規格）。這類**不佔用正式條件編號**，在報告以「補充查核」獨立列出，同樣給 ✅／❌／⚠️ 之一，不能只提不判。

彙整成「待驗收清單」，供 Step 5 使用。

---

## Step 3：理解程式碼修復內容（diff-first）

在讀手冊、動手前先讀懂這次修復改了什麼；Step 6 的「補充查核」與論證法都要靠它。

1. **取得精確的變動檔案**：
   - 首選 GitHub `pull_request_read`（`get_files`）：直接給 PR 的檔案與 patch，不受班車分支漂移影響。
   - 交叉驗證：`git merge-base origin/<base> HEAD` 算出分支點，再 `git diff <merge-base>..HEAD --stat`。**不要**直接對 base 分支目前狀態跑 diff（班車會混入十幾個無關檔案）。變動檔案數應與 PR description 的調整內容吻合。
2. 找**共用的核心函式**：修復常抽出一支共用純函式，被多個呼叫端共用。理解它的輸入輸出契約，比逐一讀呼叫端快。
3. 對照 Step 2 的 `description`／規格／正確行為：每條根因路徑與規格細節，是否都能在 diff 找到對應修正。找不到的，代表可能沒修好，或需要進一步確認。
4. 讀 PR 新增的測試涵蓋哪些情境，並**實際跑一次**作為獨立證據（只跑 next 層；electron 層單測在本機有已知問題，不作依據）：
   ```bash
   npm run test:next:integration -- --skip-build <相對 test/next/integration/ 的路徑，例 salon/xxx.test.tsx>
   npm run test:next:unit -- <相對 next/ 的路徑>      # 單元不要加 --skip-build，加了會卡死（RD-8311 記錄）
   ```
   前景執行，tool timeout 約 240 秒；看到 `Test Files … passed` 才算。stderr 雜訊（如 `Missing Description…`、測試替身缺 `db.list` 的 `triggerCalcBestPromotion` TypeError）不是失敗，先看堆疊是否指向本 PR 新增的程式碼。啟動後 0% CPU、零輸出＝卡住，只殺**自己 worktree** 的 vitest 行程後重跑。也看專案的 `.claude/rules/testing-rules.instructions.md` 有沒有「曾被 mock 救援出假綠燈」的記載。

---

## Step 4：讀操作手冊

依序嘗試，找到能回答「怎麼操作」的來源就停：

1. `ragdoll-workspace:ragdoll-user-manual`（涵蓋範圍以其 `SKILL.md` 為準；美容模式、促銷、退貨等尚待補）。
2. `petpetgo-llm-wiki`：`wiki/ragdoll/` 對應功能模組頁面。
3. `ragdoll-workspace:ragdoll-project-knowledge`（在 Ragdoll worktree 內可用）：原始碼細節、呼叫鏈、型別契約。
4. Step 3 讀到的程式碼本身：UI 入口元件、JSDoc、測試的 `describe`／`it` 標題，常是最準確的操作步驟（例：美容模式切換器在 `item-input.tsx`，由 `handleModeSwitch` 處理）。

都查過仍找不到才標 ⚠️ 無法驗證（找不到操作方式的文件依據），**不要猜**。

**手冊缺口回饋**：驗收中摸索出手冊沒寫的操作路徑，在報告「建議補手冊」寫一句（入口 → 步驟），不要只留在這次對話。

---

## Step 5：盤點測試資料與實機操作

### 5.1 盤點測試資料（動手前）

逐條寫出：需要什麼資料（會員／寵物／月卡／單據、哪個門市、什麼狀態）→ 去哪查 → 缺口怎麼辦。

- 查 dev 中台：`mcp-wonderpet-table-local` 先 `javacat_switch_environment(env: "dev")`，**唯讀**。查詢陷阱、本機 DB 現成資料、發票條碼等食譜見 `references/test-data-recipes.md`。
- **留意門市維度**：機台的門市決定哪些資料算本店／他店（例如「帶入未付款銷售」只列本店單據；本機 `pos_store` 只有目前門市一列，查不到他店名稱）。
- **資料有缺口時**：不要寫入共用 dev 中台或本機 DB 去造資料。改走 Step 6 的**模擬資料法**；仍不可行才用論證法。

### 5.2 操作與證據

1. 依 Step 4 的步驟，用 `ragdoll-electron` 系列工具實際操作。
2. `read_electron_logs` 確認主控台；`ragdoll-sqlite-*` 的 `query` 確認資料落地（唯讀）。
3. **截圖存檔**：對應每條驗收條件的關鍵畫面，一律用 `electron_take_screenshot` 的 `outputPath` 存到暫存目錄，檔名帶卡號與條件編號（如 `RD-8427-c1-paid-cross-store.png`）。事後留言（Step 6b）要用，不要只留在對話裡。
4. 版面類條件先 `electron_get_viewport_size`：門市標準是 1024×768（DPR 2），在這個尺寸觀察才算數。
5. **操作鐵則**（細節與已知坑見 `references/electron-tool-pitfalls.md`）：
   - 工具回報「成功」≠ 狀態真的變了；每個關鍵點擊後截圖或讀狀態確認。
   - selector 先確認唯一（用 `electron_get_page_structure` 的 className 組合）。泛用 selector 會點到被彈窗遮住的背景元素。
   - 不要為了收尾去點「取消銷售」「確認結帳」「後付款」；不付款收尾用 **Escape** 逐層退出（結算彈窗按 Escape ＝放棄帶入）。
   - 完成結帳／付款需使用者同意（見授權分界）；條件不是非看落地資料不可時，用論證或模擬資料法。
   - **觸發實體列印會凍住整個 renderer**（Mac 開發環境無印表機）：條件不是明確要求確認紙本內容就不要點，改用 SQL 或程式碼論證（見 pitfalls 末節）。

### 5.3 涉及正式環境（production）

Claude Code 的自動模式分類器會直接擋下對 production 的查詢與寫入（不論透過 `javacat_switch_environment(env: "production")` 或其他工具）。這是平台層級的安全政策，**不是**工具故障，**不要**嘗試繞過（換帳號、換工具、用別環境的憑證硬闖）。這類條件標 ⚠️ 無法驗證（Claude Code 權限限制擋下 production 查詢，需使用者親自確認或明確授權後再繼續），並告知使用者卡在哪一步。

---

## Step 6：判定與回報（預設不留言 Jira）

每條驗收條件**只能**標三態之一，**MUST NOT** 發明「部分驗證」「大致通過」之類的第四態——使用者要的是「到底過了沒」：

- ✅ **通過** — 實際結果與條件一致（含條件本身就在測未開帳／未登入等邊界狀態、且行為符合預期）。
- ❌ **不通過** — 實際結果與條件不符（含邊界狀態條件行為不符；**不得**因環境未開帳／未登入改標「無法驗證」，因為那正是條件要求的情境）。
- ⚠️ **無法驗證** — 找不到操作方式的文件依據（Step 4 都查過）、環境一致性有疑慮（Step 0b 第 3 點）、條件不是在測邊界狀態卻因環境未就緒而操作失敗且自己建不起來（Step 0b 第 2 點），或涉及被平台擋下的 production 查詢（Step 5.3）。

**證據等級**（與三態並列，不是第四態；每條在「驗證方式」欄標明，讓 ✅ 的強度看得見）：

| 等級 | 說明 |
|---|---|
| 實機·真實資料 | 真實 dev 資料與流程 |
| 實機·模擬資料 | 真實元件與流程，但查詢回應在記憶體中被改寫；報告 MUST 明講改寫了什麼 |
| 論證 | 純函式論證或程式碼追蹤，無實機畫面 |

### 資料缺口時的兩種手段（優先序）

某條件描述的邊界資料在 dev 找不到，而安全地「真的造出來」需要寫共用資料時，**不要**硬湊實機重現的有風險寫入：

1. **模擬資料法（優先）**：在主程序以 inspector 包住 IPC 處理器，只在記憶體改寫回應，真實元件渲染。畫面可截圖，證據等級＝「實機·模擬資料」。做法、腳本範本、注意事項見 `references/memory-fixture.md`（腳本 `scripts/inspector-eval.mjs`）。
2. **純函式論證法**（模擬資料法不適用時，例如邊界狀態不是某個查詢回應造成的）：
   1. 用 Step 3 找到的核心函式，確認它是「純函式」：輸出只由某個 state（如 `member`）決定，沒有「查詢成功／失敗」的額外分支——「一開始就沒有」與「查詢失敗變成沒有」餵給函式的是同一個值。
   2. 分別驗證函式在「有效值」與「null／空」兩種真實輸入下的實際輸出（可經不同呼叫路徑各驗一種，例如一般非會員結帳驗 `member = null`，暫結還原／換購驗 `member = 有效會員`）。
   3. 在 Step 3 的 diff 閱讀中確認呼叫端在「失敗」情境同樣把 state 設回同一個 null／空值（確認呼叫順序），即可合併推論。
   4. 報告 MUST 寫出推論鏈（哪個函式、驗了哪兩種輸入、呼叫順序如何確認），不能只寫「邏輯上應該沒問題」。

### 回報

報告骨架（條件表＋證據等級、補充查核、自動化測試、**環境副作用**、建議補手冊、待確認、建議留言草稿）與留言草稿範本見 `references/report-and-comment.md`。

**預設 MUST NOT 呼叫任何 Jira 寫入工具**（`addCommentToJiraIssue`、`addOrEditJiraIssueComment`、`editJiraIssue`、`createJiraIssue`、`transitionJiraIssue`、`addWorklogToJiraIssue`、附件上傳）。把表格與草稿回報給使用者，等使用者明確要求才進 Step 6b。委派給 `ragdoll-acceptance-qa` subagent 時，這是該 agent 工具集的限制；由 orchestrator 或本 session 直接執行 SOP 時，是這條規則——**即使沒有 subagent 也一樣**。

---

## Step 6b：留言與截圖（僅在使用者明確要求時）

使用者明確要求留言（含「附上關鍵截圖」這類交辦），並指明哪張票時才做。留言與上傳是對外發布，不屬於驗收本身。

1. **選圖**：2–3 張，各對應一條或一組驗收條件；邊界或模擬類的補充圖寫進文字即可。每張先 `Read` 確認不含完整手機、地址、會員全名；有的話先遮蔽**副本**（用 PIL，不要用 `sips`，見 reference）。
2. **上傳並留言**：兩階段上傳取 `fileId`，以 `inlineFileId` 內嵌到 HTML 留言（**不要**再跑階段二，否則重複附檔）。流程與參數見 `references/report-and-comment.md` §三。
3. **內文寫給 PM／QA 看得懂的業務語言**（不要程式碼、函式名）；明講哪些是模擬資料；列出待確認事項。
4. **讀回確認**：留言內文完整、內嵌圖數正確、附件 `size` 與本機一致；回報 `commentId`。

---

## Step 7：驗收結束後清理環境

只在使用者明確表示「驗收完成」或要求清理時才做（含「留言完成後就清理」這類交辦），不要在 Step 6 回報完就自動清掉——使用者可能還要人工複查畫面。

1. **還原模擬資料**（若有用）：跑 `restore.js`，確認 `restored: true`，再跑 `hits.js` 確認 `wrapped: false`。
2. **停行程（用明確 PID）**：若 dev 是依 Step 0a-2 直接以 `run_in_background` 啟動的，先 `TaskStop` 該背景任務；`npm run dev` 的子行程有時不會隨父殼結束，所以一律再做下面的核對與清除：
   ```bash
   ps -eo pid,ppid,etime,command | grep <worktree 名>     # 列出自己 worktree 的行程
   kill <PID…>                                            # 先 SIGTERM
   lsof -nP -iTCP -sTCP:LISTEN | grep -E ":3100|:9222|:9229"   # 確認埠釋放；Next 的 PID 常不含 worktree 路徑，要靠埠找
   ```
   - **MUST NOT** 用 `pkill -9 -f "electron/dist/…"`／`pkill -f "next dev …"`：會殺掉整台機器上**所有** Ragdoll（含使用者或其他 session 的視窗）；`-f <worktree 名>` 還會比對到自己的 shell。
   - 本機 SQLite 是各 session 共用的，強殺（`-9`）可能留下沒寫完的 WAL；只有 SIGTERM 後仍殘留、且確認屬自己的 worktree 才用 `-9`（列印卡死是例外，見 pitfalls）。
3. **確認沒有自己的內容**：`git fetch origin <分支>`，`git rev-parse HEAD` 與 `FETCH_HEAD` **完全一致**，且 `git status --short` 為空 → 可安全移除。不一致（有你自己的 commit 或未提交變更）就不要清，告知使用者 worktree 路徑。
4. **移除 worktree**（依建立方式）：
   - 用 `EnterWorktree({name})` 建的 → `ExitWorktree(remove, discard_changes: true)`。
   - 用 `git worktree add` ＋ `EnterWorktree({path})` 進入的（Step 0a-2 的預設做法）→ `ExitWorktree(remove)` 會被拒（「not the owner」）。先 `ExitWorktree(keep)` 退回原目錄，再在**主 checkout** 用絕對路徑執行 `git worktree remove <路徑>`。`node_modules` 與 build 產物是 ignore 檔，**不需要 `--force`**；git 若拒絕，先看原因，不要盲目加 `--force`。用 `--detach` 建的沒有本機分支要刪。
5. **核對**：`git worktree list` 不再有該 worktree，主 checkout `git status` 乾淨。
6. **維持不動**：今日日結（開帳中是機台正常狀態，不要關）、其他 session 的 worktree 與行程。暫存目錄隨 job 清掉，需要留的證據應已在 Jira。
7. 最終回報列出清理結果，以及仍保留的狀態。

---

## 檔案索引

| 檔案 | 何時讀 |
|---|---|
| `references/electron-tool-pitfalls.md` | Step 5 操作前掃一遍；點擊或輸入不如預期時 |
| `references/test-data-recipes.md` | Step 5.1 盤點資料；發票條碼、跨配號週期、退換貨分流 |
| `references/memory-fixture.md`、`scripts/inspector-eval.mjs` | Step 6 資料缺口時的模擬資料法 |
| `references/report-and-comment.md` | Step 6 報告骨架；Step 6b 留言與截圖流程、範本 |
