# 本機驗收環境（harness）

`scripts/harness.sh` 在 Abyssinian 的 worktree 內起一套完整、可控、不碰共用 dev 的環境。2026-11-23 在 PR #26657 的 head `3e2a58be07` 實測：`up` 全程 35 秒。

## 起了什麼

| 元件 | 怎麼起 | 埠（預設） | 日誌 |
|---|---|---|---|
| 假中台（JavaCat） | `tsx .local-data/accept/fake-world.mts` | 假中台 3192、控制 3193 | `run/fake.log` |
| 內嵌 PostgreSQL ＋ Server | `npm run dev`（`scripts/dev` 一併起內嵌資料庫、建庫、套 migration，再起 `next dev`） | 資料庫 54391、Server 3191 | `run/server.log` |
| Worker | `npm run worker:dev`（`tsx --env-file=.env src/worker/index.ts`，直接跑原始碼，不必建置） | — | `run/worker.log` |

檔案都在 `Abyssinian/.local-data/accept/`（`.gitignore` 已排除）：`fake-javacat-multi.mts`、`fake-world.mts`、`device-peek.mts`、`run/*.log`、`run/*.pid`、`run/fake.ready`。另外寫 `Abyssinian/.env`（也被排除）與內嵌資料庫目錄 `.dev-db/`。

## 為什麼用假中台，而且用 patch

- 驗收要「新增員工看版本變化」「故意讓一筆內容不同」，共用的 dev 中台不能這樣寫；假中台讓異動只發生在自己的行程裡，Worker 的讀取、編譯、發佈走的是**真實程式碼**。
- 假中台取自 repo 內的 `test/integration/support/fake-javacat.ts`，但那份只記得**最後一次登入**的工作階段。Worker 同時有兩個 JavaCat client（機台狀態同步與來源讀取，各自登入），兩個 client 會互相踢掉，所以要改成「記住所有工作階段」並讓埠可指定。這個改動只有 4 處，存成 `scripts/fake-javacat-multi.patch`，`prepare` 時對**現行原檔**套用。
- 原檔改動而 patch 套不上時，`prepare` 會明確失敗（結束碼 5）。處理方式：複製原檔，改 `startFakeJavaCat` 加 `port: number = 0` 參數並傳給 `server.listen`、把 `sessionCookie` 改成 `Set<string>` 並在登入時 `add`、驗證時 `has`，再 `diff -u` 重新產生 patch。這比放一份會過期的複本安全。

## 種子資料與預期結果（`fake-world.mts`）

啟動時全部資料集都是 v1，manifest 共 25 個（共用 11、專屬 14）。

| 門市 | 群組 | 專屬 `pospromotion` | 專屬 `possalonpromotion` | 專屬 `poscoupon` |
|---|---|---|---|---|
| 001 台北信義店 | 北區 | `P-NORTH-01`、`P-NOSOUTH-01`、`P20261101` | （空） | `C-NORTH-01` |
| 002 新北板橋店 | 北區 | 同 001 | （空） | `C-NORTH-01` |
| 003 高雄左營店 | 南區 | `P-SOUTH-01`、`P20261101` | `S-SOUTH-01` | （空） |

- `P-OLD-01` 在 40 天前結束，落在讀取視窗之外，**任何門市都不該有**。`P20261101` 帶 3000 列料件表身，專屬檔約 80 KB，足以測續傳。
- 料件檔 30000 筆（gzip 約 819 KB），由假的 `__file2__` 檔案紀錄指到控制埠下載（紀錄必須有 `name` 欄位，否則 Worker 的料件檔同步會失敗）。
- 機台（`__device__`）：`POS00101`、`POS00102`、`POS00103`（停用）、`POS00111`、`POS00201`、`POS00202`、`POS00301`、純 5 碼的 `00101`、非 POS 命名的 `TEST-DEVICE-A`。各有一筆令牌紀錄。後台同步狀態頁預期：001 有 3 台、002 有 2 台、003 有 1 台，停用的 `POS00103` 不列入，`00101` 與 `TEST-DEVICE-A` 在「找不到所屬門市的機台」。
- 員工（`__user__`）三位，帶 `email`、`otp` 欄位，用來檢查這些欄位**不會**出現在資料集裡。
- 門市 `posstore` 的 `edenredClientSecret` 值帶 `DO-NOT-SHOW`，用來檢查比對報告與後台畫面不顯示密鑰欄位的值（應顯示「（內容不同，值不顯示）」）。

## 時序（`harness.sh` 寫進 `.env` 的縮短值）

| 變數 | 本機值 | 正式預設 | 作用 |
|---|---|---|---|
| `SOURCE_READ_INTERVAL_SECONDS` | 30 | 300 | 增量讀取間隔 |
| `SOURCE_SCHEDULER_TICK_SECONDS` | 5 | 30 | 排程檢查間隔 |
| `DATASET_COMPILE_INTERVAL_SECONDS` | 5 | 60 | 編譯迴圈間隔 |
| `DATASET_QUIET_SECONDS` | 10 | 300 | 緩衝：同一輸入連續這麼久才編譯 |
| `DATASET_MAX_WAIT_SECONDS` | 60 | 1800 | 緩衝最長等待 |
| `DATASET_NOTIFY_SPREAD_SECONDS` | 0 | 300 | 推播分散時間 |
| `DATASET_RETRY_AFTER_SECONDS` | 1 | 10 | 429 的 Retry-After 基準 |
| `SOURCE_AVOID_WINDOWS` | （空） | 夜間兩段 | 排程避開時段 |

實測異動到新版本發佈：改名一筆活動 19 秒、新增員工 33 秒、改名另一筆活動 10 秒。要驗證**正式預設的緩衝行為**（例如「5 分鐘內多次異動合併成一個版本」）時，把這些值改回預設再驗，並在報告註明。

## 控制埠（`http://127.0.0.1:3193`）

| 路徑 | 作用 |
|---|---|
| `POST /ctl/upsert`，本文 `{table, record, lines?, touch?}` | 新增或更新一筆（以 `name` 比對）；日期用 `{"$date":"ISO"}`；`touch:false` 不刷新 `_updatedAt`（模擬「內容變了但 Worker 看不出來」）。通常用 `harness.sh upsert` |
| `GET /ctl/dump?table=<表名>` | 看假中台目前的表頭與表身 |
| `GET /ctl/count` | 假中台被查詢的次數 |

## 重開環境：要從乾淨狀態開始

`down` 只停行程，**不清資料**。如果 `down` 之後直接 `up`，內嵌資料庫與本機物件儲存還留著上次的來源快取與各資料集版本，而假中台每次啟動都重新灌種子，兩邊就不一致：

- 實測（2026-11-23）：重開後 manifest 仍是上次的 `__user__` v2（4 筆，含驗收時新增的 U004），但假中台的種子只有 3 位員工。
- 原因：Worker 的增量讀取只看 `_updatedAt` 之後的變動，看不出「被還原的值」與刪除；要等每日全量校驗才會對齊。

所以 `up` 看到殘留的 `.dev-db` 或 `.local-data/objects` 會拒絕（結束碼 8）。正確的重開做法是 `bash "$H" clean`（含 `down`）再 `up`；只有確定要保留資料時才用 `ABY_KEEP_DATA=1`，並在報告註明。

**乾淨啟動的基準可以重現**：種子不變時，門市 001 的 manifest ETag 前 8 碼固定是 `016bdfcc`（兩次獨立啟動實測相同），25 個資料集全是 v1，可當作「環境就緒且乾淨」的檢查；改了 `fake-world.mts` 的種子這個值就會不同。

## 這套環境驗不到什麼

- **真實 FCM 推播**：沒有金鑰，推播只寫日誌（`dataset_push_log_only`）。
- **真實 S3**：物件儲存用本機檔案（`OBJECT_STORE_DRIVER=file`），S3 的 Range、條件寫入、角色權限驗不到。
- **真實令牌與機台名稱**：令牌用 `.env` 的本機假密鑰簽；真實 `__device__` 名稱是否都符合「POS 加 5 碼」要在 dev 對照。
- **真實資料量**：種子是 3 間門市、3 萬筆料件，編譯記憶體與耗時不代表真環境。
- **多實例與 ALB／WAF 行為**。
- `npm run dev` 是開發模式，不是 `next build` 後的正式模式；標頭與壓縮行為如要驗，另外 `npm run build` 後用 `next start`（會印 standalone 警告，仍可服務）。

## 出錯時

| 症狀 | 原因與處理 |
|---|---|
| `prepare` 結束碼 3 | 埠被占用。看列出的 pid、cwd，**不要殺**；換 `ABY_*_PORT` 或請使用者處理 |
| `prepare` 結束碼 4 | 已有**不是本腳本產生的** `.env`（本腳本寫的 `.env` 第一行有標記，會直接覆蓋）。確認可丟棄後 `ABY_FORCE_ENV=1` |
| `prepare` 結束碼 5 | 沒有 `fake-javacat.ts`，或 patch 套不上（見上） |
| `up` 結束碼 8 | 發現上次留下的 `.dev-db` 或 `.local-data/objects`，見下一節「重開環境」。先 `clean` |
| 假中台 120 秒沒就緒 | 看 `run/fake.log`；料件檔 3 萬筆的產生需要幾秒 |
| Server 240 秒沒就緒 | 看 `run/server.log`；第一次要建內嵌資料庫與套 migration；Prisma client 不存在時會自動 `prisma generate` |
| 頁面停在「載入中…」 | 你用了 `127.0.0.1`，改 `localhost` |
| 後台比對一直「比對中…」 | 畫面輪詢約 15 秒；先打 `/api/v1/admin/store-compare/latest` 確認 |
| Worker 日誌的「來源讀取」事件 `status` 不是 `ok` | 看同一行的 `errorSummary`。曾遇到的是假的 `__file2__` 紀錄缺 `name` 欄位，料件檔同步失敗；補上 `name` 後用 `POST /api/v1/admin/data-source/read-now` 立即讀取（202） |
| `down` 後仍有埠被占用 | 腳本只處理 cwd 在本專案目錄底下的行程；其餘會列出但不動 |

## 驗證的 shell 注意事項

- zsh 不對未引號變數斷詞，`P="a b"; $P` 會把整串當成指令名稱；重複使用的指令寫成函式。
- zsh 未引號的 `*`（例如 `--include=*.ts`）沒有符合時整條指令失敗，要加引號。
- 變數名後面緊接全形字元（`$VAR）`）在 bash 會被吃進變數名，`harness.sh` 內的訊息一律寫 `${VAR}`。
