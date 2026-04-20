# dsvorderdetail（DSV 出貨明細）

## 欄位定義

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `name` | KEY | 明細編號 = `{調撥單_id}_{表身列_id}` |
| `dsvOrderName` | REF | 出貨單號 → dsvorder.name |
| `itemName` | REF | 料件編號 → ITEM.name |
| `quantity` | INT | 出貨數（對應調撥明細的 amount） |
| `actualQuantity` | INT/NULL | 實際出貨數（DSV 確認後回填） |
| `cuft` | FLOAT | 材積數 |
| `fromLocationName` | REF | 出貨倉庫 → LOCATION.name |
| `toLocationName` | REF | 目標倉庫 → LOCATION.name |
| `expirationDate` | DATE/NULL | 效期（batchPolicy 回填，null 代表尚未分配） |
| `batchSerial` | STRING/NULL | 批號（batchPolicy 回填，null 代表尚未分配） |
| `transferOrderItemId` | STRING | 調撥明細表身列 ID = transferorder.lines.items._id |
| `sysMemo` | STRING/NULL | 系統備註 |

## 建立時機

在 `upsertDSVOrder`（transferorder.policy 內）中，依每筆 `transferorder.lines.items` 建立對應的 dsvorderdetail：

```
transferorder.lines.items[0] (_id=AAA) → dsvorderdetail { name: "{dsvOrderId}_AAA", transferOrderItemId: "AAA" }
transferorder.lines.items[1] (_id=BBB) → dsvorderdetail { name: "{dsvOrderId}_BBB", transferOrderItemId: "BBB" }
```

**新建時 `batchSerial` 和 `expirationDate` 均為 `null`**，等待 `batchPolicy` 回填。

## batchPolicy 批號回填機制

### 觸發時機

- `batchInsertV2 dsvorderdetail`（新建明細後）→ INSERT 情境，`oldRecords = undefined`
- `batchUpdateV2 dsvorderdetail`（`ignorePolicy: false`）→ UPDATE 情境

### 回填觸發條件（needFillBatchSerialRecords）

```typescript
const needFillBatchSerialRecords = records.filter(record => {
  const { batchSerial, expirationDate, transferOrderItemId } = record?.body || {};
  return transferOrderItemId && (!batchSerial || !expirationDate);
  // transferOrderItemId 有值 + 批號或效期任一為空 → 需要回填
});
```

### 批號分配邏輯（fillBatchSerialEach）

以效期由舊到新（FEFO，First Expired First Out）從 `dsvinventory` 分配批號：

1. 查詢 dsvinventory（依 `fromLocationName` + `itemName` 篩選）
2. 排除在途數量（`getDSVInTransitInfo`，排除自身 dsvorder）
3. 依以下優先順序分配：
   - 有指定效期 + 有指定批號 → 找完全匹配
   - 有指定效期 + 無批號 → 找同效期的批號
   - 無指定效期 + 有批號 → 找指定批號
   - 無效期無批號 + 門市目標 → 找最近效期（大於今天）
   - 無效期無批號 + 非門市 → 找允效 9 個月以上的批號
4. 若庫存不足 → 記錄 warningMessage
5. 若找不到 → 記錄 invalidMessage → 拋出錯誤

### 回填結果的處理

batchPolicy 執行完畢後，依序執行三個更新：

```
① batchUpdateV2 dsvorderdetail（ignorePolicy:true）
    → 更新 batchSerial, expirationDate

② batchUpdateV2 transferorder rowSetUpdates（ignorePolicy:true）
    → 更新調撥明細的 batchSerial, expirationDate, amount, systemMemo
    → user 帶 isFromDSVOrderDetailBatchPolicy:true（防循環旗標）
    → 觸發 transferorder.batchBeforeUpdate [A2]

③ [若 oldRecords 存在] batchUpdateV2 dsvorder（totalQuantity:0）
    → 觸發 dsvorder.policy 重算庫存
```

> **注意**：③ 只在 UPDATE 情境（`oldRecords` 有值）時執行。INSERT 情境跳過此步驟，因為後續的 `updateV2 dsvorder (updatedAtByTransferOrder)` 會在所有更新完成後觸發 dsvorder.policy（更準確）。

### 特殊情況：WHAT 類型

```typescript
// WHAT 類型跳過批號分配（由任務自行處理）
if (transferOrder.body.type === 'WHAT') continue;

// 系統任務（Cron）+ WHAT 且明細有門市 systemMemo → 不分配批號
const isFromWHATTransferTask =
  transferOrder.body.type === 'WHAT' &&
  Validator.isCronTrigger(user) &&
  (targetTransferOrderItem?.systemMemo || '').split(',').some(loc => Validator.isStoreId(loc));
if (isFromWHATTransferTask) return { updateDetailBody, updateTOItems };
```

### quantityChangedDetails 區塊

在 `needFillBatchSerialRecords` 處理**之後**，檢查所有 records 的數量是否有變動：

```typescript
const quantityChangedDetails = records.filter(record => {
  const oldRecord = oldRecords?.find(old => old.body.name === record?.body.name);
  return !!(record && (!oldRecord || oldRecord.body.quantity !== record?.body.quantity));
});

// 只在 UPDATE 情境（oldRecords 有值）才觸發 dsvorder.policy 重算
if (dsvOrderNames.length && oldRecords) {
  await ctx.query.batchUpdateV2<DSVOrderBody>({ body: { totalQuantity: 0 }, ... });
}
```

## 與 transferorder 的數量同步

當調撥明細（transferorder items）的 amount 被修改時：
- `transferorder.batchBeforeUpdate` 找到對應的 dsvorderdetail
- 更新 `dsvorderdetail.quantity = newAmount`（`ignorePolicy:true`）
- 若非來自 dsvorderdetail.batchPolicy，更新 dsvorder 觸發重算
