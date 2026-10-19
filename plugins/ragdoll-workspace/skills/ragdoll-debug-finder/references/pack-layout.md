# 回報包導覽

回報包由門市的 Ragdoll 產生：收集本機檔案與兩個 SQLite 快照 → 打包成 `issue-report-<日期>-<時間>-<門市>-<機台>.tar.gz` → 上傳中台 `__file2__`（category 為 `POS問題回報`）→ 通知 Google Chat。產生流程的完整說明見 wiki 的 `ragdoll/issue-report.md`。

## 檔案一覽

| 檔案 | 內容 | 注意 |
|---|---|---|
| `metadata.json` | `eventId`、`saler`、`storeName`、`configName`、`targetEnv`、`posVersion`、`capturedAt`、`submittedAt`、`collectErrors` | 時間是 UTC ISO（結尾 `Z`），加 8 小時才是台灣時間；`collectErrors` 有值代表某一段收集失敗 |
| `description.txt` | 門市原話 | 報告中原文引用 |
| `screenshot.png` | 按下回報當下的主視窗畫面 | 在回報對話框開啟前截圖；用 Read 直接看圖 |
| `config.ini` | Ragdoll 自己的設定 | 不是刷卡機 ECR 的設定 |
| `ragdoll-store.json` | 本機設定與時戳：`POS_STORE_NAME`、`POS_CONFIG_NAME`、`CREDIT_CARD_READER_TYPE`、`LAST_*_AT`（最後一次同步或計算的毫秒時戳）、`CHECKOUT_SUSPENSION` | 用 `LAST_*_AT` 判斷同步是否落後 |
| `storeSnapshot.json` | 送出當下前端各 Zustand store 的狀態（購物車、會員、付款…），已遮罩 `mobile` | 約 2 MB，以 `python3 -I` 載入後依 key 取用，不要整份 `cat` |
| `offline-mutable.snapshot.db` | 本機交易：`offline_sale` 與其表身、`offline_return*`、`offline_customer_order*`、`issue_invoice`、`offline_pos_report` | 只含這一台機台；含明文個資 |
| `offline-readonly.snapshot.db` | 同步下來的主檔：`item`、`pos_promotion`、`pos_coupon`、`service_item`、`package_service_item`、`pos_pilot`、`user`… | 時間欄位語意見下方 |
| `logs/<範圍>/<日期>.log` | 近約 3 天的日誌。範圍：`auto-update`、`credit-card`、`error`、`invoice`、`issue-report`、`main`、`promotion-price`、`push-notification`、`scheduler`、`sync`、`tray`、`upload` | 格式 `[YYYY-MM-DD HH:mm:ss] [level]  訊息`；多行錯誤只有第一行有時戳 |
| `ecr/` | 台新刷卡機 `ECR.exe` 的資料夾（`log/`、`transmitted/`、`CS_ecr.dat`） | 只有刷卡機問題才用，改走 `ragdoll-card-reader-triage`；不要執行 `ECR.exe` |

## 讀 SQLite

一律唯讀開啟。表身子表命名為 `<主表>_lines_<表身名>`，以 `<主表>_name` 欄位關聯主表的 `name`（例如 `offline_sale_lines_month_cards.offline_sale_name` → `offline_sale.name`）。欄位是 snake_case，時間是毫秒時戳。

```bash
sqlite3 -readonly "$WORK/pack/offline-mutable.snapshot.db" ".schema offline_sale"
sqlite3 -readonly -header "$WORK/pack/offline-mutable.snapshot.db" \
  "select name, datetime(created_at/1000,'unixepoch','+8 hours') as 建立時間 from offline_sale order by created_at desc limit 5"
```

## 時間的三種寫法

| 來源 | 寫法 | 換算 |
|---|---|---|
| `metadata.json` | UTC ISO 字串 | +8 小時 |
| SQLite `created_at`、`updated_at` | UTC 毫秒時戳 | `datetime(x/1000,'unixepoch','+8 hours')` |
| `logs/**/*.log` | 機台本地時間 | 已是台灣時間，不用換算 |

**唯讀快照的時間語意不一致**：`offline-readonly.snapshot.db` 的主表（如 `service_item`）`created_at`／`updated_at` 是**中台記錄的時間**，舊資料會顯示好幾年前；lines 子表（如 `service_item_lines_tasks`）的 `created_at` 才是**本地寫入時間**。要判斷「這台機台何時拿到這筆主檔」，用 lines 子表的時間，再對 `logs/sync/<日期>.log` 的「開始同步」時間點交叉比對。

## 個資

`offline-*.snapshot.db` 與 `logs/` 含明文會員手機、姓名、發票與交易明細（回報流程刻意不遮罩，讓 RD 能診斷資料層問題）。分析時只輸出單號、編號、筆數與時間；不要整表 `select *` 印出，也不要把個資貼進報告、Jira 或 Chat。
