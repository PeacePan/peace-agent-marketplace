# 後台頁面與 Playwright 操作

後台在 `/admin/*`，選單依權限顯示（`src/app/admin/_lib/menu.ts`）。**本機 `ADMIN_IDENTITY_MODE=open` 免登入、全部權限**，頂端狀態列顯示「dev 環境」與「開放模式」。2026-11-23 於 PR #26657 head `3e2a58be07` 逐頁實測。

## 頁面對照

| 選單 | 路徑 | 用途 | 主要 API（`/api/v1/admin/…`） | 驗收時什麼條件會用到 |
|---|---|---|---|---|
| 首頁 | `/admin` | 身分、權限、環境；末尾一句「門市客制、離線交易監控等功能會隨後續開發陸續加入」 | `me` | 判斷某功能是否已有入口（尚未實作的證據之一） |
| 資料來源 | `/admin/data-source` | 中台連線狀態、各類來源資料（活動主檔 14 類＋共用資料）的筆數、最後讀取、最近變動、讀取失敗；「立即讀取」按鈕 | `data-source/summary`、`changes`、`failures`、`read-now` | 來源讀取是否反映異動；異動後「最近變動」會更新 |
| 差異報告 | `/admin/diff-report` | **來源暫存 vs 中台現況**（B1 的比對），沒有選門市的功能 | `data-source/diff-report/latest`、`diff-run` | 來源讀取正確性；**不是**「專屬檔 vs 機台現況」 |
| 資料集同步 | `/admin/dataset-sync` | 共用資料集的版本與「至少一台已套用」的門市數；各門市機台數、已套用、落後或待同步、尚未回報、最近發佈；「看機台」抽屜：各資料集目前版本、每台機台的回報狀態與時間；「找不到所屬門市的機台」；頂端推播通知狀態 | `dataset-sync/summary`、`dataset-sync/stores/{storeNo}` | 機台是否套用最新版本、回報時間、共用資料集版本、推播狀態 |
| 門市比對 | `/admin/store-compare` | **專屬檔 vs 機台現在會拿到的內容**：輸入 3 碼門市編號，「開始比對」；結果有六種分類（內容不同、專屬檔缺少、專屬檔多出、兩種預期差異、一致）與差異清單，可「展開對照」看欄位兩邊的值 | `store-compare/latest?storeNo=`、`store-compare/run` | 「在後台比對報告頁選一間門市…」這類條件 |
| 稽核紀錄 | `/admin/audit-logs` | 每次寫入操作的時間、操作人、來源位址、動作、變更內容 | `audit-logs` | 驗證操作有留紀錄；本機操作人是「未登入」 |
| 系統設定 | `/admin/settings` | 目前只有 `dataset_notifier_mode`（推播通知器模式）一個設定 | `settings` | 開放旗標類條件：目前**沒有**客制開放旗標 |

## 判定時的對照提醒

- 「比對報告頁」「選一間門市」→ **門市比對**，不是差異報告。
- 後台畫面給非工程人員看：**不應出現資料表名或欄位代碼**（例如 `pospromotion`、`ALLOW`）；顯示名稱取自中台的表格定義（種子資料已灌 `__table__`）。驗收時順手檢查畫面有沒有代碼外露；機密欄位（`edenredClientSecret`）只能顯示「（內容不同，值不顯示）」，**值本身不得出現在畫面、API 回應或報告**。
- 同步狀態頁只列**啟用中**的機台：停用機台不計入機台數，也不在「找不到所屬門市」區，不是漏掉。
- 機台名稱不是「POS 加 5 碼」的（`00101`、`TEST-DEVICE-A`）會被放進「找不到所屬門市的機台」，這是預期。

## 常用的 Playwright 流程

```text
1. browser_navigate  http://localhost:3191/admin/store-compare        （localhost，不是 127.0.0.1）
2. browser_find      text="門市編號"        → 取得輸入框 ref
3. browser_type      target=<ref> text="001"
4. browser_find      text="開始比對"        → 輸入後按鈕狀態變了，要重新取 ref
5. browser_click     target=<ref>
6. 先 GET /api/v1/admin/store-compare/latest?storeNo=001 確認報告已產生（約 2 秒），畫面約 15 秒才更新
7. browser_find      regex="共比對|其中 \d+ 筆需要追查"
8. browser_find      text="展開對照" → browser_click → browser_take_screenshot（fullPage）
```

- 讀畫面一律先 `browser_find`（比整份 snapshot 便宜），要看整頁再 `browser_snapshot`。
- 量畫面更新的延遲或做多步驟等待時，用 `browser_evaluate` 在頁面內輪詢，比重複呼叫工具準確（2026-11-23 用它量到「比對完成後畫面約 14.5 秒才更新」）。
- 抽屜（`dialog`）裡的內容超出視窗時，對該元素 `browser_evaluate` 執行 `(el) => el.scrollIntoView({block:'center'})` 再截圖；一般的 `scrollTop` 找不到可捲動的容器。
- 版面類條件：窄版（例如 390 寬）與桌面版（1280 寬）各拍一次（`browser_resize`）。卡片沒寫的版面要求不當條件判定。

## 其他觀察（驗收時可順便記錄，不影響判定）

- 「稽核紀錄」頁直接顯示 `store_compare.run` 與 `{"requestId":"3"}` 這類原始動作代碼與 JSON；是否要白話化由使用者判斷。
- Console：在門市比對頁用 `localhost` 開，只有 `favicon.ico` 404 一個錯誤；用 `127.0.0.1` 開則多出 HMR WebSocket 握手失敗，且頁面停在「載入中…」。其他頁面的 Console 條目我沒有逐一檢查，驗收時請自己用 `browser_console_messages` 看一次。
