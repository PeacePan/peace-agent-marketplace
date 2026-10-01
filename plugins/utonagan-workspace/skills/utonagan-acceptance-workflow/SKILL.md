---
name: utonagan-acceptance-workflow
description: Utonagan（店系統）實機驗收的標準作業流程：依賴檢查、登入與員編閘門等前置狀態、驗收範圍界定（父系 Epic 必須是 RD-7599）、驗收條件擷取（customfield_10030，以 markdown 清單為主、ADF 為備用）、diff-first 理解修復內容、用瀏覽器實際操作 dev server（4100 埠）驗證、三態判定與報告格式、驗收後清理，以及「agent 不可留言 Jira，只能回報草稿」的規則。使用者要求對某張 Utonagan 的 Jira 卡做實機驗收、或要確認店系統功能是否符合驗收條件時使用。
---

# Utonagan 實機驗收 SOP

## 適用範圍

- 只適用於父系 Epic 是 **RD-7599（SC）** 的 Jira ticket。驗收的是「使用者明確指定的單一 ticket」，不是「給一個 Epic、自動列出所有子卡逐一驗收」。
- 這是「像 QA 人員一樣操作一次正在跑的 app」，不是撰寫自動化測試（Utonagan 沒有 E2E）。
- 發現程式碼缺陷時只回報，不修正原始碼。

## 執行順序

Step 1 的範圍判斷只需要 Jira 的唯讀查詢，不依賴瀏覽器與 dev server，所以**先做 Step 1 的範圍判斷**：卡號本身是 `RD-7599`、查詢後父系明確不是 `RD-7599`（拒絕），或沒有父系（回報無法確認範圍）時，直接依 Step 1 回報並停止，**不必先做 Step 0a、0b**，沒有理由為了一張會被拒絕的卡去啟動瀏覽器與 dev server。確定屬於範圍之後，才依 0a、0b、2、3、4、5、6 的順序進行。

---

## Step 0a：工具依賴檢查（MUST，任何一項缺失就停止）

| 檢查項 | 方法 | 缺失時的訊息 |
|---|---|---|
| `wonderpet-general:jira-overview` skill | 用 `Skill` 工具載入 | 「缺少 wonderpet-general plugin（找不到 jira-overview skill），請先安裝該 plugin」 |
| Playwright MCP | 呼叫 `browser_navigate` 到 `http://localhost:4100/login` | 工具不存在：「請確認 utonagan-workspace plugin 已啟用，並用 `/mcp` 檢查 utonagan-playwright 的狀態」；工具存在但瀏覽器無法啟動：「Playwright 需要 Google Chrome，請安裝，或在 plugin 的 `.mcp.json` 以 `--browser` 指定其他瀏覽器」；工具存在但頁面連不上：「Utonagan 尚未啟動，請先在 Utonagan 目錄執行 `npm run dev`」 |
| Node 版本 | `node --version` | 必須落在 `>=22 <=24` |

Playwright 工具的完整名稱形如 `mcp__plugin_utonagan-workspace_utonagan-playwright__browser_navigate`，本文以短名 `browser_*` 稱呼。這些工具在工具清單中可能是 **deferred** 狀態：只有名稱、沒有參數定義，第一次呼叫前要先用 `ToolSearch` 以 `select:<完整名稱>` 載入，否則呼叫會失敗。**在判斷「沒有拿到 Playwright 工具」之前，一定要先用 `ToolSearch`（關鍵字 `playwright`）查過。**Jira MCP 的可用性由 Step 1 實際查卡一併驗證。

**沒有 SQLite 與本機資料庫**：Utonagan 是純 web 前端，所有資料都來自中台；資料層的確認改用 `browser_network_requests` 與 `browser_console_messages`。

**委派給 subagent 時的工具授權落差**：若在 `utonagan-acceptance-qa` 內用 `ToolSearch` 查過仍找不到 `browser_*` 工具，不要重試同一次委派、不要嘗試替代做法，改由 orchestrator 自己的 session 直接執行整套 SOP（前提是 orchestrator 的工具清單確實有這些工具，用 `ToolSearch` 確認）。

**選用依賴**：`mcp-wonderpet-table-local`（javacat）MCP，只在需要準備或核對中台資料時使用。使用前**先**呼叫 `javacat_switch_environment(env: "dev")`（對應本機 `local` build 所連的 dev 中台）；查詢大表一律給日期範圍。

### 要驗收哪個分支

Utonagan 尚未啟動時，執行 `npm run dev` 之前 **MUST** 先確認要跑的是哪個分支，不是隨便啟動目前 checkout 到的任何分支：

1. 查 Jira `customfield_10033`（分支名稱）取得這次修復的分支。
2. 查該分支 PR 的狀態與 base：

   ```bash
   gh pr view <分支名稱> --json state,baseRefName
   ```

   - 已 merge 進 `master`：可以直接在 `master` 上驗收。
   - **PR 仍是 `OPEN`**：修復只存在這個 PR 分支，**MUST** checkout 該分支才驗收得到；驗收 `master` 目前狀態驗不到任何修復。
3. checkout 既有遠端分支時 **MUST NOT** 用 `EnterWorktree({name})`，那只會從目前的 HEAD 新建分支。改為：

   ```bash
   git fetch origin <分支名稱>
   git worktree add .claude/worktrees/<自訂名稱> <分支名稱>
   ```

   建好後用 `EnterWorktree({path: ".claude/worktrees/<自訂名稱>"})` 讓 session 切進去隔離。
4. worktree 需要**實體** `npm ci`（於 `Utonagan/`；`file:` 依賴搭配 `install-links`，symlink 的 `node_modules` 會被 Turbopack 拒絕）。用 `run_in_background` 執行並以 log 輪詢確認完成，不要用 `sleep` 卡住整個 turn。
5. 啟動 dev server：於 `Utonagan/` 以 `npm run dev` 背景執行，固定 **4100 埠**。**不要直接執行 `bash bin/dev.sh`**：`npm run dev` 就是執行那支腳本，但只有透過 `npm run` 才會把 `node_modules/.bin` 放進 PATH，直接執行會找不到 `next`。
   - 埠被佔用時，先 `lsof -ti:4100` 查出佔用的程序，再用 `ps -p <pid> -o command=` 與 `lsof -p <pid>` 的 cwd 欄位確認它屬於哪個 worktree。若屬於別的 session：**停止並回報**，不自行 kill、不自行換埠。佔用者無法對應到本次要驗收的 worktree（包含根本不是 Utonagan 的程序），**一律視為別人的**，同樣停止並回報：附上 pid、command、cwd 與已執行時間（`ps -p <pid> -o etime=`），等使用者指示；不要因為它「不是 Utonagan」就當成殘留而結束它。
   - 不換埠的原因：RD-7573 是為 4100 這個來源開立中台 CORS 白名單的需求，換埠後查詢可能被 CORS 擋下。症狀是 `browser_console_messages` 出現 CORS 錯誤、畫面一直停在 loading。出現這個症狀時回報環境問題，不要歸為程式缺陷。

### 瀏覽器的行為

- 瀏覽器以 headless 與 isolated 模式執行，登入狀態只存在記憶體。**閒置超過 1 小時瀏覽器會自動關閉，下次工具呼叫重啟後登入狀態消失，必須重新登入。**
- **不使用 `browser_run_code_unsafe`**：官方標註它在 Playwright 伺服器行程內執行任意程式碼，等同遠端程式碼執行。

---

## Step 0b：業務前置狀態確認（MUST，用來正確分類結果）

**先讀懂每一條驗收條件本身描述的情境**，再決定要不要建立前提：

1. **條件本身就在描述「未登入」「員編閘門未解鎖」等邊界狀態下的行為** → **不要**先登入或解鎖，直接在該真實狀態下操作、觀察、判定。若一律先建立前提，這類條件永遠無法被驗證。
2. **條件描述的是正常流程** → 前提必須就緒，依序確認：
   - **登入**：登入頁需要員編（8 碼）、門市編號（3 碼）、OTP（6 碼）。使用者已在本次對話提供就使用，否則**向使用者索取**；不寫進任何檔案、不猜、不從其他檔案或記憶推測。取得前，這類條件標「⚠️ 無法驗證（尚未登入）」。
   - **送出員編與門市編號（登入第一步）就會讓中台寄出驗證碼**：登入頁自己寫著「驗證碼已寄至門市管理員信箱」，這是會通知到真人的操作。使用者尚未準備好收碼、或沒有說可以送出之前，**不要送出第一步**。
   - OTP 是中台發出的裝置驗證碼，**不要假設 dev 環境有固定碼**（實測以其他系統慣用的 dev 固定碼登入，被中台以「裝置驗證碼驗證失敗」拒絕）。
   - OTP 錯誤或過期、使用者又沒有提供新碼時，整張卡的條件都標「⚠️ 無法驗證（登入失敗：OTP 無效）」並停止，**不要點「重新發送驗證碼」**，那會再寄一封信。
   - **續跑規則（OTP 要分次取得時）**：驗收 agent 在背景執行，無法中途向使用者要 OTP，而 OTP 又只有在送出第一步之後才會寄出，所以流程通常分成三次委派：第一次在使用者同意前停止；第二次送出第一步後，因為沒有 OTP 而停止並回報「等待 OTP」；第三次帶著 OTP 續跑。拿到 OTP 的續跑，**先用 `browser_snapshot` 確認瀏覽器是否仍停在 OTP 輸入步驟**（同一個 session 內，Playwright MCP 的瀏覽器通常仍在），在就直接輸入 OTP；**不得重新導向 `/login` 或重送第一步**，那會再寄一封信，新的請求還可能讓手上的 OTP 失效。瀏覽器已經關閉時，回報「需要重新請求驗證碼」並停止，由使用者決定。需要 OTP 的驗收，建議由 orchestrator 在自己的 session 直接執行，避免瀏覽器狀態跨委派遺失。
   - **員編閘門（EmpGate）**：首頁速報、日業績、日結帳報表須先以員編驗證才顯示。解鎖態只存在記憶體，且綁定當時的路徑，**切頁即上鎖**。要驗證這些畫面時，在同一個路徑內完成驗證與檢查，中途不要導航離開。
   - **今日開帳機台**：支出申請依帳務日查今日的開帳機台；沒有開帳機台時該流程無法進行，標「⚠️ 無法驗證」並說明原因。
3. **環境一致性**（不論條件屬於哪一類都要確認一次）：`bin/dev.sh` 以 `UTONAGAN_TARGET_ENV=local` 啟動，連的是 dev 中台。用 `browser_network_requests` 確認請求打向 dev 端點；若看到 production 端點，**立即停止並回報**。

判定規則見 Step 6：只有「條件本身不是在測邊界狀態，卻因前提不足導致操作失敗」才歸「⚠️ 無法驗證」；條件本身在測邊界狀態時，一律依實際觀察判定 ✅ 或 ❌。

---

## Step 1：驗收範圍界定（RD-7599 校驗）

1. 使用者給一張 ticket 卡號（例：`RD-7862`）。
2. 若卡號本身就是 `RD-7599`：停止並回報「RD-7599（SC）本身是 Epic，請指定其底下的具體 ticket 卡號」。
3. 呼叫：

   ```
   mcp__claude_ai_Atlassian__getJiraIssue(
     cloudId: "f338306a-4b54-421e-9209-2e9f451c67f7",
     issueIdOrKey: "<使用者指定的卡號>",
     fields: ["summary", "issuetype", "parent", "customfield_10030"]
   )
   ```

   呼叫失敗（查無此卡、無權限）：停止並回報「查無 `<卡號>` 或沒有讀取權限，請確認卡號是否正確」。
4. 回傳結果**沒有 `parent`**：停止並回報「⚠️ 無法確認範圍：此卡沒有父系 Epic，無法判斷是否屬於 SC（RD-7599），請確認後再指定」。**這與「明確不屬於」不同，不可當成拒絕**，避免對資料缺失的卡片產生使用者無法覆寫的誤判。
5. `parent.key === "RD-7599"`：屬於範圍，繼續 Step 2。
6. `parent.key !== "RD-7599"`：
   - `parent.fields.issuetype.name` **不是**「大型工作」（代表這張卡是 Subtask，`parent` 指向的是它的父 Task）：對 `parent.key` 再做一次相同的查詢，只遞迴這一次，用新查到的 `parent` 重複第 4 到 6 點。
   - 是「大型工作」但 key 不是 `RD-7599`：**明確拒絕**：「此卡（`<卡號>`）的父系 Epic 是 `<parent.key>`（`<parent.fields.summary>`），不是 SC（RD-7599），本 SOP 僅適用於 Utonagan 的 SC 範圍，無法驗收」，停止流程。後端或基礎建設卡（例如掛在 BE 的中台 CORS 白名單、掛在 TABLE 的資料表擴充）沒有 Utonagan 的畫面可驗收，拒絕訊息要提到這點。

**掛在 RD-7599 也不代表一定有畫面可驗收**（例如建置與部署卡）。驗收條件無法對應到畫面操作時，標「⚠️ 無法驗證」並說明。

**已實測**：RD-7539、RD-7905、RD-7862 的 `parent.key` 為 `RD-7599`，`parent.fields.summary` 為 `SC`，`parent.fields.issuetype.name` 為「大型工作」；RD-7573 的 `parent.key` 為 `RD-782`（BE）。

---

## Step 2：解析驗收條件（`customfield_10030`）

**實測：Jira MCP（claude.ai Atlassian connector）回傳的 `customfield_10030` 是 markdown 字串，不是 ADF**，即使呼叫時指定 `responseContentFormat: "adf"` 也一樣。典型內容：

```markdown
### 1. 確認商品（門市）側與門市報表一致

- [x] 確認同一門市同一工作日，四格的門市子數字與門市報表日業績的指標卡完全一致
- [x] 確認門市金額為當日銷售單明細中非店內專櫃商品的價值加總

### 2. 確認美容側（新增）

- [x] 確認美容金額為當日服務銷售單的服務項目價值加總
```

markdown 的抽取規則：

- **每個清單項目是一條獨立的驗收條件**：以 `- `、`* ` 或 `1. ` 開頭，含 `- [ ]` 與 `- [x]` 的勾選寫法。**忽略勾選狀態**，`[x]` 只代表 Jira 上被手動勾過，與驗收判定無關。
- **`#` 開頭的行是分組標題，不是條件**。報告中可以拿它當條件的分組名稱，條件編號仍依出現順序連續編號。
- 清單項目後縮排的延續行，屬於同一條條件。
- 完全沒有清單、只有純段落時，每個以空行分隔的段落視為一條條件。
- 一條條件內若用「；」串了多項檢查，仍算一條，但判定時逐項檢查，並在「判定依據」逐項寫出；只要有一項不符，整條就是 ❌。

### 備用：ADF

若工具改回傳 ADF `doc` JSON（`content` 陣列），可能包含以下任一種寫法，**三種都要能解析**：

1. **`taskList`**（checklist 寫法）：`content` 是多個 `taskItem`，每個 `taskItem` 的 `content` 是內文節點。**忽略 `attrs.state`**，那是 Jira 上是否被手動勾選過，與驗收判定無關。
2. **`bulletList` / `orderedList`**：`content` 是多個 `listItem`，每個 `listItem.content` 通常是一個 `paragraph`，`paragraph.content` 才是 `text` 節點（比 `taskList` 多一層）。
3. **頂層 `paragraph`**（純文字寫法）：`paragraph.content` 是 `text` 節點。

ADF 的抽取規則（一律適用）：

- 每個 `taskItem`、每個 `listItem`、每個 `doc.content` 頂層的 `paragraph`，都是一條獨立驗收條件的起點。
- 在邊界內遞迴收集所有 `text` 節點的內容，串接成該條件的文字。
- **`hardBreak` 節點也視為條件邊界**：作者常用 Shift+Enter 手動換行，在同一個 `paragraph` 或 `taskItem` 裡塞好幾條條件。遇到 `hardBreak` 就把目前收集到的文字結算成一條條件，重新開始收集下一條。
- 去除每條條件前後的空白。

### 通用規則（不論格式）

**解析出 0 條**：**MUST 停止並回報**「無法從 `customfield_10030` 解析出任何驗收條件，請確認該卡是否已填寫驗收條件」。**MUST NOT** 自行從規格、正確行為、使用者故事等欄位發明新的驗收條件編號，那些不是判定 ✅ 或 ❌ 的正式依據。

**但仍須完整讀 `description` 與 `customfield_10059`（正確行為，漏洞類卡片才有）**：這兩個欄位常以敘事描述根因，可能提到驗收條件清單沒有單獨列出的額外觸發路徑。這類路徑不佔用正式驗收條件的編號，在報告中以「補充查核」獨立列出，並同樣給出 ✅、❌、⚠️ 三態之一的結論，不能只提及不下判斷。

彙整成一份「待驗收清單」，供 Step 5 逐條驗證。

---

## Step 3：理解程式碼修復內容（diff-first）

在動手操作之前，先讀懂這次修復實際改了什麼；Step 6 的「純函式論證法」與「補充查核」都需要它，光靠 Jira 描述猜測運作方式，遇到不容易重現的邊界情境會判斷不出結果。

1. **依 PR 狀態選擇比較方式**（狀態在 Step 0a 已查過）：
   - **PR 仍是 `OPEN`**：先算出真正的分支點，再比較，不要直接對 base 分支目前的狀態跑 diff（`master` 會持續有別的 PR 合併進來，直接比較會混入大量無關檔案）：

     ```bash
     git merge-base origin/master HEAD
     git diff <merge-base 的輸出>..HEAD --stat
     ```

     base 為 `master`；hotfix 的 base 是 `release/utonagan`，把上面的 `origin/master` 換成 `origin/release/utonagan`。
   - **PR 已合併**：HEAD 已經在合併後的 base 分支上，`git merge-base` 會等於 HEAD，diff 是空的，不能用上面的做法。改取該 PR 的合併 commit，與它的第一個親代比較：

     ```bash
     gh pr view <分支名稱> --json number,mergeCommit
     git diff <合併 commit>^1..<合併 commit> --stat
     ```

     或直接用 `gh pr diff <PR 編號>`。

   變動檔案數應與 PR 描述的「調整內容」吻合，才是正確的比較基準。
2. 找出**核心函式**：Utonagan 的修復通常落在純邏輯函式或 Hook。理解它的輸入輸出契約，比分別讀每個呼叫端更快建立全局理解。
3. 對照 Step 2 讀到的 `description` 與正確行為敘述，逐條核對：每一條根因路徑，是否都能在 diff 裡找到對應的修正。找不到的路徑，代表可能沒有真的修好。
4. 讀同一批 commit 新增或修改的測試：`describe`、`it` 的標題往往就是最準確的行為說明。

---

## Step 4：找操作依據

Utonagan 目前沒有使用手冊。依序嘗試，找到能回答「怎麼操作這個功能」的來源就停：

1. `peace-wp-llm-wiki` 的 `utonagan/` 頁面：先讀 `wiki/index.md` 的 Utonagan 區塊；路由與功能清單見 `wiki/utonagan/overview.md`，本 SOP 不重複維護。
2. Claude Design 設計稿「門市作業統一入口」（連結在 `Utonagan/CLAUDE.md`）。
3. Step 3 讀到的程式碼註解與測試標題。

以上都查過仍找不到某條驗收條件的操作方式，才標「⚠️ 無法驗證（找不到對應操作方式的文件依據）」，**不憑空猜測**。

---

## Step 5：實機操作驗收

對每一條驗收條件：

1. 依 Step 4 的步驟，用 Playwright 工具實際操作。
2. 以 `browser_snapshot`（無障礙樹）為主要依據，`browser_take_screenshot` 存證。
3. 用 `browser_console_messages` 看錯誤與警告；用 `browser_network_requests` 確認中台請求與回應。
4. 每個關鍵操作後截圖存證。

| 需求 | 工具 | 要點 |
|---|---|---|
| 看畫面結構、取得元素參照 | `browser_snapshot` | 優先於截圖；`browser_find` 可在快照中搜尋文字，找元素比抓整份快照省 |
| 點擊、輸入 | `browser_click`、`browser_type`、`browser_fill_form`、`browser_press_key`、`browser_select_option` | 以 `target` 指定元素（快照中的參照，或唯一的選擇器）；`browser_type` 的 `submit` 可在輸入後按 Enter，`slowly` 逐字輸入以觸發按鍵處理 |
| 等待 | `browser_wait_for` | 等文字出現或消失，不用固定 sleep；`time` 上限 30 秒 |
| Excel 匯入 | `browser_file_upload` | 傳入檔案的絕對路徑 |
| 確認視窗 | `browser_handle_dialog` | `accept` 決定接受或取消 |
| 看中台請求 | `browser_network_requests` | 可用 `filter` 正規表示式；單筆細節用 `browser_network_request` |
| 讀頁面狀態 | `browser_evaluate` | 例如讀 `localStorage` 的 session |

**操作眉角**：Radix 與 shadcn 的 Select、Dropdown、疊層 Dialog，在 Playwright 下可能需要特別的點擊方式。遇到點了沒反應時，先用 `browser_snapshot` 確認實際焦點與結果，不要重複同一個動作；把有效的做法寫進報告。

**證據檔不要寫進 repo**：`browser_take_screenshot`、`browser_snapshot` 的 `filename` 若給相對路徑，會以工作目錄為基準，弄髒 git 工作區（乾跑實測踩到）。不指定 `filename` 時，MCP 會存進已被 `.gitignore` 忽略的 `.playwright-mcp/`；需要指定檔名時，用暫存目錄的絕對路徑。

### 寫入守則（共用 dev 中台）

資料源是**共用 dev 中台**，不是本機資料庫；你的操作會影響所有連到 dev 的人。

- **唯讀操作**（開頁面、搜尋、切分頁）可自由進行。
- **會寫入的操作**（例如送出支出申請，會同時觸發簽核與通知；任何新增或更新）：**MUST** 先取得使用者明確同意，並優先使用既有的測試資料。未取得同意時，該條標「⚠️ 無法驗證（需要寫入共用 dev 中台，尚未取得同意）」。
- **production 一律不碰**：平台的權限分類器會擋下對 production 的查詢與寫入，這是平台層級的安全政策，不是工具故障。不要嘗試繞過（換帳號、換工具、換環境憑證）。涉及 production 的條件標「⚠️ 無法驗證（平台權限限制擋下 production 操作，需使用者親自確認）」，並告知卡在哪一步。

### 列印

驗收條件不是明確要求確認紙本輸出時，**不要觸發實體列印流程**（貨價卡的列印確認、支出證明單列印）。優先以程式碼論證：讀版面組裝函式（`components/pricetag/print/`、`lib/pricetag/`），確認欄位值是否原樣輸出，並在報告如實標註是程式碼論證而非肉眼比對紙本。若確實需要觸發列印，先告知使用者，並在回報中註明觀察到的行為（對話框是否出現、頁面是否仍可操作）。

### 靜態匯出產物

預設在 dev server 驗收。只有當驗收條件涉及靜態匯出特有的行為（例如字型的長快取標頭）時，才用 `npm run build:local` 加 `npx serve out` 檢視產物。

---

## Step 6：判定與回報（agent 不可留言 Jira）

每條驗收條件**只能**標記以下三態之一，**MUST NOT** 發明「部分驗證」「大致通過」之類的模糊第四態：

- ✅ **通過**：實際操作結果與條件描述一致（含條件本身就在測未登入或未解鎖，且實際行為符合預期）。
- ❌ **不通過**：實際操作結果與條件描述不符（含條件本身在測邊界狀態、但行為不符預期；**不得因為環境「未登入」而改標「無法驗證」**，因為未登入正是條件要求的測試情境）。
- ⚠️ **無法驗證**：Step 4 查過仍找不到操作依據、環境一致性有疑慮、條件本身不是在測邊界狀態卻因前提不足導致操作失敗、需要寫入共用 dev 中台但尚未取得同意，或涉及被平台權限擋下的 production 操作。

**「純函式論證法」**：當某條件描述的邊界狀態，安全地重現需要對共用資料做有風險的異動時使用。不要為了硬湊實機重現而改動共用 dev 中台的資料，改用推論鏈得出可稽核的結論：

1. 用 Step 3 找到的核心函式，確認它是純函式：輸出只由某個輸入（例如 session 或 EmpGate 解鎖狀態）決定，沒有「成功走一條路、失敗走另一條路」的額外分支。
2. 分別驗證這個輸入在「有效」與「空」兩種真實情況下的實際輸出，即使透過不同的呼叫路徑各驗證一種也算數。
3. 兩種輸入都驗證過，且呼叫端在觸發「失敗」情境時同樣會把輸入設成同一個空值（於 Step 3 的 diff 閱讀中確認呼叫順序），即可合併推論。
4. **回報時把推論鏈寫出來**（哪個函式、驗證了哪兩種輸入、呼叫順序如何確認），不能只寫「邏輯上應該沒問題」。

報告格式：

```markdown
## RD-XXXX 驗收結果

| # | 驗收條件 | 結果 | 驗證方式 | 判定依據 |
|---|---|---|---|---|
| 1 | <條件文字> | ✅ 通過 | 畫面快照＋network | <快照摘錄、截圖路徑、請求回應，或純函式論證鏈> |
| 2 | <條件文字> | ❌ 不通過 | 畫面快照 | <具體不符現象> |

### 補充查核（description 或正確行為提及、但驗收條件清單未單獨列出的路徑）

| 路徑 | 結果 | 判定依據 |
|---|---|---|
| <從 description 讀到的額外根因路徑> | ✅ 通過 | <diff 追蹤鏈或實機驗證> |

### 建議留言草稿

<給 orchestrator 詢問使用者是否留言用的文字>
```

**MUST NOT 呼叫任何 Jira 寫入工具**（`addCommentToJiraIssue`、`editJiraIssue`、`createJiraIssue`、`transitionJiraIssue`、`addWorklogToJiraIssue`、`createIssueLink`）。agent 定義用 `disallowedTools` 移除了這些工具，但黑名單只認 claude.ai Atlassian connector 的工具名稱，所以這條文字禁令才是主要依據。把上表與「建議留言草稿」回報給 orchestrator，由它詢問使用者是否同意留言，同意後才由 orchestrator 自己呼叫留言工具。

---

## Step 7：驗收結束後清理環境

只在使用者明確表示「驗收完成」或要求清理時才執行，不要在 Step 6 回報完就自動清掉，使用者可能還要接著人工複查畫面。

1. 呼叫 `browser_close` 關閉瀏覽器。
2. 停止背景的 dev server（用 `TaskStop` 停掉對應的背景任務），並確認 4100 埠已釋放：

   ```bash
   lsof -ti:4100
   ```

   仍有輸出時，用 `ps -p <pid> -o command=` 確認它屬於本次的 worktree，才可結束；屬於別人的就不要動。
3. 先確認 worktree 裡沒有你自己產生的未推送內容：`git fetch` 後比對 worktree 的 `git rev-parse HEAD` 與 `git rev-parse origin/<分支名稱>`，**完全一致**才代表可以安全清除；不一致（有你自己的 commit 或未提交變更）就不要清除，明確告知使用者 worktree 路徑。
4. 手動建立的 worktree，`ExitWorktree(action: "remove")` 會被拒絕（錯誤訊息為「This session is not the owner of the worktree」，該工具只認自己用 `{name}` 建立的 worktree）。正確流程：先 `ExitWorktree(action: "keep")` 讓 session 退回原本的工作目錄，再手動執行：

   ```bash
   git worktree remove .claude/worktrees/<自訂名稱>
   git branch -d <分支名稱>
   ```
