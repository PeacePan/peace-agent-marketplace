# DSV 系統表格總覽

## 六個表格用途

| 表格 | 顯示名稱 | 用途 |
|-----|---------|-----|
| `dsvorder` | DSV 出貨單 | 每張調撥單對應一張出貨單，記錄出貨主資訊與狀態 |
| `dsvorderdetail` | DSV 出貨明細 | 每筆調撥明細對應一筆出貨明細，記錄料件/批號/數量 |
| `dsvshipment` | DSV 出貨貨況 | DSV 回傳的配送進度，記錄每批貨的實際出貨狀態 |
| `dsvdailytask` | DSV 每日配貨檔 | 每日建立一筆，管理 DSV 庫存同步排程與紀錄 |
| `dsvinventory` | DSV 配貨庫存 | 從 DSV FTP 同步的總倉實際庫存（含批號/效期/數量） |
| `dsvinventoryoperation` | DSV 庫存異動明細 | 記錄 dsvinventory 每次異動的前後數量（稽核用） |

## 表格關聯圖

```
TRANSFER_ORDER
    │ _id = dsvorder.name（關鍵！不是 TO 開頭的業務單號）
    │
    ▼
DSV_ORDER（出貨單）
    │ name = dsvorder.name
    │ transferOrderName = transferorder.name（業務單號）
    │
    ├──────────────────────────┐
    │                          │
    ▼                          ▼
DSV_ORDER_DETAIL（出貨明細）  DSV_SHIPMENT（貨況）
    │ dsvOrderName              │ dsvOrderName
    │ transferOrderItemId        │ transferOrderName（業務單號）
    │                          │
    ▼                          ▼
  ITEM（料件）               ITEM（料件）
  LOCATION（倉庫）

DSV_DAILY_TASK（每日配貨）
    │
    ├──→ DSV_INVENTORY（配貨庫存）[外部表身，W17R01/W17R05 的當日/當月]
    ├──→ DSV_ORDER_DETAIL [外部表身，當日/當月建立]
    └──→ TRANSFER_ORDER [外部表身，WH/WHAT，當日/當月建立]

DSV_INVENTORY
    │
    └──→ DSV_INVENTORY_OPERATION（異動記錄，稽核用）
```

## 關鍵外鍵對應關係

| 欄位 | 所在表格 | 對應表格 | 說明 |
|-----|---------|---------|-----|
| `name` | dsvorder | TRANSFER_ORDER._id | **用 _id 當 name**，非業務單號 |
| `transferOrderName` | dsvorder, dsvshipment | TRANSFER_ORDER.name | 業務單號（`TO` 前綴） |
| `dsvOrderName` | dsvorderdetail, dsvshipment | dsvorder.name | 關聯出貨單 |
| `transferOrderItemId` | dsvorderdetail, dsvshipment | transferorder.lines.items._id | 關聯調撥明細表身列 |
| `inventoryName` | dsvinventoryoperation | dsvinventory.name | 關聯配貨庫存 |

## 各表格 Hooks 摘要

| 表格 | Hook | 類型 | 位置 |
|-----|-----|-----|-----|
| dsvorder | policy.ts | POLICY | scripts/dsvorder/policy.ts |
| dsvorderdetail | batchPolicy.ts | BATCH_POLICY | scripts/dsvorderdetail/batchPolicy.ts |
| dsvdailytask | policy.ts | POLICY | scripts/dsvdailytask/policy.ts |

## Scripts 目錄結構

```
NorwegianForest/tables/dsv/scripts/
├── dsvorder/
│   ├── policy.ts            — 出貨單政策（庫存計算、狀態更新）
│   ├── shipping.ts          — 出貨拋單邏輯（生成 CSV）
│   ├── shippingUpload.ts    — 上傳 FTP（Retry: 2）
│   ├── shippingReset.ts     — 重置拋單（DEV 用）
│   ├── updateStatus.ts      — 更新訂單狀態
│   ├── updateStatus.cron.ts — 每 5 分鐘排程
│   ├── cancel.ts            — 取消拋單
│   └── complete.ts          — 驗收完成（無配送紀錄時）
├── dsvorderdetail/
│   └── batchPolicy.ts       — 批號/效期回填、數量同步
├── dsvshipment/
│   ├── sync.ts              — 同步貨況邏輯
│   └── sync.cron.ts         — 每 10 分鐘排程
└── dsvdailytask/
    ├── policy.ts            — 配貨政策
    ├── sync.ts              — 同步庫存邏輯
    ├── sync.cron.ts         — 每 30 分鐘排程
    ├── autoInsert.cron.ts   — 每日 00:00 建立記錄
    └── clearFtpBackup.cron.ts — 每日 23:00 清理 FTP 備份
```
