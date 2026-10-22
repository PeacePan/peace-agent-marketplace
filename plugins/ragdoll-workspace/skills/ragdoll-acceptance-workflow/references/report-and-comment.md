# 報告骨架與留言流程

Step 6（回報）與 Step 6b（留言）用。**預設只回報、附留言草稿；使用者明確要求才留言。**

## 一、回報骨架（Step 6）

```markdown
## RD-XXXX 驗收結果

**驗收版本**：PR #NNNN（commit <sha>，狀態 <open/draft/merged>，base <分支>）
**環境**：Ragdoll vX.Y.Z、<RAGDOLL_TARGET_ENV>、門市／機台、視窗 1024×768

| # | 驗收條件 | 結果 | 驗證方式（證據等級） | 判定依據 |
|---|---|---|---|---|
| 1 | <條件文字> | ✅ 通過 | 實機·真實資料 | <截圖檔名 / log 摘錄 / SQL 結果> |
| 2 | <條件文字> | ✅ 通過 | 實機·模擬資料 | <截圖＋fixture 命中紀錄；說明改寫了什麼> |
| 3 | <條件文字> | ❌ 不通過 | 實機·真實資料 | <具體不符現象> |
| 4 | <條件文字> | ⚠️ 無法驗證 | — | <卡在哪一步、需要使用者做什麼> |

證據等級：**實機·真實資料**（真實 dev 資料與流程）／**實機·模擬資料**（真實元件，但查詢回應在記憶體中被改寫，見 `memory-fixture.md`）／**論證**（純函式論證或程式碼追蹤，無實機畫面）。三態不變，證據等級只是讓 ✅ 的強度看得見。

### 補充查核（description／規格／正確行為提及、但驗收條件未單獨列出的細節）

| 路徑或細節 | 結果 | 判定依據 |
|---|---|---|
| <例：欄位順序、移除舊欄位> | ✅ 通過 | <實機畫面或 diff 追蹤鏈> |

### 自動化測試（Step 3 跑的 PR 測試）
<指令與結果，例：`salon/xxx.test.tsx` 30/30 通過；stderr 雜訊的判讀>

### 環境副作用（對共用環境做過的動作，MUST 列出）
- 日結：關閉 <單號>（<筆數>、<金額>）、新開 <單號>（今日，仍開帳中）
- 誤觸／唯讀動作：<例：點到「立即同步」（唯讀同步）、開過「歷史消費」對話框>
- 建立的資料：<銷售單號；沒有就寫「未建立任何銷售單」>
- 模擬資料：<是否使用、是否已還原>

### 建議補手冊
- <手冊沒寫、這次摸索出的操作路徑：入口 → 步驟>

### 待使用者／PM 確認
- <規格沒寫清楚、判定時採用的假設>

### 建議留言草稿
<見下一節範本>
```

**MUST NOT 呼叫任何 Jira 寫入工具**（`addCommentToJiraIssue`、`addOrEditJiraIssueComment`、`editJiraIssue`、`createJiraIssue`、`transitionJiraIssue`、`addWorklogToJiraIssue`、附件上傳）。把上表與草稿回報給使用者，**等使用者明確要求才進 Step 6b**。委派給 `ragdoll-acceptance-qa` subagent 時，這是 agent 工具集本身的限制；由 orchestrator（或沒有 subagent、本 session 直接執行 SOP）時，是上面這條規則。

## 二、留言草稿範本（寫給 PM／QA／客服等非工程師看）

不要出現程式碼、函式名、檔案路徑。用業務語言說「操作什麼 → 看到什麼」。

```text
實機驗收結果：<通過／有 N 條不通過>（驗收條件 N 條）

驗收環境：Ragdoll vX.Y.Z（開發環境，連 dev 中台），門市「<名稱>」（<代號>）、機台 <代號>，畫面 1024×768；驗收版本為 PR #NNNN（<狀態>，commit <前 10 碼>）。

驗收條件逐條結果
- ✅ <條件白話描述>（圖 1）。
- ❌ <條件>：<看到的現象>。

規格欄位的補充確認
- ✅ <…>

說明
- <哪些情況是以模擬資料驗證，以及原因：dev 沒有對應資料。沒有改動任何中台或本機資料。>
- <自動化測試結果，一句話>
- <圖中與本功能無關的雜訊（如殘留的提示 toast）>
- <是否建立銷售單>

待確認：<規格沒寫清楚、判定時採用的假設，請 PM 確認>

附圖（依序）：圖 1 <…>；圖 2 <…>；圖 3 <…>
```

## 三、Step 6b：留言與截圖流程

**前提**：使用者明確要求留言，且說明哪張票、附哪些圖（含「附上關鍵截圖」這類交辦）。留言與上傳是對外發布，不是驗收的一部分。

### 1. 選圖與個資檢查

- 選 **2–3 張**，各對應一條或一組驗收條件；邊界／模擬類的補充圖寫進文字即可。
- **每張都先 `Read` 看過**：不可含完整手機、地址、會員全名（dev 測試會員也一樣）。有的話先遮蔽**副本**：用 PIL（`python3 -I` 執行放在暫存目錄的小 `.py`，`Image.crop`／畫色塊），不要用 `sips -c`（會靜默「成功」但輸出尺寸不變，仍是含個資的原圖，RD-8363 差點外洩）。遮完先檢查輸出尺寸有變，再 `Read` 副本確認個資不在畫面內。
- 另存成描述性檔名（上傳後就是票上的附件名），如 `RD-8427-fig1-paid-cross-store.png`。圖中若有與本功能無關的雜訊（殘留的 toast），在留言的「說明」中註明。

### 2. 上傳（兩階段，內嵌留言只做階段一）

附件工具不在 Atlassian MCP 的 primary tools，要用 `discover` 找：

1. `discover("upload an attachment file to a jira issue")` → 會得到 `uploadAttachmentToJiraIssue`（`executeWrite`）。
2. 對**每張圖**各呼叫一次，只給 `issueIdOrKey` 與 `filePath`，取回 `uploadCommand`（一條帶短效 Bearer token 的 `curl`）與 `collection`。
3. 在本機 shell **原樣執行** `uploadCommand`（位元組直接送到 Atlassian Media，不經過模型；多張圖可平行各跑一次），從回傳 JSON 取 `data.id`。token 約 20 分鐘過期，取得後盡快執行。
4. **不要**再跑階段二（帶 `fileId` 的呼叫）：內嵌進留言會自動掛成票附件，再跑會重複。

### 3. 發留言

`addOrEditJiraIssueComment`：`contentFormat: "html"`、`inlineFileId: [<data.id>…]`、`inlineFileCollection: [<collection>…]`、`inlineFileName: [<檔名>…]`（三個陣列依序對應）。

- 圖會依陣列順序附在留言**文末**，內文用「圖 1／圖 2／圖 3」對照，並在結尾列出各圖說明。
- 內文只用 `<p>`、`<strong>`、`<ul>`／`<ol>`／`<li>` 最穩；要用表格等，先查 `getContentFormatGuide`。
- 不寫手機、地址；只寫會員編號與單號。

### 4. 讀回驗證

- `listJiraIssueComments`（`executeRead`，`orderBy: "-created"`、`maxResults: 1`、`responseContentFormat: "html"`）：內文完整、`data-media` 數量等於圖數。
- `getJiraIssue` 取 `fields: ["attachment"]`：附件數與檔名對、**`size` 與本機檔案一致**。
- 回報 `commentId`。

### 不要做

- 不要為了附圖去找帳號憑證改打 Jira REST API。
- 沒被要求就不要留言、不要上傳、不要改票的狀態或欄位。
