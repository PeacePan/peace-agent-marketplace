# 調撥單（transferorder）完整欄位定義

## 表格基本資訊

- **表格名稱**：`transferorder`（TABLE_NAME.TRANSFER_ORDER）
- **顯示名稱**：調撥單
- **表格類型**：DATA
- **Job Queues**：10 個佇列（第 9 個為總倉調撥檢查專用高優先佇列）
- **版本**：124

## Body 欄位

### 基本資訊

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `name` | KEY | 調撥單號（前綴 `TO`，格式：`TO{來源倉}{日期}{調撥別}{目標倉}{序號}`） |
| `subsidiary` | ENUM | 公司別 |
| `type` | ENUM | 調撥單別（`WH`/`WHAT`/`ST`/`DN`，詳見 types.md） |
| `memo` | STRING/NULL | 備註（總倉調撥時等同 DSV 出貨備註） |
| `expectedAmount` | INT/NULL | 應收量（系統自動計算，等於所有表身列 amount 加總） |
| `totalCuft` | FLOAT/NULL | 總材積（系統自動計算，根據 hqcuft 表） |
| `from` | REF | 來源倉庫 → LOCATION.name |
| `to` | REF | 目標倉庫 → LOCATION.name |

### 物流與出貨

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `skipLogistics` | BOOLEAN | 使用一般調撥（`true` = 不出訂單給 DSV，僅 W17R01/W17R05 可用） |
| `estimatedShippedTime` | DATE/NULL | 預計出貨日期（預設建立當天 +2 天，限非六日） |
| `shippingAddress` | STRING/NULL | 指定送貨地址（無則使用目標倉庫地址） |
| `itemReceiptName` | REF/NULL | 驗收單號 → ITEM_RECEIPT.name |
| `to2ir` | STRING/NULL | 調轉驗結果（成功時為 `'成功'`） |
| `to2irError` | STRING/NULL | 調轉驗錯誤訊息 |

### DSV 整合

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `dsvOrderName` | REF/NULL | DSV 出貨單號 → DSV_ORDER.name（值等於調撥單的 `_id`） |
| `hqWareHouseStatus` | STRING | 總倉調撥檢查狀態（`可調撥`/`検查中`/`不可調撥`/`錯誤`，詳見 hq-warehouse-status.md） |
| `hqWareHouseBlockReason` | STRING/NULL | 不可調撥原因（多行文字） |
| `hqTransferApproved` | BOOLEAN/NULL | 總倉調撥核准（執行「總倉調撥核准」函式後更新） |

### 自動調撥專用

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `fromTransferOrderName` | REF/NULL | 來源倉庫自動調撥轉調單號 → TRANSFER_ORDER.name |
| `hqReorderTaskSequence` | STRING/NULL | 總倉自動調撥任務序號（批次追蹤用） |

### 鎖庫

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `unlock` | ENUM/NULL | 鎖庫別（僅 WH 總倉調撥可用） |
| `unlockStatus` | STRING/NULL | 釋放鎖庫狀態（`等待釋放`/`已釋放`） |

### 其他系統欄位

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `isCanceled` | BOOLEAN | 是否作廢 |
| `cancelMemo` | STRING/NULL | 作廢原因 |
| `reserveArchive` | BOOLEAN/NULL | 預約封存 |
| `shopeeBoxfulOutboundType` | ENUM/NULL | 蝦皮 Boxful 出倉類型 |
| `shopeeBoxfulOutboundDate` | DATE/NULL | 蝦皮 Boxful 出倉日期 |

## Lines：items（調撥明細）

每筆調撥明細（表身列）的欄位：

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `_id` | 系統 | 表身列系統 ID（`transferOrderItemId` 的對應值） |
| `item` | REF | 料件編號 → ITEM.name |
| `expirationDate` | DATE/NULL | 效期 |
| `batchSerial` | STRING/NULL | 批號 |
| `amount` | INT | 調撥數量 |
| `cancelAmount` | INT/NULL | 作廢異動數量 |
| `cuft` | FLOAT/NULL | 材積數（由 policy 自動帶入 hqcuft 值） |
| `memo` | STRING/NULL | 備註（可多行） |
| `minShippingAmountMemo` | STRING/NULL | 批量單位提示（policy 自動計算，非批量單位倍數時設置警告） |
| `systemMemo` | STRING/NULL | 系統備註（WHAT 型態記錄目標門市編號） |
| `from` | REF/NULL | 實際來源倉庫（W17R01/W17R05 雙倉專用） |

## 關聯表格

| 關聯 | 方向 | 欄位 | 說明 |
|-----|-----|-----|------|
| LOCATION | → | `from`, `to` | 來源/目標倉庫 |
| DSV_ORDER | → | `dsvOrderName` | 對應的 DSV 出貨單（`_id` 作為 key） |
| ITEM_RECEIPT | → | `itemReceiptName` | 調轉驗產生的驗收單 |
| TRANSFER_ORDER | → | `fromTransferOrderName` | WHAT 型態的上游調撥單 |
| ITEM | → | `lines.items[].item` | 料件 |

## Cron Jobs

| 名稱 | 頻率 | 用途 |
|-----|-----|------|
| 釋放鎖庫排程 | 每 5 分鐘 | 調轉驗成功後自動釋放鎖庫 |
| 執行封存排程 | 每日台灣時間 03:00 | 自動調撥任務前執行預約封存 |
