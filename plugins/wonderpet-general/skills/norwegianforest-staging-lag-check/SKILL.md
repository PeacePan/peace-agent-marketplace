---
name: norwegianforest-staging-lag-check
description: 檢查萬達中台（JavaCat / NorwegianForest）正式環境（production）近期異動的表格，在 staging 環境的版號（body.version）有沒有落後、還沒同步。當使用者問「staging 落後 production 嗎」「表格版號有沒有同步到 staging」「正式環境改的東西 staging 追上了嗎」「patch 進度」「__table__ 版號比對」，或任何提到中台表格在兩個環境之間版號差異、同步狀態時，都應優先使用此 skill，不要臨時重新摸索 __table__ 的查詢方式。
---

# Production → Staging 表格版號落後檢查

比對萬達中台 `__table__` 系統表（JavaCat 存放所有表格定義的地方，`body.version` 是表格版本號）在 **production** 與 **staging** 兩個環境的版號差異，找出「production 已經改過、staging 卻還沒 patch 上去」的表格。

這張表就是 `javacat_list_tables` 內部查的那張表；每次表格定義透過 `npm run patch` 部署到某個環境，`body.version` 就會 +1。兩個環境版號不同代表其中一邊還沒跑 patch。

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
  selects: ['_id', 'body.name', 'body.displayName', 'body.version', '_updatedAt'],
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

---

## 常見陷阱

- `_updatedAt` 的 `gte` 條件記得帶時區（`+08:00`），避免抓到的區間跟使用者認知的日期差一天。
- `archived` 參數不用特別設定，`__table__` 一般不會有封存紀錄。
- 兩環境的 `__table__` 文件 `_id` 通常相同（同一張表在不同環境建立時共用同一個 ObjectId），可以拿來交叉核對「這真的是同一張表」，但不要拿 `_id` 是否存在來判斷表格是否同步——要看 `body.version`。
- 這個 skill 只做**讀取比對**，不會、也不應該主動去跑 patch 或改任何表格版號；發現落後清單後如何處理（要不要 patch、找誰處理）交給使用者判斷。
- 自動撈 OTP 信只在使用者的 JavaCat 帳號 email 是 `wonderpet.asia` 網域、且已連上該使用者本人 Gmail 的情況下才做；不是同一個人的信箱絕對不要去撈。
- 實測這類密碼信送達後很快就會被規則移到垃圾桶，`search_threads` 預設不含垃圾桶，**忘記加 `in:anywhere` 會直接搜不到任何結果**（連舊信都搜不到，不是只有新信搜不到）。
- 短時間內重複呼叫 `javacat_request_otp` 可能會因為節流而沒有新信寄達（實測已登入的環境重新要求 OTP，等了將近 2 分鐘仍未收到新信）；重試等待時間到了還是找不到「晚於 `requestedAt`」的信，就老實退回去問使用者，不要無限重試卡住。
