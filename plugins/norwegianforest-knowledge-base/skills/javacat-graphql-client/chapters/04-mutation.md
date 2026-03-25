# 變更操作（Mutation）

所有變更方法均在 `client.mutation` 命名空間下。

## 方法總覽

| 方法 | 說明 | 回傳值 |
|------|------|--------|
| `insert()` | 新增資料 | `string[]`（新增的 `_id` 陣列） |
| `update()` | 更新資料 | `string[]`（更新的 `_id` 陣列） |
| `patch()` | 修補資料（僅更新有差異的欄位） | `string[]` |
| `archive()` | 封存資料 | `string[]` |
| `unarchive()` | 解除封存 | `string[]` |
| `execute()` | 執行表格自訂函數 | `Response \| null` |
| `call()` | 執行 JSON 參數函數 | `Response \| null` |
| `approve()` | 簽核通過 | `string[]` |
| `deny()` | 簽核駁回 | `string[]` |
| `dangerDropTable()` | 刪除整個表格 | `boolean`（DEV only） |

---

## `insert()`

```typescript
const ids = await client.mutation.insert({
  table: 'member',
  data: [
    {
      body: { name: 'john', email: 'john@example.com' },
      lines: {
        addresses: [{ city: 'Taipei', district: 'Xinyi' }],
      },
    },
  ],
  // 可選：簽核相關
  approvalSubject: '新增會員申請',
  approvalDescription: '說明原因',
});
// ids[0] → 新增後的 _id
```

---

## `update()`

更新支援三種表身操作：

```typescript
const ids = await client.mutation.update({
  table: 'member',
  data: [
    {
      keyName: 'name',    // 定位鍵（string 欄位）
      keyValue: 'john',
      body: { email: 'new@example.com' }, // 只傳要改的欄位

      // 新增表身列
      pushLineRows: [
        { lineName: 'tags', lineRow: { tag: 'vip' } },
      ],

      // 更新表身列（以 key 定位）
      setLineRows: [
        {
          lineName: 'addresses',
          keyName: 'city',
          keyValue: 'Taipei',
          lineRow: { district: 'Daan' },
        },
      ],

      // 移除表身列
      pullLineRows: [
        { lineName: 'tags', keyName: 'tag', keyValue: 'old_tag' },
      ],
    },
  ],
});
```

---

## `patch()`

與 `update()` 類似，但 server 會比對差異，只更新有變更的欄位（節省網路傳輸）：

```typescript
await client.mutation.patch({
  table: 'member',
  data: [
    {
      keyName: 'name',
      keyValue: 'john',
      body: { email: 'patched@example.com' },
      lineRows: [
        { lineName: 'tags', lineRow: { tag: 'premium' } },
      ],
    },
  ],
});
```

---

## `archive()` / `unarchive()`

```typescript
// 封存
await client.mutation.archive({
  table: 'member',
  data: [{ keyName: 'name', keyValue: 'john' }],
});

// 解除封存
await client.mutation.unarchive({
  table: 'member',
  data: [{ keyName: 'name', keyValue: 'john' }],
});
```

---

## `execute()`

執行表格上定義的伺服器端自訂函數，適合複雜的業務邏輯：

```typescript
const result = await client.mutation.execute({
  table: 'order',
  key: { name: 'orderNo', value: 'ORD-001' }, // 定位資料的 key
  name: 'confirmShipment',                      // 函數名稱
  argument: { shippingDate: '2025-01-01' },     // 傳入參數（可選）
  ignoreApproval: false,
  ignoreArchive: false,
});
// result 為 JSON.parse 後的回傳值，若回傳為 null 或解析失敗則為 null
```

---

## `call()`

執行不需綁定特定 record 的函數，參數完全自由（任意 JSON）：

```typescript
const result = await client.mutation.call({
  table: 'report',
  name: 'generateMonthlyReport',
  argument: JSON.stringify({ year: 2025, month: 1 }), // 必須 JSON.stringify
});
```

**`execute` vs `call` 差異：**

| 項目 | `execute` | `call` |
|------|-----------|--------|
| 需要定位 record | 是（key + value） | 否 |
| 參數格式 | 物件（自動序列化） | 字串（需手動 `JSON.stringify`） |
| 使用場景 | 針對特定資料執行操作 | 全域函數呼叫 |

---

## `approve()` / `deny()`

```typescript
// 簽核通過
await client.mutation.approve({
  table: 'leave_request',
  data: [{ keyName: 'requestNo', keyValue: 'LR-001' }],
  comment: '同意',
});

// 簽核駁回
await client.mutation.deny({
  table: 'leave_request',
  data: [{ keyName: 'requestNo', keyValue: 'LR-001' }],
  comment: '不符規定',
});
```

---

## 中止請求

所有 mutation 方法都支援 `abortSignal`：

```typescript
const controller = new AbortController();
await client.mutation.insert({
  table: 'member',
  data: [...],
}, { abortSignal: controller.signal });
```
