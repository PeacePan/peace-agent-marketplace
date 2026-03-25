# transferorder ↔ DSV 出貨系統整合

## 整合概覽

```
transferorder.policy
  └─ upsertDSVOrder()
        ├─ 建立/更新 dsvorder
        ├─ 建立/更新 dsvorderdetail（每筆表身列一筆明細）
        └─ 更新 dsvorder.updatedAtByTransferOrder → 觸發 dsvorder.policy
```

## upsertDSVOrder 詳細流程

函式位於 `NorwegianForest/tables/inventory/scripts/transferorder/policy.ts`

### 入口條件

```typescript
if (
  to._id &&
  (to.body.type === 'WH' || to.body.type === 'WHAT') &&
  hqWareHouseStatus === '可調撥' &&
  isHqWareHouseTransfer(fromLocation) &&   // W17R01 或 W17R05
  !to.body.skipLogistics
) {
  await upsertDSVOrder(ctx, { to, user });
}
```

### 執行步驟

**步驟 1：查詢既有 dsvorder**
- dsvOrderName = `${to._id}`（用調撥單的系統 ID 作為 DSV 出貨單 name）
- 查詢包含 `dsvOrderStatus`、`dsvOrderFile`、`pickedTime`、`actualShippedTime`、`deliveredTime`

**步驟 2：若不存在則建立 dsvorder**
```typescript
await ctx.query.insertV2<DSVOrderBody>({
  table: 'dsvorder',
  body: {
    name: dsvOrderName,
    transferOrderName: toName,
    fromLocationName: fromLocation,
    toLocationName: toLocation,
    shippingAddress: to.body.shippingAddress,
    estimatedShippedTime: to.body.estimatedShippedTime,
    flowStatus: 'TRANSFER_ORDER_GENERATED',
    dsvOrderStatus: 'PENDING',
    totalQuantity: 0,
  },
  ignorePolicy: true,
});
hasUpdated = true;
```

**步驟 3：回寫 dsvOrderName 到調撥單**
```typescript
await ctx.query.updateV2<TransferOrderBody>({
  table: 'transferorder',
  key: { name: 'name', value: toName },
  body: { dsvOrderName },
  ignorePolicy: true,
});
```

**步驟 4：比對並更新 dsvorderdetail**
- 查詢既有 dsvorderdetail（以 `dsvOrderName=$dsvOrderName` 查詢）
- 建立 existedMap（key = transferOrderItemId）
- 對每筆調撥明細（`toItems`）：
  - **已存在且未封存** → 更新 quantity/cuft（若有變動）
  - **已存在但已封存** → 取消封存（unarchive）後更新
  - **不存在** → 新建（無 batchSerial/expirationDate，等待 batchPolicy 回填）
  - **已存在但表身列已移除** → 封存對應的 dsvorderdetail
- `ignorePolicy` 設定：
  ```typescript
  ignorePolicy: !!user && /總倉自動調撥任務/.test(user)
  // WHAT 任務觸發時 = true，人工觸發時 = false（會跑 batchPolicy）
  ```

**步驟 5：更新 dsvorder（觸發 policy）**
```typescript
if (hasUpdated) {
  await ctx.query.updateV2<DSVOrderBody>({
    table: 'dsvorder',
    key: { name: 'name', value: dsvOrderName },
    body: { totalQuantity: 0, updatedAtByTransferOrder: new Date() },
    ignorePolicy: false,  // 觸發 dsvorder.policy（意圖性的）
  });
}
```

## dsvorder.name 的命名規則

**重要**：`dsvorder.name` = 調撥單的 `_id`（系統流水號），**不是** 調撥單的 `name`（`TO` 前綴的業務單號）。

```typescript
const dsvOrderName = `${to._id || ''}`;
```

這樣設計讓 dsvorder 和 transferorder 之間有唯一且穩定的對應關係。

## dsvorderdetail.name 的命名規則

```
{調撥單_id}_{表身列_id}
```

確保每筆調撥明細對應唯一的 DSV 出貨明細。

## 跳過 DSV 的情境

### skipLogistics = true

用一般調撥（不走 DSV），通常用於已有其他物流安排的情況：
- 設定時若已有 dsvorder 且狀態為 `PENDING`，自動取消（設為 `CANCELLED`）
- 切換為一般調撥後**無法再切回** DSV（需作廢重建）

### WHAT 類型被系統任務建立

系統任務（`hqreorder.ts`）建立 WHAT 調撥單時，`ignorePolicy: true` 跳過 batchPolicy：
```typescript
// hqreorder.ts 中使用的旗標
user: JSON.stringify({
  functionName: '總倉自動調撥任務',
  skipBeforeUpdate: true,
  ignoreDSVOrderDetailPolicy: true,
})
```

## 出貨完成後的保護

```typescript
// policy.ts 中的保護
const isDSVBlocked =
  dsvOrder?.body.dsvOrderFile &&
  (['SHIPPED', 'DELIVERING', 'DELIVERED', 'CANCELLED'].includes(dsvOrder.body.dsvOrderStatus));

if (dsvOrder && isDSVBlocked && isTriggerByHuman && isItemsChanged && !to.body.skipLogistics) {
  return `DSV 出貨單 ${dsvOrder.body.name} 已出貨完成，無法再由調撥單更新調撥明細`;
}
```

已拋單後（有 `dsvOrderFile`），部分欄位也無法由調撥單更新（shippingAddress、estimatedShippedTime）。

## 完整整合生命週期

```
[建立 WH 調撥單]
  → policy: 設 hqWareHouseStatus='検査中'，建立 todoJob

[檢查完成，hqWareHouseStatus='可調撥']
  → 再次觸發 policy → upsertDSVOrder
  → dsvorder (PENDING) + dsvorderdetail (無批號)

[dsvorderdetail.batchPolicy 批號回填]
  → 填入 batchSerial/expirationDate
  → 更新 transferorder 表身列

[人工執行「出貨拋單」]
  → 生成 CSV → 上傳 DSV FTP
  → dsvOrderStatus: PENDING → ORDER_CREATED

[排程更新訂單狀態]
  → 同步 DSV 回傳狀態 (PICKING → SHIPPED → DELIVERED)
  → dsvshipment 記錄貨況

[執行「調撥轉驗收」]
  → 建立 ITEM_RECEIPT
  → transferorder.itemReceiptName = 驗收單號
  → transferorder.to2ir = '成功'

[執行「釋放鎖庫」]
  → unlockStatus = '已釋放'
```
