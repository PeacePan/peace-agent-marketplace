---
name: ragdoll-acceptance-workflow
description: >
  Ragdoll POS-R（Jira Epic RD-7600）實機驗收的標準作業流程。定義依賴檢查、業務
  前置狀態檢查、驗收範圍界定（父系 Epic 必須是 RD-7600）、驗收條件擷取（
  customfield_10030 的 ADF 解析）、修復內容理解（diff-first）、實機操作判定
  方式、判定信心不足時的論證技巧、報告格式、驗收後環境清理，以及「agent 不
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

**選用依賴（缺少不擋流程，只在需要時才會用到）：**

- `ragdoll-workspace:ragdoll-user-manual` skill **實測目前不存在**（曾嘗試載入
  直接回傳 `Unknown skill`）。Step 4 已改為以 fallback 鏈處理，這裡不再把它列
  為硬性依賴，避免每次驗收都被一個不存在的 skill 卡住。
- `mcp-wonderpet-table-local`（javacat）MCP：只有當驗收情境需要**真實會員/
  優惠券資料**時才用得到（見 Step 5 的「測試資料查詢」）。本地唯讀 DB **不
  含**會員資料，Ragdoll 對會員的查詢一律打遠端 GraphQL，這不是「本地 DB 沒
  同步」，是設計上就不落地。

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

**判定規則（見 Step 6）**：只有「條件本身不是在測試邊界狀態、卻因環境未就緒
導致操作失敗」時才歸類「⚠️ 無法驗證」；條件本身就是在測邊界狀態時，一律依實際
觀察結果正常判定「✅ 通過」或「❌ 不通過」，不套用「無法驗證」escape hatch。

**實測發現：「開帳」不是一次性動作，MUST 允許自己執行開帳/登入來建立測試前提。**
第 2 類條件（正常流程）的前提環境常常需要**你自己**動手建立，而非要求使用者
先做好——只要是在專屬於這次驗收的隔離開發環境（自建的 worktree + `npm run dev`）
裡，登入銷售員、開帳都是低風險、可逆的本地操作，直接自己做，不要停下來問。
以下是實測中發現的兩個非顯而易見的坑：

- **本機開發資料庫是整台機器共用，不是依 worktree 隔離。** Ragdoll 的
  `offline-mutable.db`/`offline-readonly.db` 路徑固定在
  `~/Library/Application Support/Electron/data/<RAGDOLL_TARGET_ENV>/`，
  跟你在哪個 worktree 執行 `npm run dev` 無關。這代表：
  - 可能會看到**其他 session 或前幾天測試殘留**的已開帳紀錄（`offline_pos_report`
    的 `squared_at IS NULL`），日期是舊的。
  - 這種殘留紀錄雖然技術上「已開帳」，但畫面會判定「已超過營業時間」並擋下
    所有商品掃描/小計操作，提示「請先至功能選單重新開帳」。
  - **處理方式**：這不是 bug，是正常前置作業。先在功能選單執行一次「關帳」
    （closing 資料即使是別人開的也可以關），再「立即開帳」開一筆今天的新
    紀錄，即可正常操作。
  - 同理，這個 DB 是共用的，**不要**為了製造測試情境去直接改寫其中的資料列
    （例如改別人的銷售單、改本地 `user` 表的 disabled 欄位）——那會影響同
    機器上其他平行進行的 session。若真的需要用資料異動製造某個邊界狀態，
    參考 Step 6 的「純函式論證法」，優先用邏輯推論取代實際資料破壞。
- **銷售員登入/會員查詢的輸入框常是數字鍵盤 UI，不是純文字輸入框。**
  `electron_fill_input` 對這類欄位可能填得進去、但畫面顯示的是數字鍵盤的
  自訂 state，直接送出可能無效。保險做法：對每一位數字用
  `electron_click_by_text`（如 `"7"`）逐位點擊，或用 `electron_press_key`
  送單一按鍵，最後點擊/送出「確認」。

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
（`customfield_10060`）等欄位**發明新的獨立驗收條件編號**——那些不是判定
✅/❌ 的正式依據來源。

**但這不代表可以不讀那些欄位。** MUST 額外完整讀一次 `description` 與
`customfield_10059`（正確行為，Bug 類型卡片才有）。這兩個欄位常常用「敘事」
的方式描述根因，裡面可能提到**驗收條件清單沒有單獨列成一條的額外觸發路徑**
——例如某張票的驗收條件只寫了「情境 A」「情境 B」兩條，但 `description` 裡另外
敘述了開發階段才發現的「情境 C」，且修復本身也一併處理了。若不讀完整段落，
很容易漏驗這條路徑（曾實際發生：只看驗收條件清單會漏掉第三條根因路徑，
是使用者事後追問「正確行為有沒有真的修復」才逼出來的）。

處理方式：對於 `description`/正確行為中提到、但驗收條件清單沒有單獨列出的
額外路徑，**不要**佔用正式驗收條件的編號，而是在報告中以「補充查核」的方式
獨立列出（見 Step 6 的回報格式），並同樣給出 ✅/❌/⚠️ 三態之一的結論，不能只
提及不下判斷。

彙整結果為一份「待驗收清單」，供 Step 5 逐條驗證。

---

## Step 3：理解程式碼修復內容（diff-first，建立判定信心的基礎）

在讀操作手冊、動手操作之前，**先讀懂這次修復實際改了什麼**，理由：Step 6 的
「純函式論證法」與「補充查核」都需要以此為根據，光靠 Jira 描述或操作手冊猜測
運作方式，遇到不容易操作重現的邊界情境會判斷不出結果，也難以自信地給出結論。

1. 找出這次修復所在的分支與其對應的 base（通常是 `merge-base <base> HEAD`），
   跑 `git diff <base>..HEAD --stat` 看改了哪些檔案，再對每個核心邏輯檔案跑
   單檔 diff 細看。
2. 找出**共用的核心函式**：Ragdoll 的修復常常會抽出一支共用的純函式（例如
   `applyXxxToYyy(items, someState)`），被多個呼叫端（一般流程、暫結還原、
   換購、優惠券回滾……）共同呼叫。找到這支函式，理解它的輸入輸出契約，比
   分別去讀每個呼叫端更快建立全局理解。
3. 對照 Step 2 讀到的 `description`/正確行為敘述，逐條核對：每一條敘述的
   根因路徑，是否都能在 diff 裡找到對應的呼叫點被修正。找不到對應修正的
   路徑，代表可能沒有真的修好，或是需要進一步確認。
4. 若修復已經有專屬的自動化測試（同一批 commit 新增的 test 檔案），讀一下
   測試涵蓋了哪些情境、以及測試檔案/專案內部規則（如
   `.claude/rules/testing-rules.instructions.md`）有沒有記載「這個情境曾經
   被 mock 救援出假綠燈，已經改過測試寫法」這類線索——這代表這條路徑的自動
   化測試是可信的，可以作為信心來源之一。

---

## Step 4：讀操作手冊

先嘗試載入 `ragdoll-workspace:ragdoll-user-manual` skill。

**Fallback 鏈（依序嘗試，找到能回答「怎麼操作這個功能」的來源就停）：**

1. `ragdoll-workspace:ragdoll-user-manual`（優先用它，涵蓋範圍
   以其 `SKILL.md` 的路由涵蓋狀態表為準）。
2. `peace-wp-llm-wiki` skill：查 `wiki/ragdoll/` 底下對應功能模組的頁面（如
   `checkout-components.md`、`exchange-flow.md`），理解 UI 結構與操作入口。
3. `ragdoll-workspace:ragdoll-project-knowledge` skill（若在該 Ragdoll worktree
   內可用）：查原始碼細節、呼叫鏈、型別契約。
4. Step 3 已經做過的 diff 閱讀本身：程式碼的 JSDoc 註解、測試檔案的
   `describe`/`it` 標題，往往就是最準確的操作步驟說明。

若把以上來源都查過，仍然找不到某條驗收條件對應的操作方式（涵蓋範圍真的是
空白，不是你沒找到），才在報告中標記該條「⚠️ 無法驗證（找不到對應操作方式的
文件依據）」，不要憑空猜測操作方式。

---

## Step 5：實機操作驗收

對每一條驗收條件：

1. 依 Step 4 取得的操作步驟，用 `ragdoll-electron` 系列工具實際操作（點擊、輸
   入、截圖）
2. 用 `read_electron_logs` 確認主控台輸出
3. 用 `ragdoll-sqlite-mutable` 或 `ragdoll-sqlite-readonly` 的 `query` 確認資料
   是否正確落地
4. 每個關鍵操作後截圖存證

**實測環境操作注意事項：**

- **測試資料查詢（會員/優惠券）**：本地唯讀 DB **沒有**會員資料，Ragdoll 對
  `posmember` 的查詢一律打遠端 GraphQL。要準備一個真的能被 Ragdoll 查得到的
  測試會員，或需要查某會員持有的優惠券，用 `mcp-wonderpet-table-local` 的
  `javacat_find`，且**先**呼叫 `javacat_switch_environment(env: "dev")`（對應
  Ragdoll 的 `RAGDOLL_TARGET_ENV=development`）。查詢優惠券時若要用
  `couponEventName_type` 這類 join 出來的欄位當篩選條件，避免同時疊加日期範圍
  篩選——實測混用容易觸發後端 500，改成先撈較大 `limit` 再自己過濾。
- **商品的會員價/定價**：本地唯讀 DB 的 `item` 表就有，`price` 欄位＝會員價、
  `label_price` 欄位＝定價，兩者不同的商品才適合拿來測「會員價 vs 定價」類的
  驗收條件。
- **換購/退貨的紙本發票條碼驗證**：UI 會要求刷入 19 碼一維條碼才能繼續，格式
  是 `{民國年3碼}{結束月份2碼}{發票號碼10碼}{來源末4碼}`（結束月份是雙月配號
  期別的月份，公式邏輯見 `next/lib/utils/invoice/egui-period.ts` 的
  `getEGUIPeriod` 與 `invoice-verify-panel.tsx`），不是把發票號碼原文送出就
  能過。本地 `issue_invoice` 表可查到 `egui_no`，`offline_sale.name`（或
  `offlineReferenceName`）取末 4 碼當「來源末 4 碼」。
- **`ragdoll-electron` MCP 工具的已知眉角**：
  - Radix `DropdownMenu` / `Popover` 觸發鈕用 `electron_click_by_text` 點擊
    時，實測經常在同一次呼叫內被判定成「點了又點到外部」而立刻關閉，導致
    看起來「點了沒反應」。更穩定的做法：先點一次觸發鈕讓它拿到 focus，接著
    用 `electron_press_key(key: "Enter")` 開啟，選項用
    `electron_click_by_text` 或 CSS selector（如
    `[role="menuitem"]:nth-of-type(2)`）點擊。
  - 原生/Radix `<Select>` combobox 同理：點開後對選項用
    `electron_click_by_text` 常因為多個相近文字元素分數相近而點不中；改成
    「點開 combobox → `electron_press_key(Enter)` 選中目前高亮/預設的第一個
    選項」，或用 CSS selector 精準指定。
  - `electron_click_by_text` 對「包含中文字的較長字串」有時會因為內部拿去做
    `btoa` 編碼而直接丟出 `Latin1 range` 錯誤——這是工具本身的限制，不是操作
    錯誤，遇到就直接改用 `electron_click_by_selector` 配 CSS selector（`role`
    屬性、`:nth-of-type`、`#id` 皆可）繞過，不需要重試原本的呼叫。
  - 同一畫面出現多個文字相同/相近的按鈕（例如商品搜尋跟會員搜尋都有一顆
    「查詢」按鈕）時，`electron_click_by_text` 可能命中錯的元素。優先用
    `electron_fill_input` 鎖定該欄位、搭配 `electron_press_key(Enter)` 在該
    輸入框內送出，避免依賴按鈕文字比對。
- **涉及正式環境（production）的驗收條件**：Claude Code 的自動模式分類器會
  直接擋下對 production 的查詢/寫入動作（不論是透過 `javacat_switch_environment
  (env: "production")` 還是其他工具），這是平台層級的安全政策，**不是**工具
  故障，也**不要**嘗試繞過（換帳號、換工具、用別的環境的憑證硬闖）。這類條件
  一律標記「⚠️ 無法驗證（Claude Code 權限限制擋下 production 查詢，需使用者
  親自確認或明確授權後再繼續）」，並清楚告知使用者卡在哪一步，交由使用者
  親自確認或明確指示如何處理。

---

## Step 6：判定與回報（agent 不可留言 Jira）

每條驗收條件**只能**標記以下三態之一，**MUST NOT** 發明「部分驗證」「大致通過」
之類的模糊第四態來迴避給結論——使用者要的是「到底過了沒」，含糊的中間態等於
沒有回答問題：

- ✅ **通過** — 實際操作結果與條件描述一致（含條件本身就是在測「未開帳/未登入」
  等邊界狀態、且實際行為符合預期的情況）
- ❌ **不通過** — 實際操作結果與條件描述不符（含條件本身就是在測邊界狀態、但
  實際行為不符合預期的情況——**這類判定不得因為環境「未開帳/未登入」而改標
  「無法驗證」，因為未開帳/未登入正是條件本身要求的測試情境**）
- ⚠️ **無法驗證** — 手冊/文件依據找不到（Step 4 fallback 鏈都查過仍然空白）、
  環境一致性有疑慮（Step 0b 第 3 點）、條件本身不是在測邊界狀態卻因環境未就緒
  導致操作失敗（Step 0b 第 2 點），或涉及被平台權限擋下的 production 查詢
  （Step 5 最後一點）

**「純函式論證法」——當某條件描述的邊界狀態，安全地人工重現需要對共用/正式
資料做有風險的異動時使用：**

有些驗收條件描述的邊界狀態（例如「查詢會員失敗時」），在測試環境中要嚴格
按照字面重現，得讓某筆真實資料在操作當下真的變得「查不到」——這通常代表要
去改動其他 session 也在用的共用本機 DB，或去停用/啟用正式環境的測試帳號。
**不要**為了硬湊實機重現而執行這類有風險的資料異動（見 Step 0b 的共用 DB
警告）。改用以下推論鏈，一樣可以得出可稽核、有信心的 ✅/❌ 結論：

1. 用 Step 3 找到的核心函式，確認它是「純函式」：輸出只由某個 state（例如
   `member`）決定，程式碼裡**沒有**「查詢成功走一條路、查詢失敗走另一條路」
   的額外分支——不論這個 state 是「一開始就沒有」還是「查詢失敗變成沒有」，
   函式吃到的輸入都是同一個值，行為必然相同。
2. 分別驗證這支函式在「該輸入為有效值」與「該輸入為 null/空」兩種真實輸入下
   的實際輸出——即使是透過**不同的呼叫路徑**各驗證一種也算數（例如：從一般
   非會員結帳驗證 `member = null` 時的輸出，從暫結還原/換購驗證
   `member = 有效會員` 時的輸出）。
3. 兩種輸入都驗證過、且呼叫端在觸發「失敗」情境時同樣會把 state 設回同一個
   null/空值（於 Step 3 的 diff 閱讀中確認呼叫順序），即可合併推論：「查詢
   失敗」這個特定成因下的行為，等同於「輸入為 null」這個已驗證過的情況，
   可以據此下 ✅（或 ❌，如果驗證結果不符預期）的結論。
4. **回報時把這條推論鏈寫出來**（哪個函式、驗證了哪兩種輸入、呼叫順序如何
   確認），不能只寫「邏輯上應該沒問題」帶過——可稽核是重點，不是給個模糊
   的正面印象。

回報格式：

```markdown
## RD-XXXX 驗收結果

| # | 驗收條件 | 結果 | 驗證方式 | 判定依據 |
|---|---|---|---|---|
| 1 | <條件文字> | ✅ 通過 | 畫面 + SQL | <截圖描述 / log 摘錄 / SQL 查詢結果，或純函式論證鏈> |
| 2 | <條件文字> | ❌ 不通過 | 畫面 | <具體不符現象> |

### 補充查核（description/正確行為提及、但驗收條件清單未單獨列出的路徑）

| 路徑 | 結果 | 判定依據 |
|---|---|---|
| <從 description 讀到的額外根因路徑> | ✅ 通過 | <diff 追蹤鏈或實機驗證> |
```

**MUST NOT 呼叫任何 Jira 寫入工具**（`addCommentToJiraIssue`、`editJiraIssue`、
`createJiraIssue`、`transitionJiraIssue`、`addWorklogToJiraIssue`）。把上表 +
一份「建議留言草稿」文字一併回報給 orchestrator（呼叫你的上層對話），由
orchestrator 詢問使用者是否同意留言、同意後才由 orchestrator 自己呼叫留言工具。
這條規則不是「請不要做」的提醒，而是這個 agent 的工具集本身就不包含 Jira 寫入
工具（見 `ragdoll-acceptance-qa` agent 定義）。

---

## Step 7：驗收結束後清理環境

只在使用者明確表示「驗收完成」或要求清理時才執行，不要在 Step 6 回報完就自動
清掉——使用者可能還要接著人工複查畫面。

1. 停止背景執行的 `npm run dev`（用 `TaskStop` 停掉對應的背景任務），並用
   `ps aux` 確認沒有殘留綁定該 worktree 路徑的 Electron/Next 程序（`npm run
   dev` 的子程序有時不會隨父殼一起結束）。
2. 若驗收環境是透過 `EnterWorktree` 建立的獨立 worktree：先確認裡面沒有你
   自己產生的未推送內容——比對 worktree 目前 HEAD 與遠端對應分支
   （`origin/<branch>`）的 commit hash 是否**完全一致**。一致才代表這個
   worktree 除了 checkout 既有分支之外沒有任何屬於這次驗收工作自己產生的
   東西，可以安全用 `ExitWorktree(action: "remove", discard_changes: true)`
   清除。若不一致（有你自己的 commit 或未提交變更），改用
   `action: "keep"` 並明確告知使用者 worktree 路徑，不要自行決定丟棄。
