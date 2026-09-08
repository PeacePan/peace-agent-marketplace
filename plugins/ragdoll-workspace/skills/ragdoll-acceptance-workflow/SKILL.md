---
name: ragdoll-acceptance-workflow
description: >
  Ragdoll POS-R（Jira Epic RD-7600）實機驗收的標準作業流程。定義依賴檢查、業務
  前置狀態檢查、驗收範圍界定（父系 Epic 必須是 RD-7600）、驗收條件擷取（
  customfield_10030 的 ADF 解析）、實機操作判定方式、報告格式，以及「agent 不
  可留言 Jira，只能回報草稿」的規則。當使用者要求對某張 POS-R ticket 做實機驗
  收時使用。
---

# Ragdoll POS-R 實機驗收 SOP

## 適用範圍

本流程只適用於父系 Epic 是 **RD-7600（POS-R）** 的 Jira ticket。驗收的是「使用
者明確指定的單一 ticket」，不是「給一個 Epic、自動列出所有子卡逐一驗收」。

---

## Step 0a：工具依賴檢查（MUST，任何一項缺失就停止）

| 檢查項 | 方法 | 缺失時的訊息 |
|---|---|---|
| `wonderpet-general:jira-overview` skill | 用 `Skill` 工具嘗試載入 | 「缺少 wonderpet-general plugin（找不到 jira-overview skill），請先安裝該 plugin 後再繼續」 |
| `ragdoll-runtime-debugging-usage` skill | 用 `Skill` 工具嘗試載入 | 「缺少 ragdoll-runtime-debugging plugin（找不到 skill 說明），請先安裝該 plugin」 |
| `ragdoll-electron` MCP | 呼叫 `get_electron_window_info` | 工具不存在 → 「缺少 ragdoll-runtime-debugging plugin，請先安裝」；工具存在但找不到 app/port → 「Ragdoll 尚未啟動，請先在 Ragdoll 專案目錄執行 `npm run dev` 後再繼續」 |
| `ragdoll-sqlite-mutable` / `ragdoll-sqlite-readonly` MCP | 各呼叫一次 `list_tables` | 同上邏輯區分「未安裝」vs「DB 檔案不存在（Ragdoll 未啟動過，或 `RAGDOLL_TARGET_ENV` 指向錯的環境）」 |

四項全部通過才進入 Step 0b。

---

## Step 0b：業務前置狀態確認（MUST——用來正確分類結果，不是無條件擋在 Step 4 之前）

`/checkout` 對「未開帳」與「未登入銷售員」有全面性攔截（見
`next/app/checkout/page.tsx:149-165` 的 `isCheckoutDisabled` / `guardCheckout`）。
**但 MUST NOT 把「未開帳/未登入」直接當成無條件的硬性前置門檻**：POS-R 有不少
驗收條件本身描述的就是「未開帳／未登入／跨日未關帳」這類邊界狀態下按鈕該有的
行為（例如 RD-8153「尚未開帳時點擊『銷售查詢(退換貨)』按鈕 → 按鈕可點擊並顯示
提示」），若在進 Step 4 前一律要求先開帳、先登入，會讓這類條件永遠無法被驗證
——這是初版 SOP 在 dry run（見 Task 6）中發現的真實設計缺陷，已修正如下。

**MUST** 在進入 Step 4 前，先讀懂**每一條**驗收條件本身描述的情境：

1. **條件本身就是在描述「未開帳／未登入／跨日未關帳」等邊界狀態下的行為**
   （例如「尚未開帳時點擊 X」「銷售員未登入時點擊 Y」）→ **不要**先幫使用者
   開帳或登入，直接在目前的真實邊界狀態下操作、觀察、判定通過/不通過。
2. **條件描述的是正常結帳流程的一部分**（例如「掃碼後小計金額正確」）→ 這類
   條件的前提是環境已經就緒，此時才需要依序確認：
   - **開帳狀態**：用 `electron_take_screenshot` 或 `electron_eval` 讀取畫面/
     store 狀態，確認 `reportStatus === 'OPENED'`。不符 → 該條標記
     「⚠️ 無法驗證（環境未開帳，且此條件本身不是在測試未開帳行為）」，
     並回報「請先在功能選單執行開帳後再重新驗收此條件」，**不要**標「不通過」。
   - **銷售員登入狀態**：確認畫面上已顯示登入的銷售員。不符 → 同上邏輯標記
     「⚠️ 無法驗證」並提示「請先登入銷售員」。
3. **環境一致性**（不論條件屬於哪一類都要確認一次）：確認
   `ragdoll-sqlite-mutable`/`readonly` 查到的資料是使用者預期的環境
   （`RAGDOLL_TARGET_ENV`，預設 `development`，需在啟動 Claude Code**之前**
   設定，事後改不會生效）。若查詢結果明顯與使用者描述的情境對不上，回報
   「目前連到的環境可能是 `<猜測值>`，與你描述的情境不符，請確認
   `RAGDOLL_TARGET_ENV` 設定」，停止並等待使用者確認後再繼續（這條無法 100%
   自動判定，只能盡力提示）。

**判定規則（見 Step 5）**：只有「條件本身不是在測試邊界狀態、卻因環境未就緒
導致操作失敗」時才歸類「⚠️ 無法驗證」；條件本身就是在測邊界狀態時，一律依實際
觀察結果正常判定「✅ 通過」或「❌ 不通過」，不套用「無法驗證」escape hatch。

---

## Step 1：驗收範圍界定（POS-R = RD-7600 校驗，含邊界情況）

1. 使用者給一張 ticket 卡號（例：`RD-8153`）。
2. 若使用者給的卡號本身就是 `RD-7600` → 停止並回報：「RD-7600（POS-R）本身是
   Epic，請指定其底下的具體 ticket 卡號」。
3. 呼叫：

```
mcp__claude_ai_Atlassian__getJiraIssue(
  cloudId: "f338306a-4b54-421e-9209-2e9f451c67f7",
  issueIdOrKey: "<使用者指定的卡號>",
  fields: ["summary", "issuetype", "parent", "customfield_10030"]
)
```

   若呼叫失敗（查無此卡 / 無權限）→ 停止並回報：「查無 `<卡號>` 或沒有讀取權限，
   請確認卡號是否正確」。

4. 若回傳結果**沒有 `parent` 欄位**（無父系卡片）→ 停止並回報：「⚠️ 無法確認範圍：
   此卡沒有父系 Epic，無法判斷是否屬於 POS-R（RD-7600），請確認後再指定」。
   **這與「明確不屬於」不同，不可當成拒絕處理**（避免對資料缺失的卡片產生使用者
   無法覆寫的假陰性）。
5. 若 `parent.key === "RD-7600"` → 屬於 POS-R 範圍，繼續 Step 2。
6. 若 `parent.key !== "RD-7600"`：
   - 檢查 `parent.fields.issuetype.name`：若**不是**「大型工作」（代表這張卡是
     Subtask，`parent` 指向的是它的父 Task 而不是 Epic）→ 對 `parent.key` 再做
     一次相同的 `getJiraIssue` 查詢（只遞迴這一次，最多往上兩層），把新查到的
     `parent` 拿來重複步驟 4-6 的判斷。
   - 若 `parent.fields.issuetype.name` **是**「大型工作」但 key 不是 `RD-7600`
     → **明確拒絕**：「此卡（`<卡號>`）的父系 Epic 是 `<parent.key>`
     （`<parent.fields.summary>`），不是 POS-R（RD-7600），本 skill 僅適用於
     Ragdoll POS-R 範圍，無法驗收」，停止流程。

**已實測案例**：`RD-8144` 的 `parent.key` 為 `"RD-7600"`，`parent.fields.summary`
為 `"POS-R"`，`parent.fields.issuetype.name` 為 `"大型工作"`。

---

## Step 2：解析驗收條件（`customfield_10030`）——通用 ADF 文字抽取器

`customfield_10030` 回傳 ADF `doc`，`content` 陣列可能包含以下任一種寫法，**三種
都要能解析**：

1. **`taskList`**（checklist 寫法）：`content` 是多個 `taskItem`，每個 `taskItem`
   的 `content` 是內文節點（通常是一個 `text`）。
   ```json
   {"type":"taskList","content":[
     {"type":"taskItem","content":[{"type":"text","text":"驗收條件文字"}],
      "attrs":{"localId":"...","state":"TODO"}}
   ]}
   ```
   **忽略 `attrs.state`**（那是 Jira 上是否被手動勾選過，跟驗收判定無關）。

2. **`bulletList` / `orderedList`**（項目符號/編號清單寫法）：`content` 是多個
   `listItem`，每個 `listItem.content` 通常是一個 `paragraph`，`paragraph.content`
   才是實際的 `text` 節點（比 `taskList` 多一層）。

3. **頂層 `paragraph`**（純文字寫法）：`paragraph.content` 是 `text` 節點。

**抽取規則（一律適用）：**

- 把每個 `taskItem`、每個 `listItem`、每個「`doc.content` 頂層的 `paragraph`」
  視為**一條獨立的驗收條件邊界**的起點。
- 在邊界內遞迴收集所有 `text` 節點的內容串接成該條件的文字。
- **`hardBreak` 節點也視為條件邊界**（作者常用 Shift+Enter 手動換行，在同一個
  `paragraph`/`taskItem` 裡塞好幾條條件，而不是規規矩矩用清單語法）——遇到
  `hardBreak` 就把目前收集到的文字結算成一條條件，重新開始收集下一條。
- 收集完後，去除每條條件前後的空白字元。

**若最終解析出 0 條** → **MUST 停止並回報**：「無法從 `customfield_10030` 解析出
任何驗收條件，請確認該卡是否已填寫驗收條件」。**MUST NOT** 自行從「規格」
（`customfield_10057`）、「正確行為」（`customfield_10059`）、「使用者故事」
（`customfield_10060`）等欄位推導驗收條件——那些是理解上下文用的輔助欄位，不是
判定依據的來源。

彙整結果為一份「待驗收清單」，供 Step 4 逐條驗證。

---

## Step 3：讀操作手冊

載入 `ragdoll-workspace:ragdoll-user-manual` skill，依驗收條件內容判斷涉及哪個
入口/功能（涵蓋範圍以 `ragdoll-user-manual/SKILL.md` 的路由涵蓋狀態表為準）。
若條件涉及尚未撰寫手冊的範圍，在報告中標記該條「⚠️ 無法驗證（手冊尚未涵蓋此
範圍）」，不要憑空猜測操作方式。

---

## Step 4：實機操作驗收

對每一條驗收條件：

1. 依 Step 3 取得的操作步驟，用 `ragdoll-electron` 系列工具實際操作（點擊、輸
   入、截圖）
2. 用 `read_electron_logs` 確認主控台輸出
3. 用 `ragdoll-sqlite-mutable` 或 `ragdoll-sqlite-readonly` 的 `query` 確認資料
   是否正確落地
4. 每個關鍵操作後截圖存證

---

## Step 5：判定與回報（agent 不可留言 Jira）

每條驗收條件標記三態之一：

- ✅ **通過** — 實際操作結果與條件描述一致（含條件本身就是在測「未開帳/未登入」
  等邊界狀態、且實際行為符合預期的情況）
- ❌ **不通過** — 實際操作結果與條件描述不符（含條件本身就是在測邊界狀態、但
  實際行為不符合預期的情況——**這類判定不得因為環境「未開帳/未登入」而改標
  「無法驗證」，因為未開帳/未登入正是條件本身要求的測試情境**）
- ⚠️ **無法驗證** — 手冊未涵蓋此範圍、環境一致性有疑慮（Step 0b 第 3 點），
  或者**條件本身不是在測邊界狀態、卻因環境未就緒（未開帳/未登入）導致操作
  失敗**（Step 0b 第 2 點的情況）

回報格式：

```markdown
## RD-XXXX 驗收結果

| # | 驗收條件 | 結果 | 驗證方式 | 判定依據 |
|---|---|---|---|---|
| 1 | <條件文字> | ✅ 通過 | 畫面 + SQL | <截圖描述 / log 摘錄 / SQL 查詢結果> |
| 2 | <條件文字> | ❌ 不通過 | 畫面 | <具體不符現象> |
```

**MUST NOT 呼叫任何 Jira 寫入工具**（`addCommentToJiraIssue`、`editJiraIssue`、
`createJiraIssue`、`transitionJiraIssue`、`addWorklogToJiraIssue`）。把上表 +
一份「建議留言草稿」文字一併回報給 orchestrator（呼叫你的上層對話），由
orchestrator 詢問使用者是否同意留言、同意後才由 orchestrator 自己呼叫留言工具。
這條規則不是「請不要做」的提醒，而是這個 agent 的工具集本身就不包含 Jira 寫入
工具（見 `ragdoll-acceptance-qa` agent 定義）。
