# dsvshipment（DSV 出貨貨況）

## 用途

記錄 DSV 回傳的貨況資訊，每批出貨（每個批號/效期組合）一筆紀錄。
用於追蹤實際配送進度，與 dsvorder 的訂單級狀態互補。

## 欄位定義

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `name` | KEY | 貨況編號（格式：`{出貨單號}_{料件}_{批號}_{數量}_{狀態}_{索引}`） |
| `dsvOrderName` | REF | 出貨單號 → dsvorder.name |
| `transferOrderName` | REF | 調撥單業務單號 → transferorder.name |
| `transferOrderItemId` | STRING/NULL | 調撥明細表身列 ID |
| `itemName` | REF | 料件編號 → ITEM.name |
| `batchSerial` | STRING | 批號 |
| `expirationDate` | DATE/NULL | 效期 |
| `quantity` | INT | 出貨數量 |
| `status` | ENUM | 貨況狀態（見下方） |
| `fromLocation` | REF/NULL | 出貨倉庫 → LOCATION.name |
| `memo` | STRING/NULL | 出貨備註 |
| `pickedTime` | DATE/NULL | 揀貨時間 |
| `shippedTime` | DATE/NULL | 出貨時間 |
| `deliveredTime` | DATE/NULL | 交貨時間 |
| `orderStatusSyncedAt` | DATE/NULL | 最後狀態同步時間 |

## status 狀態值

| 狀態 | 說明 |
|-----|-----|
| `PENDING` | 等待出貨 |
| `PARTIAL_DELIVERED` | 部分交貨 |
| `PARTIAL_SHIPPED` | 部分出貨 |
| `ERROR` | 出貨錯誤 |
| `CANCELLED` | 已取消 |

## Lines

- `files`（PUSH）：貨況相關附件

## 同步機制

### sync.cron.ts（每 10 分鐘）

定期呼叫 `sync.ts`，從 DSV 系統拉取最新貨況：

1. 找出狀態為 `PENDING` 且有 `dsvOrderFile`（已拋單）的 dsvorder
2. 呼叫 DSV API 查詢各出貨單的配送狀態
3. 更新 dsvshipment 的時間戳（`pickedTime`、`shippedTime`、`deliveredTime`）
4. 更新對應的 dsvorder.dsvOrderStatus
5. 設定 `orderStatusSyncedAt` 記錄同步時間

### 與 dsvorder 的關係

- dsvorder 是訂單層級的狀態（`ORDER_CREATED` / `SHIPPED` / `DELIVERED`）
- dsvshipment 是批貨層級的狀態（每個批號各自的配送進度）
- dsvorder 的狀態通常根據 dsvshipment 的彙總結果更新

## Lines（外部表身，在 dsvorder）

dsvorder 以外部表身方式引用 dsvshipment：

```
dsvorder.detailShipments → dsvshipment WHERE dsvOrderName=$name
```

這讓使用者可以在出貨單頁面直接看到所有貨況記錄。
