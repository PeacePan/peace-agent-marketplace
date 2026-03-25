# dsvorder（DSV 出貨單）

## 欄位定義

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `name` | KEY | 出貨單號 = 對應調撥單的 `_id`（系統流水號，非業務單號） |
| `transferOrderName` | REF | 調撥單業務單號 → TRANSFER_ORDER.name |
| `itemReceiptName` | REF/NULL | 驗收單號 → ITEM_RECEIPT.name |
| `fromLocationName` | REF | 出貨倉庫 → LOCATION.name（W17R01 或 W17R05） |
| `toLocationName` | REF | 目標倉庫 → LOCATION.name |
| `shippingAddress` | STRING/NULL | 指定送貨地址 |
| `estimatedShippedTime` | DATE/NULL | 預計出貨日期 |
| `isSpecifyExpirationDate` | BOOLEAN/NULL | 出貨是否指定效期 |
| `flowStatus` | ENUM | 調撥驗收狀態（見下方） |
| `dsvOrderStatus` | ENUM | 訂單狀態（見下方） |
| `dsvOrderError` | STRING/NULL | 訂單異常原因 |
| `totalQuantity` | INT | 總出貨數（由 policy 計算） |
| `totalActualQuantity` | INT/NULL | 總實際出貨數 |
| `pickedTime` | DATE/NULL | 揀貨時間 |
| `actualShippedTime` | DATE/NULL | 實際出貨時間 |
| `deliveredTime` | DATE/NULL | 交貨時間 |
| `dsvOrderFile` | FILE/NULL | 拋單檔案（CSV，有此欄位代表已拋單） |
| `updatedAtByTransferOrder` | DATE/NULL | 調撥單最後更新時間（sentinel 欄位，觸發庫存重算） |

## flowStatus 狀態機

| 狀態 | 說明 | 觸發時機 |
|-----|-----|---------|
| `TRANSFER_ORDER_GENERATED` | 調撥單已建立 | upsertDSVOrder 建立時 |
| `TRANSFER_TO_RECEIPT` | 調撥轉驗收進行中 | 調撥單執行「調轉驗收」時 |
| `RECEIPT_IN_PROGRESS` | 驗收進行中 | 驗收單建立後 |
| `RECEIPT_COMPLETED` | 驗收完成 | 驗收完成後 |

## dsvOrderStatus 狀態機

```
PENDING → ORDER_CREATED → PICKING → PARTIAL_SHIPPED / SHIPPED
                                          ↓
                              PARTIAL_DELIVERED / DELIVERING
                                          ↓
                                       DELIVERED → COMPLETED
                          ↓
                       CANCELLED
                ERROR / FAILED（可重試）
```

| 狀態 | 說明 |
|-----|-----|
| `PENDING` | 等待拋單 |
| `READY` | 已準備（中間狀態） |
| `ORDER_CREATED` | 訂單已建立（DSV 收到拋單） |
| `PICKING` | 揀貨中 |
| `PARTIAL_SHIPPED` | 部分出貨 |
| `SHIPPED` | 全部出貨 |
| `DELIVERING` | 配送中 |
| `PARTIAL_DELIVERED` | 部分交貨 |
| `DELIVERED` | 全部交貨 |
| `COMPLETED` | 完成（驗收完成後） |
| `CANCELLED` | 已取消 |
| `ERROR` | 錯誤（可重試） |
| `FAILED` | 失敗（不可重試） |

> **注意**：`dsvOrderFile` 有值代表已拋單，此後 DSV 出貨已由外部系統控制，大部分欄位禁止由系統更改。

## dsvorder.policy 邏輯

policy 在 `updatedAtByTransferOrder` 被設定時執行完整庫存計算。

### 觸發條件（policy 內的判斷）

```typescript
if (record.body.updatedAtByTransferOrder &&
    (currentStatus === 'PENDING' || currentStatus === 'ORDER_CREATED')) {
  // 執行完整庫存計算
}
```

### 庫存計算流程（約 6~8 個 DB 查詢）

1. 查詢所有 dsvorderdetail（取 quantity）
2. `getDSVInventoryAmounts`：查詢 dsvinventory
3. `getDSVInTransitInfo`：查詢其他在途的 dsvorderdetail + dsvorder（排除自身）
4. `getStoreLocationDSVOrderNames`：查詢門市倉庫的 WHAT 調撥單 dsvOrderName（可能 ×2）
5. 更新 `totalQuantity` 等計算結果
6. `updateV2 dsvorder`（`ignorePolicy:true`）回寫

> **效能注意**：每次執行約 6~8 個 DB 查詢，避免在單次操作中多次觸發。

## 公開函式

| 函式 | 說明 | 特殊設定 |
|-----|-----|---------|
| 出貨拋單 | 生成 CSV 並準備上傳 | 可指定出貨時間、效期 |
| 執行出貨拋單 | 上傳 CSV 到 DSV FTP | Retry: 2 |
| 取消拋單 | 取消未拋單的出貨單 | — |
| 更新訂單狀態 | 同步 DSV 回傳狀態 | Public, Retry: 1 |
| 已驗收完成 | 確認無配送紀錄但已驗收的單完成 | — |
| 重置出貨拋單 | 清除拋單檔案重新拋單 | DEV 環境專用 |

## Lines（外部表身）

| 名稱 | 來源表格 | 說明 |
|-----|---------|-----|
| `orderDetails` | dsvorderdetail | WHERE dsvOrderName=$name |
| `detailShipments` | dsvshipment | WHERE dsvOrderName=$name |
| `updateStatusTodoJobs` | joblog | 狀態更新作業日誌 |

## Cron

- **更新訂單狀態排程**：每 5 分鐘，自動呼叫「更新訂單狀態」函式
