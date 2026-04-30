---
name: mcp-wonderpet-table-usage
description: >
  使用 mcp-wonderpet-table 的 MCP tool（javacat_find / javacat_count /
  javacat_insert / javacat_update / javacat_list_tables / javacat_login /
  javacat_request_otp / javacat_switch_environment）操作 JavaCat 資料前必讀。
  涵蓋使用前置流程、filter cheat sheet（含完整 operator 表）、常用 table 速查
  （依 TABLE_GROUP 分領域、cross-link 業務 skill）、典型查詢/插入/更新範例與錯誤對照。
  專為「透過 MCP 工具」操作的 agent 設計，不重複 javacat-graphql-client（lib API）
  與 javacat-table-architecture（schema 定義）內容。
---

# mcp-wonderpet-table 使用指南

8 個 MCP tool 的 input schema 在工具列表已說明，本指南聚焦於：**先做什麼、查哪張表、filter 怎麼寫、怎麼避開常見錯誤**。

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

```
{
  _id:            string                                   // MongoDB ObjectId
  _createdAt:     Date                                     // 建立時間
  _updatedAt:     Date                                     // 最後更新時間
  _archivedAt:    Date | null                              // 封存時間（null 代表未封存）
  _approveStatus: 'APPROVED' | 'DENIED' | 'PENDING' | 'ERROR'
  body:  { ... }                                           // 表頭業務欄位
  lines: { [lineName]: Array<...> }                        // 表身（多列子資料）
}
```

- 系統欄位以 **底線開頭**（`_id`、`_createdAt`、`_archivedAt`...）。
- 業務欄位在 `body.xxx` 或 `lines.xxx[].yyy`。
- 用 `selects: ['_id', 'body.name']` 控制回傳欄位、避免回應截斷。
- `skipLines: true` 可大幅加快查詢（不需要表身時務必設定）。

---

## 3. Filter Cheat Sheet

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
- `balance` — 庫存檔 v2
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
