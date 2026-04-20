# 表格表頭 (MyTableBody)

表格表頭定義了表格本身的元資料，控制表格的行為、分類、權限等。

## 必要屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `name` | `string` | 表格名稱，必須符合正規表示式 `/^[a-z0-9_]{2,100}$/`，全小寫英文 |
| `displayName` | `string` | 中文顯示名稱，用於前端 UI |
| `type` | `TableType` | 表格類型，見下方說明 |
| `schemaVer` | `string` | 架構版本號，目前使用 `'2'` |

## TableType 表格類型

| 值 | 說明 |
|----|------|
| `DATA` | 一般資料表格，用於儲存業務資料（最常用） |
| `SYSTEM` | 系統表格，JavaCat 核心使用 |
| `UPDATE` | 變更單表格，用於記錄資料變更歷程 |

## TableStorageType 儲存類型

| 值 | 說明 |
|----|------|
| `PHYSICAL` | 實體儲存，資料存在 DocumentDB 中（預設） |
| `VIRTUAL` | 虛擬表格，不實際儲存資料 |

## IdType 紀錄 ID 類型

| 值 | 說明 |
|----|------|
| `AUTO` | 自動編碼（搭配 autoKey 設定） |
| `TIMESTAMP` | 時間序編碼 |
| `NATIVE` | 原生 ObjectId |
| `UNKNOWN` | 未指定 |

## 可選屬性

### 基本設定

| 屬性 | 型別 | 說明 |
|------|------|------|
| `version` | `number` | 表格版本號，用於前端判斷是否需要刷新快取，開發環境可設為 `null` |
| `description` | `string` | 表格說明 |
| `group` | `string` | 業務群組名稱，用於中台分類顯示 |
| `ordering` | `number` | 排序權重，數字越小越前面 |
| `icon` | `string` | 圖示名稱 |
| `isPublicTable` | `boolean` | 是否為公開表格 |

### 紀錄顯示

| 屬性 | 型別 | 說明 |
|------|------|------|
| `nameField` | `string` | 指定紀錄編號欄位，用於識別紀錄 |
| `displayNameField` | `string` | 指定紀錄顯示名稱欄位 |
| `idType` | `IdType` | 紀錄 ID 產生方式 |

### 簽核

| 屬性 | 型別 | 說明 |
|------|------|------|
| `enableApproval2` | `boolean` | 是否啟用簽核流程 |
| `approvalMode` | `ApprovalMode` | 簽核模式，嚴格模式下簽核意見必填且禁止批次簽核 |

### 變更單

| 屬性 | 型別 | 說明 |
|------|------|------|
| `source` | `string` | 變更單來源表格名稱 |
| `limitedBodyFields` | `string` | 限定變更單可操作的表頭欄位（逗號分隔） |
| `limitedLineFields` | `string` | 限定變更單可操作的表身欄位（逗號分隔） |

### 資料庫

| 屬性 | 型別 | 說明 |
|------|------|------|
| `dbSource` | `DBSource` | 資料庫來源：`DOCUMENTDB`（預設）或 `ATHENA` |
| `dbTableName` | `string` | 實體資料庫表格名稱（當不使用預設名稱時） |

### 排序與查詢

| 屬性 | 型別 | 說明 |
|------|------|------|
| `defaultSearchArgument` | `string` | 預設查詢條件 |
| `defaultSortField` | `string` | 預設排序欄位 |
| `defaultSortDirection` | `number` | 預設排序方向（`1` 升冪，`-1` 降冪） |
| `downloadBatchSize` | `number` | 批次下載大小，不設定代表不限制 |

### 進階功能

| 屬性 | 型別 | 說明 |
|------|------|------|
| `jobQueues` | `string` | 工作佇列數量 |
| `enableCron` | `boolean` | 是否啟用排程 v2 |
| `publishOn` | `string` | 發布控制 |
| `dependencyTables` | `string` | 依賴表格（patch 時會檢查是否一起 patch） |

## 範例

```typescript
body: {
  name: TABLE_NAME.PURCHASE_ORDER,
  displayName: TABLE_DISPLAY_NAME.PURCHASE_ORDER,
  type: TableType.DATA,
  group: TABLE_GROUP.PROCUREMENT,
  schemaVer: '2',
  version: null,
  icon: 'shopping-cart',
  ordering: 100,
  nameField: 'name',
  displayNameField: 'name',
}
```
