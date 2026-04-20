# dsvdailytask（DSV 每日配貨檔）

## 用途

每日建立一筆記錄，作為 DSV 庫存同步的控制中樞。管理從 DSV FTP 同步配貨庫存的排程與狀態。

## 欄位定義

| 欄位 | 類型 | 說明 |
|-----|-----|------|
| `name` | KEY | 每日配貨編號（格式：`YYYY/MM/DD`） |
| `date` | DATE | 資料時間（固定台灣時間 0 時） |
| `totalItems` | INT | 料件總數 |
| `dateDayEnd` | DATE | 資料當日結束時間（系統計算用） |
| `dateMonthStart` | DATE | 資料當月起始時間（系統計算用） |
| `lastSyncStartAt` | DATE/NULL | 最後庫存同步開始時間 |
| `lastSyncEndAt` | DATE/NULL | 最後庫存同步結束時間 |
| `syncStatus` | STRING | 庫存同步狀態 |
| `syncError` | STRING/NULL | 庫存同步錯誤訊息 |

## syncStatus 狀態值

| 狀態 | 說明 |
|-----|-----|
| `未同步` | 尚未開始同步 |
| `同步中` | 同步執行中 |
| `已完成` | 同步成功完成 |
| `已取消` | 同步被取消 |
| `錯誤` | 同步發生錯誤 |

## Lines（外部表身）

| 名稱 | 來源表格 | 篩選條件 |
|-----|---------|---------|
| `files` | PUSH | 上傳的庫存檔案 |
| `todayModifiedInventories` | dsvinventory | W17R01/W17R05，當日修改 |
| `todayDSVOrders` | dsvorderdetail | W17R01/W17R05，當日建立 |
| `currentMonthDSVOrders` | dsvorderdetail | 當月建立 |
| `todayHQTransferOrders` | transferorder | WH/WHAT，當日建立 |
| `currentMonthHQTransferOrders` | transferorder | 當月建立 |
| `syncLogs` | joblog | 同步作業日誌 |

## 排程機制

### autoInsert.cron.ts（每日台灣時間 00:00）

自動建立當日的 dsvdailytask 記錄：
- 格式：`YYYY/MM/DD`（台灣時間）
- 設定 `date`、`dateDayEnd`、`dateMonthStart` 等系統欄位

### sync.cron.ts（每 30 分鐘）

自動觸發「同步配貨庫存」函式：
1. 找到最新的 dsvdailytask（或今日的）
2. 設 `syncStatus = '同步中'`，記錄 `lastSyncStartAt`
3. 從 DSV FTP 下載庫存檔案
4. 解析並更新 `dsvinventory`（建立/更新每個料件+批號+倉庫的庫存數量）
5. 記錄異動到 `dsvinventoryoperation`
6. 設 `syncStatus = '已完成'`，記錄 `lastSyncEndAt`

### clearFtpBackup.cron.ts（每日台灣時間 23:00）

清理 FTP 上的備份檔案，避免累積過多歷史檔案。

## policy.ts

dsvdailytask 有自己的 policy，主要用於同步排程的狀態控制（防止重複執行）。

## 與 dsvinventory 的關係

dsvdailytask 是 dsvinventory 的更新入口。每次同步會：
1. 比對 FTP 最新庫存與現有 dsvinventory
2. 有差異的記錄 → 更新 dsvinventory（並在 dsvinventoryoperation 留下異動記錄）
3. 新增的批號/料件 → 建立新的 dsvinventory 記錄
4. 已清空的批號 → 將 dsvinventory.amount 設為 0 或封存

## 對 dsvorderdetail.batchPolicy 的影響

batchPolicy 的批號分配依賴 `dsvinventory` 的最新資料。
若庫存同步延遲（syncStatus 長時間為「同步中」或「錯誤」），
批號分配可能使用過時的庫存數據，導致分配結果不準確。

**建議**：修改庫存相關邏輯時，確認 dsvdailytask 的 syncStatus 是正常的。
