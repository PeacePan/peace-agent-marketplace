# RD-8484（B4 門市客制與專屬檔發佈）驗收手冊

卡片：`[Abyssinian] B4 門市客制與專屬檔發佈`，父系 RD-8489（POS-S）。這張卡分階段交付，驗收前先確認這次驗的 PR 涵蓋哪一段：

| PR | 內容 | 狀態（2026-11-23） |
|---|---|---|
| #26656（PR-0） | 封存偵測，base 為 master | open，已非 draft；head `c3e7984ca8`（`gh pr view` 實測） |
| #26657（PR-1） | 資料集編譯與發佈、機台端點、推播、比對、後台、驗收腳本，base 為 PR-0 的分支 | open、draft；head `3e2a58be07`；`mergeable` 為 `CONFLICTING`（`gh pr view` 實測） |
| PR-2 | **門市客制**（價格客制、活動客制、白名單、後台編輯頁、開放旗標） | 依 2026-11-19 的記錄尚未開工：計畫要等 PR-1 介面落定，且開工前要先交白名單逐欄清單給使用者覆核。驗收時以 `gh pr list --search "RD-8484"` 與程式碼為準（4～7 條的實際依據是 Step 3 的功能存在檢查，不是這張表） |

> 結果欄是 **PR-1 head `3e2a58be07`** 的實跑結果。換了 head 或 PR-2 出來後要重跑，不能沿用。

## 前置

1. 依 SKILL 的 Step 0a-2、0b 建 worktree 並 `bash "$H" up`。
2. 在 `Abyssinian/` 目錄定義兩個函式（zsh 不對未引號變數斷詞，不能寫成字串變數）：
   ```bash
   peek() { node_modules/.bin/tsx .local-data/accept/device-peek.mts --base-url http://localhost:3191 "$@"; }
   sim()  { npm run machine:sim --silent -- --base-url http://localhost:3191 "$@"; }
   ```
3. **基準快照**（AC8 要用）：`peek --store 001 manifest`，記下 `pospromotion`、`__user__` 的版本、大小、sha256；`peek --store 001 dataset pospromotion` 也記下。

## 建議執行順序

條件之間會互相干擾（改活動會讓版本升級），照這個順序做最省事：

| 順序 | 做什麼 | 對應條件 |
|---|---|---|
| 1 | 基準 manifest；`sim --store 001 --sign-local-device POS00101` 完整同步 | 1、3 |
| 2 | 逐門市 `peek --store <店> dataset pospromotion／possalonpromotion／poscoupon`，核對活動名稱 | 1 |
| 3 | Playwright：門市比對頁輸入 001、開始比對（預期全部一致），截圖 | 1、2 |
| 4 | **造差異**：`upsert pospromotion` 改名 `P-NORTH-01`，**立刻**對 001 觸發比對（API 或畫面） | 2 |
| 5 | 輪詢 `peek --store 001 manifest` 到 `pospromotion` 升 v2；`peek … dataset pospromotion --version 1` 比對 sha256；`--version 99` 預期 410 | 8 |
| 6 | Playwright：資料集同步頁，同步前截圖；`sim` 001 再同步一次；`sim --store 002 --sign-local-device POS00201 --interrupt-after 50000`；重新載入頁面開「看機台」截圖 | 3、9 |
| 7 | `upsert __user__` 新增員工；輪詢到 `__user__` 升 v2；`peek shared-diff 001,002,003`；員工檔不含機密欄位；同步頁截圖 | 10 前半 |
| 8 | `upsert pospromotion` 改名只有 003 適用的 `P-SOUTH-01`；確認只有 003 的專屬版本升版、001／002 的 manifest ETag 與共用條目不變 | 10 後半的替代驗證 |
| 9 | `npm run probe:dataset -- --base-url http://localhost:3191 --stores 001,002 --sign-local --machines 4 --max-seconds 60` | 11 |
| 10 | 尚未實作的證據：選單、首頁文字、`/api/v1/admin/settings`、`src/app/api/v1/admin` 清單、Prisma schema grep | 4、5、6、7 |
| 11 | 單元與整合測試（限時執行器、背景） | 旁證 |

## 逐條條件

### 1. 專屬檔只含該門市適用的活動（工程回報，附比對紀錄，PM 認可）

- **做法**：順序 1～3。「比對紀錄」＝門市比對頁的一致報告。
- **預期**：001／002 的 `pospromotion` 是 `P-NORTH-01`、`P-NOSOUTH-01`、`P20261101`；003 是 `P-SOUTH-01`、`P20261101`；`P-OLD-01` 誰都沒有；`possalonpromotion` 只有 003、`poscoupon` 只有 001／002。
- **結果 ✅（待 PM 認可）**：預期全部相符；`sim` 25 個資料集 sha256 全相符；比對報告 001 共 30 筆一致。證據等級：實機·本機假中台。

### 2. 後台比對頁看到差異，故意讓一筆不同會被列出

- **做法**：順序 3～4，**用「門市比對」頁，不是「差異報告」頁**。造差異要在 Worker 讀到之前比對。
- **預期**：差異清單列出 `P-NORTH-01` 的「促銷名稱」，專屬檔是舊名、機台現在會拿到的是新名，畫面沒有表名或欄位代碼。
- **結果 ✅**：報告 29 筆一致、1 筆內容不同，欄位「促銷名稱」兩邊的值正確；截圖 `RD-8484-c2-store-compare-001-different-expanded.png`。

### 3. 發佈新版本後，模擬機台收到通知並套用、回報版本，後台顯示已套用最新版本與回報時間（工程回報，附截圖，PM 認可）

- **做法**：順序 5～6。通知看 Worker 日誌的 `dataset_push_log_only`。
- **預期**：POS00101 套用 v2、回報 204；同步頁顯示「已套用最新版本」與回報時間；同門市還沒回報的機台標「尚未回報」；推播只發給受影響門市。
- **結果 ⚠️**：
  - ✅ 套用與回報（`sim` 成功、manifest 再取得 304）；
  - ✅ 後台：POS00101「已套用最新版本」、最近回報 2026/11/23 16:23:47，POS00102／POS00111 正確標「尚未回報」；
  - ✅ 推播目標：日誌顯示只有 001、002 兩間收到 `datasetManifestUpdated`（`audience: changed_stores`），`manifestEtag` 與同時間 manifest 的 ETag 一致；
  - ⚠️ **「機台收到通知」只驗到日誌層**：本機沒有 FCM 金鑰，推播不會真的送出（後台標籤「尚未設定（只寫日誌）」）。真實推播要在 dev 取得 `wonderpetpos` 專案的服務帳號金鑰後驗（`DEPLOY.md` 有「金鑰到位後必驗清單」）。

### 4. 門市客制：折扣值改成與全公司不同並儲存，其他門市仍是全公司版本

- **結果 ⚠️ 尚未實作**。證據：選單只有 7 項（首頁、資料來源、差異報告、資料集同步、門市比對、稽核紀錄、系統設定）；首頁寫「門市客制…會隨後續開發陸續加入」；後台 API 只有 `audit-logs`、`data-source`、`dataset-sync`、`me`、`settings`、`store-compare`；Prisma schema 沒有 `item_store_price`、`activity_store_override`；`itemstoreprice` 資料集只是空殼（0 筆）。權限常數 `edit_store_price`、`edit_store_activity` 已定義但沒有入口。

### 5. 不允許改活動對象或料件篩選、不允許對全公司共用上限或會員層級活動客制，並顯示原因

- **結果 ⚠️ 尚未實作**（同 4；合法性檢查與白名單屬 PR-2）。

### 6. 為某門市某料件設定會員價與生效期間，列表顯示，其他門市不受影響

- **結果 ⚠️ 尚未實作**（同 4）。

### 7. 客制尚未開放前後台看不到編輯入口，開放之後才看得到

- **結果 ⚠️ 尚未實作**：現況確實「看不到入口」，但那是因為功能還沒做，不具驗證意義；「系統設定」只有 `dataset_notifier_mode`，沒有開放旗標，無法驗「開放之後才看得到」。

### 8. 舊的資料集版本內容與當時發佈一致，之後的異動不影響它（工程回報，附紀錄，PM 認可）

- **做法**：順序 1（基準）與 5。**必須在造異動前記下 sha256**。
- **預期**：`--version 1` 下載的大小與 sha256 等於基準；v2 是不同內容；不存在的版本回 410。
- **結果 ✅（待 PM 認可）**：001 的 `pospromotion` v1 仍是 82365 位元組、sha256 前 8 碼 `c8d0a8b3`（與發佈當時一致）；v2 是 82445、`e2c6fb40`；`version=99` 回 410；003 不受影響。

### 9. 下載到一半中斷後從中斷處續傳並套用，後台顯示最新版本；機台全程沒有直接存取雲端儲存空間、沒有拿到下載網址（工程回報，附紀錄，PM 認可）

- **做法**：順序 6，`--interrupt-after 50000`。
- **預期**：超過 50000 位元組的資料集（`item`、`pospromotion`）「續傳：是」、sha256 相符、下載總位元組等於整份大小（沒有重下載）、「從頭重來 0 次」；同步頁顯示該門市已套用；「全程是否出現任何儲存空間網址：否」。
- **結果 ✅（待 PM 認可）**：002／POS00201 續傳 2 次、從頭重來 0 次、全部 sha256 相符、下載 907531 位元組、回報 204、再取 manifest 304；同步頁 002 顯示「已套用 1」；腳本檢查所有回應標頭與 manifest 本文，沒有儲存空間網址。
- **本機驗不到的**：「雲端儲存空間私有」是基礎設施屬性（本機用檔案儲存），真實 S3 的 Range 行為與 bucket 封鎖公開存取要在 dev 驗（`DEPLOY.md` 的「待實測」與驗收方式表）。

### 10. 新增員工後所有門市共用同一份員工資料集；只改某門市的客制價格後，其他門市共用資料集版本不變，只有該門市專屬資料集版本更新

- **做法**：順序 7～8。
- **結果 ⚠️**：
  - ✅ 前半：新增 U004 後 33 秒，三間門市的 `__user__` 都是 v2、sha256 `d8af6efa` 逐字相同（`peek shared-diff` 三間都「逐字相同」）；各門市專屬版本沒動；員工檔 4 筆，不含 `email`／`otp`／`totpSecret`；同步頁共用資料集「使用者」第 2 版、三間門市「最近發佈」同時間。
  - ⚠️ 後半：「客制價格」尚未實作（同 4）。**補充證據（不改變判定）**：改名只有 003 適用的 `P-SOUTH-01`，只有 003 的 `pospromotion` 升 v2、manifest ETag 變了，001／002 的 ETag 與所有共用條目完全沒動，證明「只更新受影響門市的專屬檔」的架構性質成立；PR-2 完成後要用真正的客制價格重驗。

### 11. staging、1000 台同時下載、離線交易收件延遲符合 T1 目標（工程回報，附紀錄，PM 認可）

- **結果 ⚠️ 本機無法判定**：`probe:dataset` 本機 4 台全部完成（最慢 1.1 秒），且**正確回報「總判定：無法判定」、結束碼 3**（規模不足、沒量離線交易）。真正的判定需要 staging（S2＝RD-8510，待辦）與離線交易收件（T1＝RD-8485，待辦；2026-11-19 的記錄是收件路由還是殼、回 501，本次未再測）。

## 自動化測試（旁證）

| 類型 | 結果（head `3e2a58be07`） |
|---|---|
| `npm run test:unit` | 85 個檔案、1874 個測試全過，7.5 秒 |
| `npm run test:integration` | 50 個檔案、1143 個測試全過，156 秒（CI 不跑這一項；`DEPLOY.md` 要求合併前本機跑並寫進 PR 說明） |

## 需要真環境或使用者協助才能驗的事（`DEPLOY.md` 已列）

- 真實 FCM 推播（金鑰）、`validate-only`、換憑證；
- 真實 S3 的 Range、條件寫入、角色權限；
- 真實令牌與 `__device__` 名稱是否都是「POS＋收銀機編號」（`DEPLOY.md`「機台名稱與門市」）；
- 真實資料量下的編譯記憶體與耗時；
- 1000 台壓測（staging）。

## 驗收時的其他觀察（不影響判定）

- PR #26657 的 `mergeable` 為 `CONFLICTING`（base 為 PR-0 的分支）。
- 門市比對頁在 Worker 完成（約 2 秒）後，畫面約 15 秒才更新。
- 稽核紀錄頁顯示原始動作代碼 `store_compare.run` 與 JSON。
