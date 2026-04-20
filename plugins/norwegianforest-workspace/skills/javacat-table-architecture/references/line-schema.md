# 表身定義 (LineSchema) 與表身欄位 (LineFieldSchema)

表身（Line）是表格定義中用於記錄明細資料的區段。一個表格可以有多個表身，每個表身包含多列（Row）。

## LineSchema 表身定義

定義一個表身區段的元資料和行為。

### 必要屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `name` | `string` | 表身名稱 |
| `displayName` | `string` | 中文顯示名稱 |
| `readWrite` | `LineReadWrite` | 表身讀寫權限 |

### LineReadWrite 表身讀寫權限

控制整個表身的列操作行為（個別欄位的可否更新仍依欄位自身的 `readWrite` 決定）：

| 值 | 建立 | 新增列 | 更新列 | 移除列 |
|----|------|--------|--------|--------|
| `FULL` | O | O | O | O |
| `UPDATE` | O | X | O | X |
| `PUSH` | O | O | O | X |
| `PULL` | O | X | O | O |
| `INSERT` | O | X | X | X |
| `READ` | X | X | X | X |

- **建立**：首次新增紀錄時可以帶入表身列
- **新增列**：對已存在紀錄新增表身列
- **更新列**：更新已存在的表身列欄位值
- **移除列**：刪除已存在的表身列

### 可選屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `scriptReadWrite` | `LineReadWrite` | 腳本時期的表身讀寫權限 |
| `idType` | `IdType` | 表身列 ID 類型 |
| `compoundLineKey` | `string` | 複合鍵欄位名稱（逗號分隔） |
| `ordering` | `number` | 顯示排序 |
| `isReversed` | `boolean` | 反序呈現列 |
| `batchAddLineRowBy` | `string` | 批次新增展開欄位 |
| `description` | `string` | 說明 |
| `editDescription` | `string` | 編輯時的說明 |
| `isHidden` | `boolean` | 是否隱藏 |
| `minLength` | `number` | 列最少數量 |
| `maxLength` | `number` | 列最多數量 |
| `defaultSortField` | `string` | 預設排序欄位 |
| `defaultSortDirection` | `-1 \| 1` | 排序方向 |

### LineType 資料嵌入類型

| 值 | 說明 |
|----|------|
| `STANDARD` | 標準表身，資料內嵌在紀錄中（預設） |
| `EXTERNAL` | 外部表身，資料來自另一個表格 |

外部表身相關屬性：

| 屬性 | 型別 | 說明 |
|------|------|------|
| `extTableName` | `string` | 外部關聯的表格名稱 |
| `extSearchArgument` | `string` | 外部表格的搜尋參數 |
| `isExtMutable` | `boolean` | 外部表身的資料是否可被修改 |

## LineFieldSchema 表身欄位定義

表身欄位繼承了 `FieldSchema` 的所有屬性，並額外增加：

| 屬性 | 型別 | 說明 |
|------|------|------|
| `lineName` | `string` | 所屬表身名稱（必須對應到 `lines` 中某個 `LineSchema.name`） |
| `isLineKey` | `boolean` | 是否為該表身的主鍵欄位 |

### 與 FieldSchema 的差異

1. 表身欄位**不支援** `unique` 約束
2. 表身欄位必須指定 `lineName`
3. `fieldType` 為 `KEY` 的欄位只能出現在表頭，表身中使用 `isLineKey: true` 標記主鍵

## 系統內建表身欄位 (BUILTIN_LINE_FIELD)

每個表身會自動包含以下系統欄位：

| 欄位名稱 | 顯示名稱 | 說明 |
|---------|---------|------|
| `_id` | 表身列編號 | 系統主鍵 |
| `_createdAt` | 建立時間 | 該列的建立時間 |
| `_createdBy` | 建立者 | 建立該列的使用者 |
| `_createdBy_displayName` | 建立者.使用者名稱 | 建立者的顯示名稱 |
| `_updatedAt` | 更新時間 | 該列的最後更新時間 |
| `_updatedBy` | 更新者 | 最後更新該列的使用者 |
| `_updatedBy_displayName` | 更新者.使用者名稱 | 更新者的顯示名稱 |

## 範例

```typescript
// 表身定義
lines: [
  {
    name: 'detail',
    displayName: '明細',
    readWrite: LineReadWrite.FULL,
    scriptReadWrite: LineReadWrite.FULL,
  },
],

// 表身欄位定義
lineFields: [
  {
    ...INSERT_REF_KEY_FIELD,
    lineName: 'detail',
    name: 'productId',
    displayName: '商品編號',
    refTableName: 'product',
    refFieldName: 'name',
    refDataFields: 'displayName,unit',
  },
  {
    ...UPDATE_INT,
    lineName: 'detail',
    name: 'quantity',
    displayName: '數量',
    numberMin: 1,
  },
  {
    ...UPDATE_FLOAT,
    lineName: 'detail',
    name: 'unitPrice',
    displayName: '單價',
    numberMin: 0,
  },
],
```
