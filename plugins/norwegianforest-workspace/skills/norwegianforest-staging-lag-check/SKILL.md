---
name: norwegianforest-staging-lag-check
description: 檢查萬達中台（JavaCat / NorwegianForest）正式環境（production）近期異動的表格，在 staging 環境的版號（body.version）有沒有落後、還沒同步。當使用者問「staging 落後 production 嗎」「表格版號有沒有同步到 staging」「正式環境改的東西 staging 追上了嗎」「patch 進度」「__table__ 版號比對」，或任何提到中台表格在兩個環境之間版號差異、同步狀態時，都應優先使用此 skill，不要臨時重新摸索 __table__ 的查詢方式。發現落後後，也用於把這些表 patch 到 staging（使用者同意後才執行）：相依表同批 patch、依請求大小分批、OTP 登入、驗證與收尾；當使用者說「把落後的表 patch 上去」「patch:staging」「staging 補 patch」「同步 staging 的表格」時同樣使用此 skill。
---

# Production → Staging 表格版號落後檢查

比對萬達中台 `__table__` 系統表（JavaCat 存放所有表格定義的地方，`body.version` 是表格版本號）在 **production** 與 **staging** 兩個環境的版號差異，找出「production 已經改過、staging 卻還沒 patch 上去」的表格。

這張表就是 `javacat_list_tables` 內部查的那張表；每次表格定義透過 `npm run patch` 部署到某個環境，`body.version` 就會 +1。兩個環境版號不同代表其中一邊還沒跑 patch。

**本 skill 分兩段：Step 0~6 只讀取比對；Step 7 起是 patch 工作流程，會對 staging 寫入，必須經使用者在對話中明確同意才執行。** 腳本都在本 skill 的 `scripts/` 目錄（路徑以載入時顯示的 Base directory 為準）。

---

## Step 0：詢問查詢區間

開始查詢前，先問使用者要檢查「production 近多久內有異動」的表格。**沒有指定就預設抓近 30 天（約 1 個月）**，並在開始查詢前明講你用的區間，讓使用者有機會喊停或擴大範圍（比照 javacat 查詢效能守則）。

---

## 前置知識：`__table__` 這張表

| 欄位 | 說明 |
|---|---|
| `body.name` | 表格名稱（小寫英文/數字/底線） |
| `body.displayName` | 表格顯示名稱（中文） |
| `body.version` | 表格版本號，每次 patch 該表格就 +1。**舊表格可能從未寫過這個欄位（undefined），不是 0** |
| `_updatedAt` | 這筆 `__table__` 紀錄本身最後被改的時間，即表格定義最後一次異動的時間 |

`__table__` 是系統 metadata 表，全站表格數量大約 200~300 筆，資料量小，**staging 端查詢不需要加日期範圍**（不受「查詢一定要給日期」的效能守則限制，性質等同 `javacat_list_tables` 的查詢對象）。

---

## 登入共用流程（Step 1、Step 3 都照這個走）

`javacat_switch_environment({ env })` 回傳 `isSignedIn: false` 才需要登入。JavaCat 帳號名稱通常是**員工編號格式**，不是使用者的 OS 帳號、git 帳號或 email 前綴——不知道使用者的 JavaCat 帳號就直接問，不要用 OS/git/email 猜。

1. 記下呼叫 `javacat_request_otp` 前的時間，當作 `requestedAt`（等一下要用來判斷哪封信是這次寄的，不是舊信）。
2. `javacat_request_otp({ env, name: <JavaCat 帳號>, email: <使用者 email> })`
3. **若使用者的 email 是 `wonderpet.asia` 網域，且 Gmail MCP（`mcp__claude_ai_Gmail__*`）可用，優先自動去信箱撈這封 OTP 信，不用等使用者手動回報驗證碼**：
   - 主旨依環境不同，對照如下：

     | env | 信件主旨 |
     |---|---|
     | production | `資料中台密碼信` |
     | staging | `資料中台準備環境密碼信` |
     | dev | `資料中台研發環境密碼信` |

   - 搜尋：
     ```
     mcp__claude_ai_Gmail__search_threads({
       query: 'in:anywhere from:do-not-reply@wonderpet.asia subject:"<對應主旨>"',
       pageSize: 5
     })
     ```
     **一定要帶 `in:anywhere`**——這類信實測常在幾分鐘內就被規則丟進垃圾桶，預設搜尋範圍（不含 trash）會撈不到。
   - 回傳的多筆訊息裡，挑 `date`（或 `internalDate`）**晚於 `requestedAt`**（容忍 30 秒左右的時鐘誤差）且最新的那一筆。**不要**直接拿 API 回傳順序的第一筆當最新——Gmail 是用 relevance 排序，不保證新信在前面；也**絕對不要**沿用 `requestedAt` 之前就存在的舊信，那是先前某次登入留下、可能已過期或已用過的驗證碼。
   - 用 `mcp__claude_ai_Gmail__get_message({ messageId: <上一步選到的訊息 id>, messageFormat: 'PLAIN_TEXT' })` 取內容，`plaintextBody` 就是純 6 位數字（例如 `"360581"`），直接當驗證碼用，不用額外解析。
   - 信件實測大約 30 秒內到 2~3 分鐘內送達，**沒搜到就每隔 10~15 秒重查一次，最多重試 5~6 次（約 60~90 秒）**。
   - 只要出現以下任一情況，就別再自動撈信，退回原本做法——跟使用者說「OTP 已寄出，請提供收到的 6 位數驗證碼」等使用者回報：使用者 email 不是 `wonderpet.asia` 網域、Gmail MCP 沒連上或沒有存取權限、或重試次數用完還是沒找到符合的信。
4. `javacat_login({ env, method: 'otp', name: <JavaCat 帳號>, email: <email>, otp: <上一步取得的驗證碼> })`

---

## Step 1：登入並切換 production 環境

```
javacat_switch_environment({ env: 'production' })
```

`isSignedIn: false` 才需要走上面的「登入共用流程」（`env: 'production'`）。

---

## Step 2：查詢 production 近期異動的表格

```
javacat_find({
  table: '__table__',
  filters: [{ bodyConditions: [
    { fieldName: '_updatedAt', valueType: 'DATE', operator: 'gte', date: '<Step 0 決定的起始日期 ISO 字串，如 2026-08-10T00:00:00+08:00>' }
  ]}],
  selects: ['_id', 'body.name', 'body.displayName', 'body.version', 'body._updatedAt'],
  skipLines: true,
  limit: 1000,
  multiSort: [{ field: '_updatedAt', direction: -1 }]
})
```

若回傳 `hasMore: true`（超過 1000 筆，理論上不太可能），用 `offset` 分頁補齊。這批結果就是「production 近期有版號異動的表格清單」，記下每張表的 `name`、`displayName`、`version`。

---

## Step 3：登入並切換 staging 環境

**production 和 staging 是各自獨立的登入憑證，就算剛登入過 production，staging 仍要重新走一次「登入共用流程」**（`javacat_switch_environment({ env: 'staging' })` 若 `isSignedIn: false`，一樣走上面的共用流程，這次 `env: 'staging'`）。

---

## Step 4：查詢 staging 全部表格版號

**不要**試圖用 `filters` 把 Step 2 抓到的表格名稱組成一個 `IN` 條件一次查完——filter cheat sheet 裡 `operator: 'in'` 對應的 `string` 欄位只吃單一字串，不支援陣列。正確做法是直接撈 staging `__table__` 全表：

```
javacat_find({
  table: '__table__',
  selects: ['_id', 'body.name', 'body.version'],
  skipLines: true,
  limit: 1000
})
```

同樣留意 `hasMore`，需要就分頁。把結果整理成 `name → version` 的對照表。

---

## Step 5：比對

對 Step 2 抓到的每一張表，用 `name` 去 Step 4 的對照表找版號，分成四類：

1. **staging 版號 < production 版號** → 落後，這是本次要輸出的主體
2. **staging 版號 = production 版號** → 已同步，不列出
3. **staging 版號 > production 版號** → staging 反而領先（staging 先開發、還沒 patch 回 production，是正常情況），列為附註，不算落後
4. **staging 完全沒有這張表 / `body.version` 是 undefined** → 比單純落後更嚴重（staging 可能從未拿到這張表的定義或從未 patch 過版號），獨立標註出來，不要跟普通落後混在一起

---

## Step 6：輸出結果

**一律使用以下格式**：先講清楚查詢區間與統計，再列落後表格的 Markdown 表格，按落後版數（production 版號 − staging 版號）**由大到小**排序：

```markdown
## 調查方法
- 查詢範圍：正式環境 `__table__` 中 `_updatedAt >= <起始日期>`（近 <N> 天），共 **<M> 張**表格有版號異動
- 逐一比對這 <M> 張表在 staging 環境 `__table__` 的 `body.version`
- 分類結果：<X> 張版號一致、<Y> 張 staging 版號反而領先、**<K> 張 staging 版號落後正式環境**

## Staging 版號落後正式環境的表格（<K> 張）

| 表格名稱 | 顯示名稱 | Production 版號 | Staging 版號 | 落後 |
|---|---|---|---|---|
| <name> | <displayName> | <prodVersion> | <stagingVersion> | -<gap> |
...
```

若 `K = 0`，明確說「近 <N> 天內 production 有異動的 <M> 張表格，staging 版號全部同步，沒有落後」，不要硬造空表格。

若 Step 5 分類 4（staging 完全沒有該表 / 版號 undefined）有結果，另外用一段 `⚠️ Staging 完全未同步的表格` 列出，跟落後清單分開。

結尾補一句 staging 反而領先的表格數量與名稱（簡短列出即可），說明這通常是 staging 先行開發、尚未 patch 回 production 的正常情況，不是本次要處理的問題。

輸出報告後，若有落後（K > 0）或有 `⚠️ Staging 完全未同步` 的表，接著進入 Step 7；K = 0 就到此結束。

---

## Step 7：詢問是否執行 patch 工作流程

用 `AskUserQuestion` 問使用者：要不要把這些落後的表 patch 到 staging？選項：

1. **產生計畫並執行**：Step 8~12 全跑。
2. **只產生計畫、不執行**：跑到 Step 9 為止，把計畫給使用者看。
3. **不 patch**：到此結束。

- patch 是**對 staging 的寫入**，必須是使用者這次明確同意；問「檢查有沒有落後」不等於授權 patch。
- 沒辦法互動時（背景執行、使用者不在場）停在報告，用 `needs input:` 請使用者決定，不要自行 patch。

---

## Step 8：準備 lag.tsv 與隔離 worktree

1. 把 Step 5 的落後表（分類 1，以及分類 4 中有版號可比的）寫成 `lag.tsv`，放在 `$NF_PATCH_STATE`（預設 `${CLAUDE_JOB_DIR:-/tmp}/nf-staging-patch`）。每行：`表名<TAB>production 版號<TAB>staging 版號`（staging 沒有版號寫 `-`）。
2. `bash scripts/prepare-worktree.sh --user <JavaCat 員編> --email <email>`
   - fetch 遠端後建立 `<主 repo>/.claude/worktrees/nf-staging-patch`，停在 `staging/norwegianforest` 並 fast-forward 到遠端最新；`npm ci`（NorwegianForest 與 JavaCat）；build；建立只含員編與 email 的 `.table.patch.env`。冪等，首次約 1~2 分鐘。
   - **一定要用 worktree、以遠端最新為準**：不要切使用者主 checkout 的分支；本機 `staging/norwegianforest` 常落後遠端很多（2026-11-11 實測落後 88 個 commit）。
   - 只支援 macOS（`bin/table.sh` 用 pbcopy 並拒絕 Linux）。

---

## Step 9：產生 patch 計畫

```bash
node scripts/plan-patch.mjs --lag "$NF_PATCH_STATE/lag.tsv" --worktree "<NF_WORKTREE>"
```

它用 `bin/table.sh --staging print` 取得各表在分支上的實際版號、相依欄位與 patch 內容大小，輸出 `plan.json` 與 Markdown 摘要：

- **結束碼 2**：有表與落後清單內的表相依，需要它們在 staging 的現值。常見於「反向相依」，例如 `poscustomerorder` 依賴 `posofflinetransaction`，卻因為近 30 天沒被 production 異動而不在清單內。用 MCP 查那些表的 `body.version`，以 `表名<TAB>-<TAB>版號` 加進 `lag.tsv` 後重跑。
- **批次**：相依群組合計 ≤ 上限的（`G*`）各自一批，用 `run-patch.sh` 同批送；**相依群組合計超過上限的（`X*`）拆成多個請求**，用 `send-split.mjs` 送（計畫直接給 `--requests` 參數；可用 `--max-bytes 4000000` 讓它拆成較少個請求）；無相依的表（`S*`）依大小打包，每批 ≤ 3.5MB。
- **被擋下的表**（附原因）：分支版號 ≤ staging 現值（版本檢查必擋），或單表就超過請求大小上限。
- **版號與 production 不同的表**：patch 後不會剛好對齊（可能超前、也可能仍落後），回報時要講。

把計畫完整呈現給使用者。**被擋下的表不要硬 patch**：不要自行改版號、改 `bin/table.sh` 或關掉相依檢查（自行 +1 版號會與 release 並行撞號，見踩坑紀錄），交由使用者決定。

**有 `X*` 批次（相依群組要拆成多個請求）時，要再問使用者一次是否接受拆開送**：請求之間 staging 會有數秒到十幾秒的版本不一致（2026-11-11 實測兩個請求相隔約 7~12 秒）。沒有同意就不送那一批。

---

## Step 10：逐批執行

順序：相依群組（`G*`）先、無相依（`S*`）後。**同一個 worktree 一次只跑一批。**

```bash
bash scripts/run-patch.sh <批次標籤> "<逗號分隔表名>"   # 表名取自 plan.json 的 batches[].tables
```

- **結束碼**：0 = 寫入成功（回應是 `patchV2` id 清單，且筆數等於表數）；1 = 寫入失敗；2 = 中止（檢查未通過或逾時，沒有回答 y、沒有寫入）。**不要看程式自己印的「已成功更新表格」**，伺服器回 413 時它照樣印（見踩坑紀錄）。
- 腳本只在版本與相依檢查都通過（log 沒有 `❌`／`⚠️`）時才回答 `y`。
- **OTP**：patch 工具有自己的登入（憑證存在 worktree 的 `tables/.table.patch.env`），與 MCP 的 `javacat_login` 是兩套，各要一組 OTP。憑證過期時腳本會印 `WAITING_OTP`、建立 `$NF_PATCH_STATE/waiting-otp-<標籤>`，然後等待 `$NF_PATCH_STATE/otp.txt`。做法：
  1. 第一批用背景方式執行（`run_in_background`），另開一個背景迴圈等標記檔：`until [ -f "$NF_PATCH_STATE/waiting-otp-<標籤>" ]; do sleep 1; done`
  2. 標記檔出現代表 OTP 信已寄出（staging 主旨「資料中台準備環境密碼信」）；依「登入共用流程」自動撈信，或請使用者提供 6 位數驗證碼。
  3. 取得後寫入：`printf '%s' '<驗證碼>' > "$NF_PATCH_STATE/otp.txt"`，腳本會繼續。
  憑證有效期約 24 小時，之後的批次不需要 OTP，可前景執行（每批約 30~60 秒）。
- 某批失敗（結束碼 1）：先看回應原因再繼續。`Request Entity Too Large` 代表那批超過請求上限；無相依的批次互相獨立，其餘批次可繼續。

**相依群組超過上限（`X*` 批次）**：「相依表必須同批」只是 npm 指令在產生 body 之前做的檢查，產生出來的 `patchV2` body 是 `data` 陣列、伺服器逐筆處理，所以可以分次請求。做法是三步，順序不可顛倒：

```bash
# 1. 讓工具把「整個群組」檢查一遍（版本、相依、⚠️），通過時回答 n，不寫入
CHECK_ONLY=1 bash scripts/run-patch.sh <標籤> "<整個群組的表名>"
# 2. 探測：送一個無副作用、與最大請求同樣大小的查詢；413 就中止，不會寫入任何東西
node scripts/send-split.mjs --worktree "<NF_WORKTREE>" --dry --requests "<plan 給的 --requests>"
# 3. 依序送出；任何一個請求失敗立刻停止，並列出已寫入與未寫入的表
node scripts/send-split.mjs --worktree "<NF_WORKTREE>" --requests "<plan 給的 --requests>"
```

- `send-split.mjs` 送出的內容與工具完全相同（同一份 `print` 結果、同一個 mutation、同一份憑證），但**不做相依與 `⚠️` 檢查**，所以第 1 步不能省。
- 憑證過期時 `send-split.mjs` 會中止；先照上面的 OTP 做法讓 `run-patch.sh`（第 1 步本身就會登入）更新憑證。
- 若中途失敗，staging 會停在「部分寫入」的狀態：依它列出的「已寫入／未寫入」重送未寫入的那組即可（`--requests` 只放未寫入的表）。
- 成功與否仍以 Step 11 為準。

---

## Step 11：以 staging 實際版號驗證

用 MCP 查 staging（`javacat_switch_environment({ env: 'staging' })`）：

```
javacat_find({
  table: '__table__',
  filters: <plan.json 的 verifyFilters>,
  selects: ['body.name', 'body.version', 'body._updatedAt'],
  skipLines: true,
  limit: 200
})
```

逐張比對 `plan.json` 的 `expected`：已 patch 的表版號必須等於 expected、`_updatedAt` 是剛才；被擋下的表版號必須與 patch 前相同（確認沒有任何半套寫入）。**成功與否以這一步為準，不是腳本訊息。**

---

## Step 12：收尾與回報

1. `bash scripts/cleanup.sh`：移除 worktree 設定檔內的 staging 登入憑證、清掉殘留的 FIFO 與 OTP 檔。確定不會再補 patch 才加 `--remove-worktree`。
2. 不 commit、不 push：整個流程沒有修改任何被追蹤的檔案（`git -C <worktree> status` 應該是乾淨的）。
3. 回報：
   - 已 patch 幾張（附前後版號）、各批結果
   - 被擋下的表與原因、需要使用者決定的事（例如相依群組超過請求上限）
   - patch 後重新對照 production 的剩餘落後清單
   - 異常（413、分支版號超前或落後 production 等）；若有拆請求的相依群組，註明請求之間的時間差（staging 不一致了幾秒）

---

## 常見陷阱

- `_updatedAt` 的 `gte` 條件記得帶時區（`+08:00`），避免抓到的區間跟使用者認知的日期差一天。
- `archived` 參數不用特別設定，`__table__` 一般不會有封存紀錄。
- 兩環境的 `__table__` 文件 `_id` 通常相同（同一張表在不同環境建立時共用同一個 ObjectId），可以拿來交叉核對「這真的是同一張表」，但不要拿 `_id` 是否存在來判斷表格是否同步——要看 `body.version`。`_id` 也不保證相同：2026-11-11 實測 `feversocialeligibilitylist`、`feversocialgamesetting` 在兩個環境的 `_id` 就不同（版號相同，所以算已同步）。
- Step 0~6 只做**讀取比對**，不會主動 patch 或改任何表格版號；發現落後後走 Step 7 詢問使用者，**同意了才進入 patch 工作流程**。
- `javacat_find` 的 `selects` 要寫 `body._updatedAt` 才會回傳更新時間；只寫 `_updatedAt` 不會回傳（`_updatedAt` 只能用在 filters／排序）。
- 「近 N 天」是以 `_updatedAt` 切齊的：窗口前一天才被 production 異動、但 staging 沒跟上的表不會出現在清單（2026-11-11 的 `poscustomerorder` 就是，production 在 10/11 21:14 異動、窗口從 10/12 開始）。若它與清單內的表相依，Step 9 會要求補查；懷疑漏了就放寬區間重跑。
- 自動撈 OTP 信只在使用者的 JavaCat 帳號 email 是 `wonderpet.asia` 網域、且已連上該使用者本人 Gmail 的情況下才做；不是同一個人的信箱絕對不要去撈。
- 實測這類密碼信送達後很快就會被規則移到垃圾桶，`search_threads` 預設不含垃圾桶，**忘記加 `in:anywhere` 會直接搜不到任何結果**（連舊信都搜不到，不是只有新信搜不到）。
- 短時間內重複呼叫 `javacat_request_otp` 可能會因為節流而沒有新信寄達（實測已登入的環境重新要求 OTP，等了將近 2 分鐘仍未收到新信）；重試等待時間到了還是找不到「晚於 `requestedAt`」的信，就老實退回去問使用者，不要無限重試卡住。

---

## Patch 工作流程踩坑紀錄（2026-11-11 首次實跑：45 張落後表，39 張 patch 成功，其餘 6 張因分支版號 ≤ staging 現值而無法 patch）

大部分坑已經被 `scripts/` 處理掉；列在這裡是讓你知道腳本為什麼這樣寫，以及腳本擋不住的情況怎麼處理。

| 坑 | 症狀／後果 | 做法 |
|---|---|---|
| **請求太大回 413，工具卻印「已成功更新表格」** | 伺服器回 `{"message":"Request Entity Too Large"}`（沒有 `errors` 欄位），`tables/index.ts` 只檢查 `errors`，所以印成功、結束碼 0，**實際什麼都沒寫** | 只認回應裡的 `{"data":{"patchV2":[id…]}}` 且筆數等於表數（`run-patch.sh` 已做）；最終以 Step 11 的 staging 實際版號為準 |
| **單次請求大小上限** | staging 實測 3.54MB、3.95MB 可通過，7.88MB 回 413，上限介於 3.95MB 與 7.88MB 之間；production 的上限沒實測 | `plan-patch.mjs` 預設每批 ≤ 3.5MB（已證實）。**相依群組合計超過上限不是死路**：`posofflinetransaction` 家族 7 張（`posofflinetransaction`、`poscustomerorder`、`poscustomerorderwithdraw`、`posreturn`、`possale`、`posservicereturn`、`posservicesale`）合計 7.88MB，拆成 3.95MB＋3.93MB 兩個請求用 `send-split.mjs` 送，都成功。**這個做法來自使用者的提醒**：我原本誤以為「相依表必須同批」是伺服器端限制、拆不開，差點請維運調高上限；實際上它只是 npm 指令在產生 body 之前的檢查，見下一列 |
| **版本檢查：整批作廢** | 只要有一張表「分支版號 ≤ staging 現值」，整批印 `❌` 並中止（不會半套寫入） | `plan-patch.mjs` 先分類。這代表 staging 分支還沒收到那一版：常見是 production 的版號比 release 分支高（production 從尚未合併的分支 patch），或 release 還沒同步進 staging。**不要自行 +1 版號硬 patch**（會與 release 並行 +1 撞號，合併後 patch 被略過），等 release→staging 同步或走 hotfix-staging，交使用者決定 |
| **相依表必須同批** | `dependencyTables`／`source` 指到的表不在同一個指令 → 相依性檢查失敗中止 | `plan-patch.mjs` 用 `print` 出來的欄位算群組；**反向相依**（依賴同一張被 patch 表的其他表）也會被找出來，這類表可能因為近 30 天窗口沒被列入而需要補查 staging 版號。**這個檢查只存在於 npm 指令（產生 body 之前）**，body 本身是 `data` 陣列、可以分次送（見上一列）；代價是請求之間 staging 有秒級的版本不一致（實測相隔約 7~12 秒），拆之前要讓使用者知情 |
| **不帶表名會直接 TypeError** | `npm run patch:staging` 單獨跑 → `tableNames.split` 的 TypeError | 一律 `npm run patch:staging -- a,b,c`（逗號分隔的單一參數） |
| **readline 會丟掉事先塞好的輸入** | `printf 'y\n' \| npm run …` 靜默什麼都不做：提示出現前就到的行被丟掉，程式在 EOF 時直接結束，沒有任何錯誤 | 用 FIFO 當 stdin，等 log 出現「是否直接更新表格」才餵 `y`；OTP 也是出現提示後才餵（`run-patch.sh` 已做） |
| **工具會覆蓋使用者的剪貼簿** | `table.sh` 的 patch 會 `pbcopy` 整包內容（數 MB） | PATH 最前面放假的 `pbcopy`（`run-patch.sh` 已做） |
| **本機 `staging/norwegianforest` 嚴重落後** | 實測落後遠端 88 個 commit；用它 patch 會把舊版定義送上去 | 一律在 worktree 以 `origin/staging/norwegianforest` fast-forward 後的內容 patch（`prepare-worktree.sh` 已做），不要切使用者主 checkout 的分支 |
| **分支守衛** | `bin/table.sh` 只允許 `staging/*` 或 `*hotfix-staging/*` 分支 patch staging，其他分支會被擋 | worktree 必須停在 `staging/norwegianforest` |
| **有兩套登入** | MCP 的 `javacat_login` 與 patch 工具的登入是兩個 session，MCP 登入過 staging 也不能讓 patch 工具免 OTP | patch 工具的憑證存在 `tables/.table.patch.env`（已被 `.gitignore` 排除），有效約 24 小時；Gmail MCP 授權可能過期，撈不到信就請使用者貼驗證碼 |
| **`⚠️ 表格已於…被…更新，請先 pull` 警告** | 有人在最近一次 merge 之後更新過 staging 這張表；盲目覆蓋可能蓋掉別人的改動 | `run-patch.sh` 遇到 `⚠️` 會中止；先確認那次更新是誰、做了什麼，再決定 |
| **分支版號與 production 不一致** | production > 分支：production 是從未合併的分支 patch 的（2026-11-11 的 `mashoporder` production 85、分支 84）。分支 > production：release 已合併但 production 還沒 patch（`possale` 227 對 226、`posservicesale` 112 對 111） | patch 後 staging 不會剛好等於 production，回報時要講清楚（`plan-patch.mjs` 會列出） |
| **zsh 陣列從 1 開始** | 在 zsh 手寫 bash 陣列索引會讓名稱整個錯位一格（這次量檔案大小就錯過一次，數字沒錯、標籤錯） | 腳本一律用 bash 或 node，名稱取自資料本身（`plan-patch.mjs` 用表格自己的 `name` 欄位），不靠順序對應 |
| **本機 grep 是 ugrep** | `git grep -E '\s'` 這類寫法回傳假的 0 命中，連「確實存在」的字串都找不到 | 用 `[[:space:]]`；只要結果是 0 筆，先拿一個確定存在的字串驗證指令本身（`plan-patch.mjs` 已用 `[ \t]`） |
| **bash 變數後面緊接全形字元會當掉** | macOS 的 bash 把全形字元的第一個位元組當成變數名稱的一部分：`echo "…$IDS）"` 在 `set -u` 下報 `IDS）: unbound variable`。靜態語法檢查（`bash -n`）看不出來，**只有走到那一行才炸**；這次它藏在「成功路徑」與「清理」，是用假 `npm` 端對端跑過才抓到 | 腳本裡變數後面接中文標點一律寫 `${VAR}`；改腳本後，每條路徑都要真的走過（成功、失敗、中止、OTP），不要只跑 `bash -n`。可用 `LC_ALL=C grep -nE '\$\{?[A-Za-z_][A-Za-z0-9_]*[^ -~]' scripts/*.sh` 掃描 |
| **每批都要 build** | `npm run patch:staging` 內含 `npm run build`（webpack 約 12~20 秒）加 ts-node 初始化，所以提示出現前約 25 秒 | 不要判斷為卡死；也不要為了省時間同時開兩批（共用 `dist` 與設定檔，會互相覆蓋） |
