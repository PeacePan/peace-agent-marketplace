# 驗證手法對照

## 目錄

1. 驗證類型與工具對照
2. 呼叫 function
3. 外部系統測試
4. 冪等性與重複呼叫
5. 失敗路徑
6. 本機單元測試基線
7. 常見陷阱

---

## 1. 驗證類型與工具對照

| 類型 | 典型條件 | 工具 | 證據 |
|---|---|---|---|
| 表格結構 | 新增欄位、列舉、參照表、可寫入性 | `javacat_get_table_schema` | 欄位清單中的 `readWrite`（INSERT／UPDATE／READ）、`allowNull`、`enumName`、`refTableName` |
| 資料讀取與落地 | 「查得到一筆狀態為 X 的紀錄」 | `javacat_find`／`javacat_count`／`javacat_summarize` | 紀錄編號、欄位值。查詢一律給日期範圍、預設只查未封存；用紀錄主鍵精確定位時可免日期 |
| policy／hook 拒絕與放行 | 「傳入不合法值時被拒絕」 | `javacat_insert`／`javacat_update` | 錯誤訊息全文，以及回查資料確認沒有被寫入。MCP 寫入會跳人工確認，先告訴使用者要寫什麼 |
| function | 「呼叫後回傳 X、紀錄變成 Y」 | `scripts/call-dev-function.cjs` | 回傳內容，加上 MCP 回查資料 |
| TodoJob／cron | 「排程會處理 X」 | 查 `__todojob__`、`__joblog__`、`__cronlog__`（唯讀） | 狀態（IDLE／WORKING／PENDING／ERROR／DONE／CANCELLED）與執行歷程；判讀規則見 `javacat-todojob-mechanism` skill，注意要等到排程週期才看得到結果 |
| 簽核 | 「送出後進入簽核」 | `__approval2__`，`javacat_find` 的 `approved` 參數 | 簽核單狀態 |
| 操作來源 | 「這筆是誰、什麼時候改的」 | `__log2__`（mutation 自動寫入） | 操作者與時間 |
| 外部串接 | Van、大哥付、NetSuite | 見第 3 節 | 外部回應碼與資料落地 |
| 失敗路徑 | 斷網、逾時 | 見第 5 節 | 單元測試佐證，通常判 ⚠️ |

MCP 的 filter 語法、日期範圍與封存預設以 `anthropic-skills:mcp-wonderpet-table-usage` 為準。

---

## 2. 呼叫 function

javacat MCP 沒有呼叫 function 的工具，用 `scripts/call-dev-function.cjs`：

```bash
# 先 dry run 看要呼叫什麼（不送請求）
node <skill 目錄>/scripts/call-dev-function.cjs --table <表名> --name '<函式名稱>' --arg '<JSON 物件>' --dry

# 確認後正式呼叫
node <skill 目錄>/scripts/call-dev-function.cjs --table <表名> --name '<函式名稱>' --arg '<JSON 物件>'
```

輸出最後一行是 `RESULT <json>` 或 `ERROR <訊息>`。失敗時 javacat-graphql-client 會先印一段堆疊，那是套件自己印的，以最後一行為準。

**四個坑（都是實際踩過的）：**

1. **函式名稱是表格定義註冊的名稱，不是腳本檔名。** 在 `NorwegianForest/tables/.../<表名>.ts` 的 `functions[].name` 查，多半是中文。用檔名呼叫會得到「找不到函數 functionName=… tableName=…」，這個錯誤同時也是「dev 還沒 patch 這支函式」的訊號，兩種原因要分清楚。
2. **`argument` 要傳物件。** javacat-graphql-client v1.3.1 的 `mutation.call` 會自己 `JSON.stringify`。先手動 stringify 會雙重序列化，函式收到的是字串，症狀是明明有傳參數卻回「缺少 XXX」。`javacat-graphql-client` skill 的 04-mutation 章節寫「必須 JSON.stringify」，與實作不一致，以實作為準；腳本已內建防呆。
3. **憑證只用 dev。** 腳本只複製 MCP 憑證檔中 dev 的那一筆到暫存目錄，結束自動刪除；MCP 尚未登入 dev 或憑證過期時會直接說明。第一次使用前告知使用者「會使用你已登入 dev 的 MCP 憑證」。
4. **有外部副作用的函式只呼叫一次。** 見第 3 節。

**與 MCP 的分工：** 呼叫 function 用腳本；寫入資料（insert／update）一律用 MCP，因為 MCP 會跳出人工確認。不要為了省一次確認而用腳本直接寫入，那是為人設計的關卡。

---

## 3. 外部系統測試

Van、大哥付、NetSuite 這類串接，測試會碰到真實的外部服務。

**動手前先問（一次問完）：**

- 這次呼叫會打到哪個環境（dev 的 Van 目前可能指向廠商的測試站，不是正式站）
- 會不會發簡訊、扣款、寫入 ERP；接收者是誰
- 廠商測試站是否只認特定的測試對象、是否需要事先通知對方

**判讀外部回應：**

- 廠商的通用錯誤碼（例如欄位缺漏、格式錯誤）通常發生在業務判定**之前**。因此「先前回欄位錯誤、現在回業務錯誤」可以推論請求已通過欄位檢查；這是不必真的成功也能證明修正有效的方法，前提是你有實際看過兩次的回應。
- 業務錯誤（例如「非該電信用戶」）代表請求本身是合格的，不是程式問題；先查測試環境的限制，再懷疑程式。
- 廠商通常要求訂單編號唯一，重打同一編號會被拒絕。這也是「只打一次」的原因：失敗的回應本身就是證據，不要用重試去試出成功。

**測試對象受限時：** 先查專案文件（例如 Drive 的廠商測試參數文件）確認廠商提供哪些測試對象，**只取需要的資訊，不要轉述文件中的憑證或密鑰**。若文件註明使用前需通知廠商，那一步由使用者處理，不要代為聯繫。

---

## 4. 冪等性與重複呼叫

驗證「重複呼叫不會重複通知外部」時：

1. 先讓紀錄完整成功一次（已有外部交易編號）。
2. 用同一組參數再呼叫一次。
3. 比對兩次回傳的交易編號與連結完全一致、沒有錯誤。若第二次真的又打了外部，會得到「重複」類錯誤，或拿到不同的編號。
4. 這個驗證本身不會再打外部，可以放心做。

驗證「同一個業務單號連建兩筆互不覆蓋」時，查同單號的紀錄應有兩筆、主鍵不同、彼此獨立。

---

## 5. 失敗路徑

斷網、逾時、外部回 5xx 這類情境，在 dev 難以安全重現，硬湊（例如中斷網路、改壞設定）會影響共用環境。處理方式：

- 業務層失敗（外部回錯誤碼）可以在 dev 實測，並回查紀錄是否如條件所述保留。
- 連線層失敗（逾時、連不上、非 2xx、回應不是合法 JSON）用單元測試佐證：確認測試存在、涵蓋該分支、且斷言了「不寫入、不刪除紀錄」。報告中判 ⚠️，說明「dev 未實際模擬，單元測試已涵蓋」。
- 需要嚴格重現時，請使用者決定是否能在隔離環境模擬，不要自行破壞共用環境。

---

## 6. 本機單元測試基線

在受影響的測試資料夾跑一次，確認異動本身沒有造成回歸。慣例指令：

```bash
cd <worktree>/NorwegianForest
bash bin/test.sh tests/<資料夾>      # 會依序建置 JavaCat worker、建置 NorwegianForest、再跑 mocha
```

**全新 worktree 的三個坑：**

1. **沒有 `node_modules`。** NorwegianForest 與 JavaCat 可以用符號連結借主 checkout 的（根目錄、`JavaCat/`、`NorwegianForest/` 各一個）；這點與 Ragdoll 不同，Ragdoll 的 Turbopack 會拒絕符號連結。清理 worktree 時記得先移除這些連結（見 SKILL.md Step 8）。
2. **缺 `JavaCat/worker.js`**：症狀是 `Cannot find module '.../JavaCat/worker.js'`。在 `JavaCat/` 跑 `npm run build:worker`。
3. **缺 NorwegianForest 的建置產物**：函式與 policy 測試讀的是預編譯的 bundle，沒建置時**全部測試都紅**，錯誤是「腳本應預設匯出函數」，這是假紅燈，不是程式碼有問題。在 `NorwegianForest/` 跑 `npm run build`。**之後每次改了 `tables/` 底下的原始碼都要重建**，否則測試跑的是舊碼，會得到假綠燈。

建置過一次後，單一測試檔可以跳過 `bin/test.sh` 的建置步驟直接跑：

```bash
export TZ=Greenwich SANDBOX_QUIET=1 \
  MOCHA_ENV_FILES="../JavaCat/sls.yml.d/env.testing.yml,../JavaCat/sls.yml.d/env.testing.codebuild.yml,tests/env.testing.norcat.yml"
npx mocha -r ts-node/register/transpile-only -r ../JavaCat/test/envYamlLoader.ts \
  -r ../JavaCat/test/mocha.fixture.ts -r tsconfig-paths/register -r tests/global-setup.ts \
  -s 5000 -t 30000 --exit "tests/<資料夾>/**/*.test.ts"
```

型別檢查（`npx tsc --noEmit --project tsconfig.json`）通常有既有錯誤，先在 base 分支取得錯誤數，再看 PR 分支有沒有**落在異動檔案內**的新錯誤。ESLint 對異動的腳本檔跑一次（`npx eslint --ext=ts <檔案>`）。

---

## 7. 常見陷阱

- **zsh 未加引號的 glob 會讓 `&&` 鏈靜默中斷**（`no matches found`）。路徑含 `*` 一律加引號。
- **macOS 沒有 `timeout` 指令。** 要限制時間用工具本身的 timeout 參數。
- **MCP 的 CUD 確認對話是給人用的。** 不要嘗試自答，也不要用腳本繞過。
- **`javacat_find` 忘了日期範圍**會掃全表而逾時；精確主鍵定位除外。
- **production 會被平台分類器擋下**，不是工具壞了，不要繞。
- **`EnterWorktree({name})` 從目前 HEAD 切出**，不是 origin；驗收 PR 分支要另外切過去並核對雜湊值。
- **同版號不代表 dev 已含最新內容**（dev 的 patch 不檢查版本）。
