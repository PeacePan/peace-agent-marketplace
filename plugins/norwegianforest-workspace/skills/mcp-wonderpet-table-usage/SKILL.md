---
name: mcp-wonderpet-table-usage
description: >
  萬達寵物中台（JavaCat / NorwegianForest）資料查詢與操作的入口 skill。
  使用者訊息出現以下任一關鍵字 → 必載入並優先以本 MCP 處理：
  萬達中台、中台、萬達資料庫、JavaCat、NorwegianForest、Norcat、查中台、查表、查資料、
  查 possale / posmember / member / item 等業務表、要看某張表、新增中台、更新中台、
  以及任何提到 javacat_find / javacat_count / javacat_insert / javacat_update /
  javacat_list_tables / javacat_login / javacat_request_otp /
  javacat_switch_environment 的場合。涵蓋使用前置流程、查詢效能守則
  （查紀錄必給日期範圍）、filter cheat sheet（含完整 operator 表）、
  常用 table 速查（依 TABLE_GROUP 分領域 + 31 張系統表，cross-link 業務 skill）、
  典型查詢/插入/更新範例與錯誤對照。專為「透過 MCP 工具」操作的 agent 設計，
  不重複 javacat-graphql-client（lib API）與 javacat-table-architecture（schema 定義）內容。
---

# mcp-wonderpet-table 使用指南

8 個 MCP tool 的 input schema 在工具列表已說明，本指南聚焦於：**先做什麼、查哪張表、filter 怎麼寫、怎麼避開常見錯誤**。

---

## 適用情境（看到這些字眼優先用本 MCP）

當使用者訊息提到下列任一關鍵字，**第一順位**改用 `javacat_*` MCP tool 處理，不要 grep 程式碼、不要 WebFetch、也不要先去翻業務 skill 找答案——資料就在中台，直接查。

- **平台名稱**：萬達中台 / 中台 / 萬達資料庫 / JavaCat / NorwegianForest
- **動作意圖**：查中台、查表、查資料、看某張表、列出 / 統計 / 插入 / 更新 中台資料
- **業務表名稱**：possale、posreturn、posmember、pospromotion、poscoupon、member、item、purchaseorder、transferorder、dsvorder、saleorder、customer ... 等任一 `TABLE_NAME`（完整清單見第 4 章）
- **系統表名稱**：`__user__` / `__log2__` / `__todojob__` / `__approval2__` 等任一 `SYSTEM_TABLE_NAME`

業務深度問題（例如「possale 的折扣是怎麼算的」「會員等級升降規則」）仍要載入對應業務 skill（`pos-knowledge-base` / `member-system-knowledge` 等），但**取資料本身永遠走本 MCP**。

---

## 1. 使用前置流程

任一資料工具（list_tables / find / count / insert / update）執行前必經兩個 gate：

```
javacat_switch_environment(env)        ← 必經，否則 checkEnv 失敗
        ↓
checkAuth (內部自動)
        ↓ 未登入
elicitation 兩段對話（自動跳出）
  Stage 1: 收集 name + email → 寄送 OTP
  Stage 2: 收集 6 位數 OTP   → 完成 signin（cert 自動寫入 ~/.local/share/mcp-wonderpet-table/）
        ↓ 已登入
原工具繼續執行
```

- **正常路徑**：直接呼叫 `javacat_find`，未登入時 server 主動跳對話、登入後自動續跑，**不必先呼叫 login**。
- **自動化路徑**：呼叫 `javacat_login` 帶 `method='access_key' + accessKeyId + secretAccessKey`，繞過 elicitation（適合無人值守場景）。
- **對話被 cancel/decline**：回應「已取消登入，未執行原工具」，**不會自動 retry**。要重試請再次呼叫工具並完整填完表單。

---

## 2. 通用欄位慣例

### 表頭基礎欄位（所有業務表都有）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `_id` | string (ObjectId) | 系統主鍵 |
| `_gId` | string (UUID v4) | 全域識別碼，**不會因紀錄更新而變動** |
| `_createdAt` / `_updatedAt` / `_archivedAt` | Date \| null | 建立 / 更新 / 封存時間（`_archivedAt = null` 代表未封存） |
| `_updateId` | ObjectId | 更新識別碼，每次紀錄更新都會變動 |
| `_createdBy` / `_updatedBy` / `_archivedBy` | string | 操作者帳號名（參考 `__user__.name`） |
| `_createdBy_displayName` / `_updatedBy_displayName` / `_archivedBy_displayName` | string | 操作者顯示名稱（refData，自動帶出） |
| `_approvalStatus` | enum | `APPROVED` / `DENIED` / `PENDING` / `ERROR`（**注意是 approval 不是 approve**） |
| `_approvalName2` / `_approvalSequence2` | string | 簽核單編號 / 序數 |
| `_approvalApprovedBy2` / `_approvalApprovedAt2` | string / Date | 簽核同意者 / 時間 |
| `_approvalDeniedBy2` / `_approvalDeniedAt2` | string / Date | 簽核拒絕者 / 時間 |
| `body` | object | 表頭業務欄位 |
| `lines` | `{ [lineName]: Row[] }` | 表身（多列子資料） |

### 表身基礎欄位（每列都有）

`_id`（表身列編號）、`_createdAt`、`_updatedAt`、`_createdBy`、`_updatedBy`（不含 `_archivedAt`，表身列不獨立封存）。

### 取用慣例

- 系統欄位以 **底線開頭**（`_id`、`_createdAt`、`_archivedAt`...）。
- 業務欄位在 `body.xxx` 或 `lines.xxx[].yyy`。
- 用 `selects: ['_id', 'body.name']` 控制回傳欄位、避免回應截斷。
- `skipLines: true` 可大幅加快查詢（不需要表身時務必設定）。

---

## 3. Filter Cheat Sheet

### ⚠️ 查詢效能守則（必讀）

**所有 `javacat_find` / `javacat_count` 呼叫，filters 內務必包含日期範圍條件。** JavaCat 後端不會自動限制時間範圍——沒給日期就會掃整張表，業務表動輒百萬筆，會造成操作逾時、回應截斷、甚至拖累整個 GraphQL 服務。

最常用的日期欄位（依場景擇一）：

| 欄位 | 適用情境 |
|------|---------|
| `_createdAt` | 想查「何時建立」的紀錄（最通用） |
| `_updatedAt` | 想查「何時被改過」的紀錄（追資料變動） |
| `body.<業務日期欄位>` | 業務語意上的日期，如 `body.saleDate`、`body.dueDate`、`body.shippedAt` |

**最低標準**：給一個 `gte`（下界）。`30 天 / 7 天 / 今天` 視 task 而定。若使用者沒明說範圍，預設取最近 30 天並向使用者明示「查詢範圍 = 過去 30 天」，再讓他確認是否擴大。

```js
// 預設模板（請至少給 _createdAt gte）
javacat_find({
  table: 'possale',
  filters: [{ bodyConditions: [
    { fieldName: '_createdAt', valueType: 'DATE', operator: 'gte', date: '<30 天前 ISO 字串>' }
    // ... 其他業務條件 AND 在後面
  ]}],
  limit: 100,
  skipLines: true,
})
```

**例外（可不給日期）**：
- `javacat_list_tables` — 查 metadata，無 row 級資料
- 系統小表（`__user__`、`__role__`、`__sysvar__`、`__enum__`） — 列數有限
- 用 `_id` 等具唯一性鍵直接定位（操作 = `in`，等於精確查詢）的場合

### ⚠️ 封存預設守則（必讀）

**`archived` 參數預設一律使用 `'NORMAL'`，不要主動傳 `'ALL'` 或 `'ARCHIVED_ONLY'`。** 已封存（`_archivedAt != null`）的紀錄通常是業務上「已作廢/已退單/已取消」的資料，混進結果會讓統計與判斷失真。

| `archived` 值 | 含義 | 何時用 |
|---------------|------|--------|
| `'NORMAL'` | 只回傳未封存（`_archivedAt = null`） | **預設、99% 場合** |
| `'ARCHIVED_ONLY'` | 只回傳已封存 | 使用者明確要查「歷史已作廢的紀錄」時 |
| `'ALL'` | 全部回傳 | 使用者明確說「含已封存」「全部都要」「不論狀態」時 |

判斷流程：
- 使用者說「查 X」「列出 X」「統計 X」「看 X 有幾筆」 → **`NORMAL`**
- 使用者說「含封存的」「包括已作廢的」「歷史所有」「不論狀態」 → `ALL`
- 使用者說「已被作廢的 / 已封存的 X」 → `ARCHIVED_ONLY`

不確定時直接走 `NORMAL`；若使用者真的想看封存資料，他會在看到結果不齊時補充說明，那時再切 `ALL`。

### 結構（OR / AND）

```
filters: [                          ← 頂層陣列：OR 關係
  {                                 ← FilterGroup
    bodyConditions: [...],          ← 表頭條件（彼此 AND）
    lineFilters:    [...]           ← 表身條件（彼此 AND）
  },
  { ... }                           ← 另一個 FilterGroup（與上一組 OR）
]
```

兩個 FilterGroup 為 OR；同一 FilterGroup 內全部 condition 為 AND。

### Operators（**完整列表，無其他**）

| operator | 語意 | 適用 valueType | 範例 |
|----------|------|---------------|------|
| `in` | 等於 / 包含 | 全部 | `{ operator: 'in', valueType: 'STRING', string: 'active' }` |
| `nin` | 不等於 / 不包含 | 全部 | `{ operator: 'nin', valueType: 'BOOLEAN', boolean: true }` |
| `like` | 模糊比對 | **STRING 限定** | `{ operator: 'like', valueType: 'STRING', string: 'wonder' }` |
| `gte` | ≥ | NUMBER / DATE | `{ operator: 'gte', valueType: 'DATE', date: '2025-01-01T00:00:00.000Z' }` |
| `lte` | ≤ | NUMBER / DATE | 同 gte |
| `gt`  | > | NUMBER / DATE | 同 gte |
| `lt`  | < | NUMBER / DATE | 同 gte |

> ⚠️ **沒有 `eq` / `ne` / `regex` / `exists`**。「等於」一律用 `in`、「不等於」一律用 `nin`。

### valueType 必填欄位對照

| valueType | 必填欄位 | 範例 |
|-----------|---------|------|
| `STRING` | `string` | `'active'` |
| `NUMBER` | `number` | `100` |
| `DATE` | `date`（ISO 8601 字串） | `'2025-01-01T00:00:00.000Z'` |
| `BOOLEAN` | `boolean` | `true` |
| `ID` | `id`（ObjectId 字串） | `'65a1b2c3d4e5f6a7b8c9d0e1'` |

### 常用 Pattern

**「name 等於 john」**：
```json
{ "filters": [{ "bodyConditions": [
  { "fieldName": "name", "valueType": "STRING", "operator": "in", "string": "john" }
]}]}
```

**「最近 30 天建立 AND status='active'」**（單組 AND）：
```json
{ "filters": [{ "bodyConditions": [
  { "fieldName": "_createdAt", "valueType": "DATE", "operator": "gte", "date": "2025-04-01T00:00:00.000Z" },
  { "fieldName": "status",     "valueType": "STRING", "operator": "in",  "string": "active" }
]}]}
```

**「status='active' OR status='pending'」**（兩組 OR）：
```json
{ "filters": [
  { "bodyConditions": [{ "fieldName": "status", "valueType": "STRING", "operator": "in", "string": "active"  }] },
  { "bodyConditions": [{ "fieldName": "status", "valueType": "STRING", "operator": "in", "string": "pending" }] }
]}
```

**表身有特定 item**：
```json
{ "filters": [{ "lineFilters": [
  { "lineName": "items", "lineConditions": [
    { "fieldName": "sku", "valueType": "STRING", "operator": "in", "string": "ABC123" }
  ]}
]}]}
```

**只查未封存且已簽核**：透過 `archived` / `approved` 直接欄位（不需手寫 filter）：
```json
{ "table": "possale", "archived": "NORMAL", "approved": "APPROVED" }
```

---

## 4. 常用 Table 速查（依 TABLE_GROUP 分領域）

完整 table 名單在 `NorwegianForest/tables/const.ts` 的 `TABLE_NAME`。**深度業務知識請載入對應業務 skill**。

### POS 門市銷售 → `norwegianforest-workspace:pos-knowledge-base`
- `possale` — 銷售單
- `posreturn` — 銷退單
- `posmember` — 會員檔
- `pospromotion` — 商品促銷檔
- `poscoupon` — 折扣碼檔

### 美容 POS（SALON_POS） → `norwegianforest-workspace:pos-knowledge-base`
- `posservicesale` — 服務銷售單
- `posservicereturn` — 服務銷退單
- `serviceitem` — 服務料件檔
- `possalonpromotion` — 美容促銷檔
- `possaloncoupon` — 美容折扣碼檔

### 會員權益（MEMBER_RIGHTS） → `norwegianforest-workspace:member-system-knowledge`
- `memberclass` — 會員等級設定檔
- `pointaccount` — 點數帳本
- `petparkcoupon` — 會員優惠券檔
- `petparkcouponevent` — 優惠券活動設定檔
- `pointpromotion` — 點數消費活動設定
- `givepointsetting` — 贈點活動設定

### 採購循環（PROCUREMENT）
- `item` — 料件檔
- `vendor` — 廠商檔
- `purchaseorder` — 採購單
- `returnorder` — 退貨單
- `requisition` — 請購單

### 銷售循環（SALES）
- `customer` — 客戶檔
- `saleorder` — 銷貨單
- `salereturn` — 銷貨退回單
- `ecsale` — 毛孩銷售單
- `ecrefund` — 毛孩銷退單

### 庫存管理（INVENTORY） → 調撥相關請載入 `norwegianforest-workspace:transferorder-business-logic`
- `location` — 倉庫檔
- `balance` — 庫存檔
- `transferorder` — 調撥單
- `adjustment` — 庫調單
- `itemreceipt` — 驗收單

### DSV 出貨（DSV） → `norwegianforest-workspace:dsv-system-knowledge`
- `dsvorder` — DSV 出貨單
- `dsvorderdetail` — DSV 出貨明細
- `dsvshipment` — DSV 出貨貨況
- `dsvinventory` — DSV 配貨庫存
- `dsvdailytask` — DSV 每日配貨

### Magento 電商
- `mafastbuyorder` — 寵速配訂單
- `mashoporder` — 寵日配訂單
- `mafastbuyrefund` — 寵速配退款單
- `mashopreturn` — 寵日配退貨單

### Emarsys CRM 同步 → `norwegianforest-workspace:member-system-knowledge`
- `emcontacttask` — 會員任務
- `emsaletask` — 銷售任務
- `emproducttask` — 商品任務
- `emstoretask` — 門市任務

### 外送平台（UberEats / Foodomo / Foodpanda）
- `ubereatsstore`、`ubereatsmenu`、`ubereatsitem`
- `foodomostore`、`foodomomenu`、`foodomoitem`
- `foodpandastore`、`foodpandaitem`

### 供應鏈管理（SCM）
- `longtermrebatecontract` — 長期回饋金合約
- `sponsorshipcontract` — 贊助金合約
- `suppliersalesstatistics` — 供應商銷售統計
- `rebatetimerangeconfig` — 回饋區間設定

### 大智通（WDS）
- `wdsproductsync` — 商品主檔同步
- `wdsordersync` — 訂單同步
- `wdspurchaseordersync` — 採購單同步
- `wdsstoresync` — 門市主檔同步

### 費用管理（EXPENSE） / ONE 碼對帳（RECONCILIATION）
- `expense` — 請款單
- `expensecategory` — 費用分類
- `bankreconciliation` — 對帳銀行檔
- `reconciliationresult` — 對帳結果

### 系統表（System Tables，名稱前後加雙底線）

JavaCat 內建系統表，**完整清單**（取自 `JavaCat/src/lib2/@type/const.ts` 的 `SYSTEM_TABLE_NAME`）。`javacat_list_tables` 內部即是查 `__table__`。

#### 高頻使用（agent 經常會用到）
| Table | 用途 |
|-------|------|
| `__table__` | 表格定義檔。所有 table 的 schema、欄位、enum、policy/hook 都存在這。**`list_tables` 即查此表** |
| `__user__` | 使用者。`_createdBy / _updatedBy / _archivedBy` 都 ref 到這張的 `name` 欄位 |
| `__role__` | 角色（權限） |
| `__file2__` | 檔案。所有 file 欄位 ref 到這張的 `name` |
| `__filecategory__` | 檔案分類 |
| `__enum__` | 列舉總覽 |
| `__sysvar__` | 系統變數 |

#### 操作 / 簽核紀錄（read-only，多用於稽核）
| Table | 用途 |
|-------|------|
| `__log2__` | **目前使用中的操作紀錄表**（mutation 自動寫入此表） |
| `__approval2__` | 簽核單 |
| `__approvalchain__` | 簽核鏈設定 |
| `__log__` / `__log2021__` / `__log2022__` / `__log2023__` | 舊版/年度操作紀錄。**新查詢請用 `__log2__`** |

#### 待辦工作（TodoJob）相關
| Table | 用途 |
|-------|------|
| `__todojob__` | 待辦工作主檔（深入請載入 `norwegianforest-workspace:javacat-todojob-mechanism`） |
| `__joblog__` | 工作執行歷程 |
| `__cronview__` | 排程總覽 |
| `__cronlog__` | 排程歷程 |

#### 事件歷程（read-only，依服務分流）
| Table | 用途 |
|-------|------|
| `__eventlog__` | 通用事件歷程 |
| `__emaillog__` | 信件服務事件 |
| `__dlqlog__` | DLQ（死信佇列）事件 |
| `__approvallog__` | 簽核服務事件 |
| `__docdblog__` | 資料庫服務事件 |
| `__authlog__` | 登入事件 |

#### 其他系統表
| Table | 用途 |
|-------|------|
| `__token__` | 令牌 |
| `__email__` | 信件 |
| `__device__` / `__devicetoken__` | 裝置 / 裝置令牌 |
| `__script__` | 指令碼檔 |
| `__tablestats__` | 表格統計報告 |
| `__dropregister__` | 刪表註冊 |

#### Mutation 自動 log 行為（撰寫測試或解析資料時注意）

對任何業務表執行 `insert / update / archive` 等 mutation，JavaCat 會**自動寫入** `${tableName}.log`（或 `__log2__`）。但有兩個例外：
- 表名是系統保留 log 表（`__log__`、`__log2__`）→ 跳過（避免遞迴）
- 表名含 `.`（如 `foo.log`）→ 跳過（避免巢狀集合 `foo.log.log`）

這代表你查 `__log2__` 看到的紀錄量，會比業務操作 + 1（log 自己不寫 log）。

---

> 不確定 table 名稱時 → 直接呼叫 **`javacat_list_tables`** 取最新清單。

---

## 5. 高頻查詢範例

### 計算「最近 30 天的 possale 筆數」

```js
javacat_count({
  table: 'possale',
  filters: [{ bodyConditions: [
    { fieldName: '_createdAt', valueType: 'DATE', operator: 'gte', date: '2025-04-01T00:00:00.000Z' }
  ]}]
})
```

### 列出「今年 status='active' 的會員，只要 name 與 email」

```js
javacat_find({
  table: 'posmember',
  filters: [{ bodyConditions: [
    { fieldName: 'status',     valueType: 'STRING', operator: 'in',  string: 'active' },
    { fieldName: '_createdAt', valueType: 'DATE',   operator: 'gte', date: '2025-01-01T00:00:00.000Z' }
  ]}],
  selects: ['_id', 'body.name', 'body.email'],
  skipLines: true,
  limit: 100
})
```

### 插入新的折扣碼（含表身）

```js
javacat_insert({
  table: 'poscoupon',
  data: [{
    body:  { name: 'NY2025', discount: 100, validFrom: '2025-01-01' },
    lines: { applicableStores: [{ storeId: '001' }, { storeId: '002' }] }
  }]
})
```

### 更新會員 status

```js
javacat_update({
  table: 'posmember',
  data: [{
    id: '65a1b2c3d4e5f6a7b8c9d0e1',
    body: { status: 'inactive' }
  }]
})
```

> ⚠️ `update` 的 `lines` 是**整批替代**而非 patch。若只想 append 一列，要先 `find` 拿到完整 lines、本地 append 後再傳。

---

## 6. 常見錯誤與處理

| 錯誤訊息 | 原因 | 處理 |
|---------|------|------|
| 「尚未設定環境」 | 沒先呼叫 `javacat_switch_environment` | 先 switch 再重試 |
| 「已取消登入，未執行原工具」 | elicitation 任一段被 decline/cancel | 再次呼叫工具、完整填完表單 |
| 「client 不支援互動式登入」 | client 沒實作 elicitation | 顯式 `javacat_request_otp` + `javacat_login` |
| 「寄送 OTP 失敗」 | name/email 不匹配 JavaCat 帳號 | 確認帳號 email；或改用 access_key |
| permission denied / 4xx GraphQL | 當前帳號無此 table 操作權限 | 檢查 JavaCat 後台權限或換帳號 |
| 「回應過大（…字元），已截斷」 | find 結果 > 25,000 字元 | 縮小 `limit`、加 `selects`、開 `skipLines` |
| 查詢長時間無回應 / 逾時 / 操作卡住 | filters 內**沒給日期範圍**，後端掃全表 | 加 `_createdAt` 或 `_updatedAt` 的 `gte` 條件（參見第 3 章「查詢效能守則」） |

---

## 7. 與其他 skill 的分工

| 想做的事 | 載入哪本 skill |
|---------|---------------|
| 用 MCP 工具操作 JavaCat 資料（本指南） | `norwegianforest-workspace:mcp-wonderpet-table-usage` |
| 直接以 `JavaCatGraphQLClient` lib 呼叫 GraphQL | `norwegianforest-workspace:javacat-graphql-client` |
| 撰寫或修改 table schema 定義 | `norwegianforest-workspace:javacat-table-architecture` |
| POS 業務邏輯與表格細節 | `norwegianforest-workspace:pos-knowledge-base` |
| 會員 / 點數 / CRM 同步邏輯 | `norwegianforest-workspace:member-system-knowledge` |
| DSV 出貨流程與庫存同步 | `norwegianforest-workspace:dsv-system-knowledge` |
| 調撥單業務邏輯 | `norwegianforest-workspace:transferorder-business-logic` |
| 撰寫 policy / hook / function 腳本 | `norwegianforest-workspace:function-script-context` |
| 為腳本撰寫測試 | `norwegianforest-workspace:norwegianforest-testing-architecture` |
