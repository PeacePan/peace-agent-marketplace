# 查詢操作（Query）

所有查詢方法均在 `client.query` 命名空間下。

## 方法總覽

| 方法 | 說明 |
|------|------|
| `find()` | 查詢多筆資料，支援批次與進度回調 |
| `get()` | 以 key/value 查詢單筆資料 |
| `count()` | 計算符合條件的資料總筆數 |
| `permissions()` | 查詢指定表格的欄位權限 |

---

## `find()`

查詢多筆資料的主要方法。

### 基本用法

```typescript
const records = await client.query.find({
  table: 'member',
  filters: [{ body: { name: { $eq: 'john' } } }],
  multiSort: [{ field: 'body.createdAt', direction: -1 }],
  limit: 20,
  offset: 0,
});
```

### 篩選條件（`filters`）

```typescript
// filters 為 OR 陣列，陣列內每個物件為 AND 條件
filters: [
  {
    body: {
      name: { $eq: 'john' },        // 等於
      age:  { $gte: 18, $lte: 65 }, // 範圍
      tags: { $in: ['vip', 'new'] },// 包含於
    },
    lines: {
      items: { productId: { $eq: 'P001' } },
    },
  },
]
```

### 批次查詢（大量資料）

```typescript
const records = await client.query.find(
  { table: 'product' },
  {
    useBatch: true,
    totalCount: 5000,    // 目標筆數（省略則抓全部）
    concurrency: 4,      // 並發請求數，預設 4
    limitPerQuery: 50,   // 每次請求筆數，預設 50
    onProgress: (progress) => console.log(`${Math.round(progress * 100)}%`),
  }
);
```

### 查詢到最後一筆

```typescript
const records = await client.query.find(
  { table: 'order' },
  { untilEnd: true }
);
```

### 中止請求

```typescript
const controller = new AbortController();
const records = await client.query.find(
  { table: 'member' },
  { abortSignal: controller.signal }
);
controller.abort(); // 中止
```

### 排序

```typescript
// 多條件排序（最多兩個欄位）
multiSort: [
  { field: 'body.category', direction: 1 }, // -1 降冪，1 升冪
  { field: 'body.name', direction: 1 },
]
```

### 封存狀態篩選

```typescript
import { ArchivedStatus } from '@norwegianForestLibs/enum';

// 只查詢未封存（預設）
archived: ArchivedStatus.NORMAL

// 只查詢已封存
archived: ArchivedStatus.ARCHIVED_ONLY

// 全部（含封存）
archived: ArchivedStatus.ALL
```

---

## `get()`

以 keyName + keyValue 查詢單筆資料：

```typescript
const member = await client.query.get({
  table: 'member',
  keyName: 'name',     // 欄位名稱（body 欄位）
  keyValue: 'john',    // 值
});
// 找不到回傳 null
```

---

## `count()`

```typescript
const total = await client.query.count({
  table: 'member',
  filters: [{ body: { isActive: { $eq: true } } }],
});
```

---

## `permissions()`

查詢當前使用者對指定表格特定操作的欄位權限：

```typescript
const perm = await client.query.permissions({
  table: 'member',
  action: 'read', // 或 'write', 'delete', 等
});
// perm.effect      → 整體權限 'allow' | 'deny'
// perm.bodyFields  → [{ name, effect }]
// perm.lineFields  → [{ line, name, effect }]
```

---

## 系統內建欄位

所有資料都有以下內建欄位（`BUILTIN_BODY_FIELD2`）：

```
_id, _createdAt, _createdBy, _updatedAt, _updatedBy,
_archivedAt, _archivedBy
```

加上顯示名稱版本：
```
_createdBy_displayName, _updatedBy_displayName, _archivedBy_displayName
```

## `selects` 指定回傳欄位（減少資料傳輸量）

```typescript
await client.query.find({
  table: 'member',
  selects: ['body', '_id', 'body.name', 'lines.items'],
});
```
