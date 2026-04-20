# DSV 庫存追蹤：dsvinventory 與 dsvinventoryoperation

## dsvinventory（DSV 配貨庫存）

### 用途

儲存從 DSV FTP 同步的總倉實際庫存，以料件+批號+倉庫為 key，記錄當前可配貨數量。
這是 `dsvorderdetail.batchPolicy` 批號分配的資料來源。

### 欄位定義

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `name` | KEY | 配貨庫存編號（通常為 `{locationName}_{itemName}_{batchSerial}` 組合） |
| `itemName` | REF | 料件編號 → ITEM.name |
| `locationName` | REF | 倉庫編號 → LOCATION.name（W17R01 或 W17R05） |
| `batchSerial` | STRING | 批號 |
| `expirationDate` | DATE/NULL | 效期 |
| `amount` | INT | 可配貨庫存數量 |

### 查詢方式

在 batchPolicy 中查詢庫存：

```typescript
const dsvInventories = await Utils.findAll<DSVInventoryBody>(ctx, {
  table: 'dsvinventory',
  filters: [{
    body: {
      itemName: { $in: itemNames },
      locationName: { $in: fromLocationNames },
    },
  }],
  selects: ['body.itemName', 'body.locationName', 'body.expirationDate', 'body.batchSerial', 'body.amount'],
  softSort: [
    { field: 'body.expirationDate', direction: 1 },  // 效期由舊到新（FEFO）
    { field: 'body.batchSerial', direction: 1 },
  ],
});
```

### 在途數量的扣除

dsvinventory 記錄的是 DSV 實際庫存，不含在途扣減。
批號分配時需手動扣除已有的在途數量（getDSVInTransitInfo）：

```typescript
// 可配貨數 = 庫存數 - 在途數
const pickedAmount = Math.max(0, Math.min(remainingQuantity, inventoryAmount - inTransitQty));
```

**在途定義**：dsvorderdetail 中，對應 dsvorder 的狀態為 `PENDING`/`ORDER_CREATED`/`PICKING`
且 `pickedTime` 為 null（未揀貨，代表庫存尚未實際出倉）。

---

## dsvinventoryoperation（DSV 庫存異動明細）

### 用途

稽核用途。記錄每次 dsvinventory 異動前後的數量，提供完整的庫存變化歷程。

### 欄位定義

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `name` | KEY | 紀錄編號（自動序列） |
| `inventoryName` | REF | 配貨庫存編號 → dsvinventory.name |
| `locationName` | REF | 倉庫編號 → LOCATION.name |
| `itemName` | REF | 料件編號 → ITEM.name |
| `batchSerial` | STRING | 批號 |
| `beforeAmount` | INT | 異動前庫存數 |
| `afterAmount` | INT | 異動後庫存數 |
| `memo` | STRING/NULL | 備註（記錄異動原因） |

### 建立時機

每次 `dsvdailytask.sync.ts` 執行庫存同步，且有數量變動時，自動建立一筆 dsvinventoryoperation。

---

## getDSVInTransitInfo 函式詳解

位於 `dsvorderdetail/batchPolicy.ts`，計算指定批號在各倉庫的在途調撥數量：

```typescript
async function getDSVInTransitInfo(ctx, args: {
  itemNames: string[];
  batchSerials: string[];
  excludeDSVOrderNames?: string[];   // 排除自身的 dsvorder，避免重複計算
}): Promise<{
  [locationName: string]: {
    [itemName_batchSerial: string]: {
      dsvOrderNames: string[];
      transferOrderNames: string[];
      quantity: number;           // 在途數量（該批號+來源倉的合計）
    }
  }
}>
```

查詢邏輯：
1. 找出指定 itemNames + batchSerials 的所有 dsvorderdetail（排除 excludeDSVOrderNames）
2. 只計算 dsvOrderStatus 為 `PENDING`/`ORDER_CREATED`/`PICKING` 且 `pickedTime` 為 null 的出貨單
3. 依 `fromLocationName` + `itemName_batchSerial` 彙總數量

---

## 庫存相關的 queries 效能注意

| 查詢 | 估計成本 | 說明 |
|-----|---------|-----|
| getDSVInTransitInfo | 2 個 queries | 1. findAll dsvorderdetail + 2. findAll dsvorder |
| getStoreLocationDSVOrderNames | 1~2 個 queries | 依是否有 fromTransferOrderName |
| getDSVInventoryAmounts | 1 個 query | findAll dsvinventory |
| dsvinventory 查詢（batchPolicy） | 1 個 query | 批次查詢所有 itemNames |

dsvorder.policy 中這些查詢全部執行時約 6~8 個 DB queries。
