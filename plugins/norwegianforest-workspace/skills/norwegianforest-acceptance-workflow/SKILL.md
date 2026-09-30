---
name: norwegianforest-acceptance-workflow
description: >
  NorwegianForest（中台表格與腳本，Jira 常標 NorCat）ticket 的驗收標準作業流程。涵蓋讀卡與範圍界定、
  驗收條件解析、diff-first 理解修改內容、確認 dev 表格是否已 patch 到待驗收版本、在 dev 環境用 javacat MCP
  與 javacat-graphql-client 逐條實測（表格 schema、policy／hook、function 呼叫、TodoJob／cron、
  大哥付／NetSuite 等外部服務串接）、三態判定、驗收條件與實作不一致的處理、報告格式、
  「agent 不可留言 Jira」規則，以及測試資料與 worktree 的清理。只要使用者要求驗收、驗證、
  確認某張中台／NorCat／NorwegianForest 的 RD ticket 是否完成，或說「幫我驗收 RD-XXXX」「這張卡過了沒」
  「dev 上測一下這個函式」「對照驗收條件跑一遍」，即使沒有明說 NorwegianForest，只要異動落在
  NorwegianForest 目錄，都應使用此 skill。
---

# NorwegianForest 驗收 SOP

## 適用範圍與定位

驗收的是「使用者明確指定的單一 ticket」，不是「給一個 Epic、自動展開所有子卡」。適用於異動落在
`NorwegianForest/`（tables、scripts、tests）的 ticket。同一張卡若同時包含 NorwegianForest 以外的異動，
本流程只處理 NorwegianForest 的部分；其餘部分不在本流程範圍，以其自身的單元測試為基礎，需要實測時比照
本流程 Step 5，並先取得使用者同意。

NorwegianForest 驗收有下列特性，整套流程都圍繞這些特性設計：

| 面向 | NorwegianForest 驗收 |
|---|---|
| 驗收對象 | 遠端表格定義（schema／policy／hook／function／TodoJob）與資料 |
| 執行環境 | **共用的 dev 中台**，多張卡同時在用 |
| 程式碼何時生效 | 必須先 **patch 進 dev 表格**才生效，沒 patch 就等於沒驗到這張卡 |
| 操作工具 | javacat MCP（讀、寫，寫入有人工確認）、javacat-graphql-client（呼叫 function） |
| 副作用範圍 | 共用 dev 資料，且常連到外部系統（簡訊、金流測試站、NetSuite） |
| 最容易出錯之處 | 條件、實作、PR 描述三者各自過時；dev 跑的不是待驗收版本 |

## 核心原則（為什麼這樣做）

1. **先證明 dev 上跑的是待驗收版本，再談結果。** 沒 patch 的 dev 跑出來的任何結果都不算數，還可能讓人誤以為修復無效或有效。
2. **驗收的對象是「條件、實作、PR 描述」三者的一致性，不只是逐條打勾。** 條件文字可能被後來的決策取代、PR 描述可能寫了程式碼沒做的事；發現不一致要如實列出，不能為了通過而曲解條件。
3. **證據是資料落地，不是函式回傳值。** 每次操作後用 MCP 回查資料表，才知道紀錄真的變成那樣。
4. **有外部副作用的操作，先取得使用者同意再做。** 簡訊、金流、NetSuite 都不可逆，也可能打擾到真人。
5. **不繞過為人設計的確認關卡、不寫 production、不寫 Jira。** 這些是使用者的決定，不是 agent 的。

---

## Step 0：工具與環境依賴檢查（任何一項缺失就停止並說明）

| 檢查項 | 方法 | 缺失時的訊息 |
|---|---|---|
| Atlassian MCP | 嘗試 `mcp__claude_ai_Atlassian__getJiraIssue` | 「缺少 Atlassian MCP，無法讀取 ticket」 |
| `wonderpet-general:jira-overview` skill | `Skill` 載入 | 「缺少 wonderpet-general plugin，請先安裝」 |
| javacat MCP 已登入 dev | `javacat_switch_environment(env: "dev")`，再對任一小表做一次帶日期範圍的 `javacat_find` | 未登入會跳出登入對話，由使用者填寫，不要替使用者填帳號 |
| `gh` CLI | `gh auth status` | 「gh 尚未登入」 |
| javacat-graphql-client（只有需要呼叫 function 時才檢查） | `scripts/call-dev-function.cjs --dry` 會自動尋找；找不到就設定 `JAVACAT_GRAPHQL_CLIENT_PATH` | 「找不到 javacat-graphql-client」 |

**已實測：javacat MCP 沒有「呼叫 function」的工具。** 工具清單只有 find／count／summarize／insert／update／list_tables／get_table_schema／login／switch_environment，不要花時間找。function 類的條件改用 `scripts/call-dev-function.cjs`（細節見 `references/verification-methods.md`）。

MCP 使用細節（filter 語法、查詢必給日期範圍、預設只查未封存）以 `anthropic-skills:mcp-wonderpet-table-usage` 為準。

---

## Step 1：讀卡並界定範圍

1. 先看 `issuetype` 再解讀欄位，不同類型的欄位不一樣：任務（規格 `customfield_10057`）、漏洞（正確行為 `customfield_10059`、上線版本 `customfield_10038`）、故事（使用者故事 `customfield_10060`、規格 `customfield_10061`）。欄位總表在 `wonderpet-general:jira-overview`。
2. 呼叫（cloudId 為 `f338306a-4b54-421e-9209-2e9f451c67f7`）：

   ```
   getJiraIssue(
     cloudId, issueIdOrKey: "<使用者指定的卡號>",
     fields: ["summary","description","issuetype","status","parent","labels","issuelinks",
              "customfield_10030","customfield_10031","customfield_10033",
              "customfield_10057","customfield_10058","customfield_10059","customfield_10266"],
     responseContentFormat: "markdown"
   )
   ```

   查無此卡或無權限 → 停止並回報。
3. **判斷是否屬於 NorwegianForest**（依序，任一成立即可）：
   - 分支欄位 `customfield_10033` 含 `norwegianforest`
   - 對應 PR 異動檔案含 `NorwegianForest/`（`gh pr view <PR> --json files`）
   - summary 前綴為 `[NorCat]` 或 `[NorwegianForest]`

   都不成立 → 停止並回報「看不出這張卡有中台異動，請確認卡號或改用其他驗收流程」。分支欄位是空的，用 `gh pr list --search "<卡號>" --state all` 找 PR。
4. 記錄 PR 的 `state`、`baseRefName`、`headRefName`、最新 commit。PR 還是 open 時，修改內容只存在於 PR 分支，驗收要以該分支為準；已 merge 則依 base 分支（`master`、`release/norwegianforest` 等）。
5. 看 `issuelinks` 裡「is blocked by」的前置卡是否完成（例如先建表的任務）。前置卡未完成不擋流程，但要在報告中標註風險。
6. 記下驗收者欄位 `customfield_10031`，報告要交給誰。

---

## Step 2：解析驗收條件

`customfield_10030` 用 markdown 格式讀回時，通常是一行一條的 `- [ ]` 清單。忽略勾選狀態（那只是 Jira 上有沒有被手動勾過，跟判定無關）。若拿回 ADF，taskList、bulletList／orderedList、頂層 paragraph 三種寫法都要能解析，`hardBreak` 也視為條件邊界。

**解析出 0 條 → 停止並回報**，不要從規格或正確行為自己發明驗收條件；那些欄位不是判定 ✅／❌ 的正式依據。

**但仍要完整讀 `description`、規格、正確行為與討論紀錄（`customfield_10266`）**，目的有兩個：

- 找出條件清單沒有單獨列成一條的額外路徑，這類路徑要在報告中另立「補充查核」，同樣給三態結論。
- **找出與條件矛盾、或已被後續決策取代的敘述。** 條件文字可能停在舊版設計（例如條件寫「不會呼叫外部服務」，討論紀錄卻記載了後來決定改由外部服務判定）。這類落差不要悄悄選一邊，要獨立列在報告的「條件與現況的落差」。

整理成待驗收清單時做兩件事：

1. **拆分含多個斷言的條件。** 一條條件若同時包含可獨立判定的多個斷言（例如「立即報錯」與「紀錄仍保留」，或「業務失敗」與「連線逾時」），拆成 a／b 子項，各自判定。這樣不需要發明「部分通過」這種模糊狀態。
2. 為每一條標註驗證類型（表格結構、資料讀寫、policy／hook、function、TodoJob／cron、外部串接、失敗路徑），對照 `references/verification-methods.md` 決定用什麼工具、需要什麼前置。

**列完清單後，把「需要外部副作用」與「需要使用者動手」的項目一次問完**（例如要發簡訊的測試對象、需要使用者執行 patch），不要每條驗到一半才停下來問。

---

## Step 3：diff-first——讀懂被驗收的程式碼

驗收之前先讀懂實際改了什麼，否則遇到不好重現的情境（斷網、逾時）就沒有論證的依據。

1. `git fetch origin <PR 分支>`，用 **merge-base** 算真正的分支點再比對，不要直接對 base 分支目前的狀態跑 diff（base 會持續有別的 PR 合進來，混入無關檔案）：

   ```bash
   git merge-base origin/<base 分支> origin/<PR 分支>
   git diff <merge-base>..origin/<PR 分支> --stat
   ```

   異動檔案數應與 PR 描述的檔案表格吻合。
2. 在表格定義檔（`NorwegianForest/tables/.../<表名>.ts`）找 `functions[].name`（**呼叫時用的是這個名稱，多半是中文，不是腳本檔名**）、`policies`、hooks，再對應到 `scripts/` 下的腳本與它底部宣告的 `Args` 型別。
3. 逐條對照驗收條件：每一條在 diff 裡對應哪支腳本、哪個測試。找不到對應的條件，代表可能沒實作或需要進一步確認。
4. **對照 PR 描述與程式碼**：描述宣稱的行為是否真的在程式碼裡。描述與程式碼不一致是要回報的發現，不是可以略過的小事。
5. 看已有的單元測試涵蓋哪些條件（看 `describe`／`it` 標題）。單元測試是輔助證據，不能取代 dev 實測。

---

## Step 4：確認 dev 上跑的是待驗收版本

1. 讀 dev 上該表的定義：

   ```
   javacat_find(table: "__table__",
     filters: [{bodyConditions:[{fieldName:"name", valueType:"STRING", operator:"in", string:"<表名>"}]}],
     selects: ["body.name","body.version","_updatedAt","_updatedBy"], skipLines: true)
   ```

   （用表名精確定位，不需日期範圍。）
2. 和 PR 分支的表格定義檔 `body.version` 比對：
   - dev 版號比分支低 → **尚未 patch**，需要使用者動手。
   - 版號相同 → 只能說「可能已 patch」。**dev 的 patch 不做版本檢查**（`bin/table.sh` 對 dev 明示「開發環境不檢查版本差異」），同版號不保證內容一致。再用行為探針確認：呼叫時出現「找不到函數 …」代表 dev 還沒有該函式；新舊版本行為不同的地方，用一次無副作用的呼叫比對錯誤訊息。
3. **需要 patch 時由使用者執行**，原因是這會覆寫共用 dev 的表格定義，可能蓋掉別人尚未合併的變更，而且腳本首次執行會詢問使用者編號與信箱。告訴使用者確切指令並暫停等待：

   ```bash
   git checkout <PR 分支>
   cd NorwegianForest
   npm run patch:dev <表名1>,<表名2>     # 只 patch 這張卡異動的表，逗號分隔
   ```

4. **staging／production 不在合併前的驗收範圍。** `bin/table.sh` 限制 staging 只能從 `staging/*` 分支、production 只能從 `release/*` 或 `hotfix/*` 分支 patch，功能分支合併前只能到 dev。報告要註明「僅在 dev 驗收，staging 驗收需合併後進行」。
5. **本機單元測試基線**（建議做，不是必要）：在 worktree 內對受影響的測試資料夾跑一次，確認修改內容本身沒有回歸。全新 worktree 有三個坑，配方見 `references/verification-methods.md`。

---

## Step 5：逐條實測

實測的手法、工具配方與坑集中在 `references/verification-methods.md`，這裡只列原則：

- **測試資料以「卡號-用途-序號」命名**（例如銷售單編號 `RD8070-ACC-01`），金額用小額，方便事後清理，也讓其他人一眼看出是驗收殘留。
- **每次操作後用 MCP 回查資料表**，再下結論。
- **function 呼叫走 `scripts/call-dev-function.cjs`**；資料寫入一律走 MCP 的 `javacat_insert`／`javacat_update`，讓人工確認關卡保留，**不要用腳本繞過**。
- **外部副作用要事先問**：打哪個環境、誰會收到簡訊、測試對象是否已被對方登記。只打一次，失敗的回應本身就是證據，不要用重試迴圈去「試出」成功。
- **不確定錯誤出在哪一層時由外而內定位**：呼叫端 → NorwegianForest function → 外部服務。用錯誤訊息的格式回到程式碼找出處，確認是哪一層產生的。
- **不可行的情境不要硬湊**：斷網、逾時、production 這類無法或不該在 dev 重現的條件，標 ⚠️ 並引用單元測試當輔助證據，不要標 ✅。
- 涉及 production 的驗收條件，平台的安全分類器會擋下查詢或寫入，這不是工具故障，也不要換帳號或工具繞過。標 ⚠️，交由使用者親自確認。

---

## Step 6：判定

每一條（或每個子項）只能是三態之一：

- ✅ **通過**：實際結果與條件一致，且有資料落地的證據。
- ❌ **不通過**：實際結果與條件不符。
- ⚠️ **無法驗證**：環境或權限不允許（未 patch、staging 尚不可驗、production 被擋、外部測試對象未登記、無法模擬的失敗情境）。**必須寫明卡在哪、需要誰做什麼才能解開。**

不使用「部分通過」「大致通過」。條件有多個斷言就拆子項，各給三態。

**「條件與現況的落差」不算條件不通過，也不算通過**，獨立成一節，寫明：條件原文、現況（程式碼或決策）、落差是什麼、建議的處理方式（修改條件文字，或修改實作）。決定權在使用者或 PM。PR 描述與程式碼不符也列在這一節。

**單元測試全綠不等於 ✅。** 它證明程式碼在 mock 環境下的行為，dev 實測證明的是整條路徑。只有單元測試佐證的條件，判 ⚠️ 並說明。

---

## Step 7：回報（agent 不可留言 Jira）

報告格式與 Jira 留言草稿範本見 `references/report-template.md`。必須包含：驗收環境與版本資訊（分支、commit、dev 表格版號）、條件判定表、補充查核、條件與現況的落差、測試資料殘留清單、未涵蓋範圍。

**不呼叫任何 Jira 寫入工具**：`addCommentToJiraIssue`、`editJiraIssue`、`createJiraIssue`、`transitionJiraIssue`、`addWorklogToJiraIssue`。只提供「建議留言草稿」，使用者同意後才由使用者或主 session 留言。PR 留言同理：使用者要文案就只給文案，不主動貼、不主動改變 PR 狀態。

---

## Step 8：收尾與清理

只在使用者明確表示驗收完成、或要求清理時才做，不要回報完就自動清掉，使用者可能還要複查。

1. **列出測試資料殘留**（表名、紀錄編號、目前狀態）交給使用者決定。javacat MCP 沒有封存或刪除的工具，不要為了「整理乾淨」擅自把測試紀錄改成終態。
2. 確認暫存的憑證副本已刪除（`call-dev-function.cjs` 會自動刪）。
3. **清 worktree**：
   - worktree 若用符號連結借了主 checkout 的 `node_modules`，先用不帶 `-r`、不帶尾斜線的 `rm` 移除這些連結，再移除 worktree，避免波及主 checkout。
   - 比對 worktree 的 HEAD 與 `origin/<分支>`。有未推送的 commit 時**不要用 `ExitWorktree(remove)`**（它會連分支一起刪）；改用 `ExitWorktree(keep)` 離開，再手動 `git worktree remove --force <路徑>`，保留分支。
   - `EnterWorktree({name})` 是從目前 HEAD 切出新分支，不是從 origin；驗收 PR 分支時用 `git checkout -B <PR 分支> origin/<PR 分支>` 切過去，並核對 HEAD 雜湊值。

---

## 延伸參考

- `references/verification-methods.md`：各驗證類型對應的工具、function 呼叫配方、外部系統測試、冪等性驗證、本機單元測試、常見陷阱
- `references/report-template.md`：報告格式與 Jira 留言草稿
- `references/worked-example-rd-8070.md`：一次完整驗收的實例，可看每一步實際遇到什麼
- 相關 skill：`norwegianforest-workspace:norwegianforest-testing-architecture`（單元測試架構）、`javacat-table-architecture`（表格定義）、`function-script-context`（腳本撰寫背景）、`javacat-todojob-mechanism`（TodoJob 狀態機）、`pos-knowledge-base`（POS 業務）
