# 灰度與更新時序：發佈前後要懂的機制

這份是 `SKILL.md` 各道把關的依據。原始碼位置都相對於 `OldEnglish/POSAgentDotNet/`；若日後程式改版，以原始碼為準。

## 目錄

- [S3 上有什麼](#s3-上有什麼)
- [manifest 結構](#manifest-結構)
- [機台怎麼判定要不要更新](#機台怎麼判定要不要更新)
- [為什麼換回 manifest 的時機重要](#為什麼換回-manifest-的時機重要)
- [強制更新與退版](#強制更新與退版)
- [機台沒有跳更新時的檢查清單](#機台沒有跳更新時的檢查清單)

## S3 上有什麼

bucket `posagentdotnet-updates.wonderpet.asia`（ap-northeast-1，私有；門市機用唯讀 IAM 金鑰讀取）：

| 路徑 | 性質 |
|---|---|
| `manifest.json` | 單一「最新版指標」。每次發佈覆寫，沒有歷史（bucket 沒開版本控制） |
| `packages/POSAgentDotNet-<版本>.zip` | 更新包。一經上傳不可變；同版號不同內容會被 `publish-release.sh` 擋下 |

所以線上 manifest 的版本低於 `packages/` 內最高版本，是模式 A 試裝後換回的正常結果，不是異常。

## manifest 結構

```json
{
  "schemaVersion": 1,
  "version": "1.3.0",
  "releasedAt": "2026-11-26T11:21:52+08:00",
  "notes": "門市看得懂的更新說明",
  "package": { "key": "packages/POSAgentDotNet-1.3.0.zip", "sha256": "…", "sizeBytes": 1969160 },
  "rollout": { "stores": null, "percent": 100 },
  "forceAfter": null
}
```

- `version`：必須恰好三段 `x.y.z`。機台替換後的健檢是拿它比對服務回報的版本（永遠三段），不是三段就會讓好版本健檢必敗。
- `rollout.stores`：`null` 代表全部門市；陣列代表白名單，只填門市代號。
- `rollout.percent`：0 到 100。
- `forceAfter`：`null` 代表純人工；有值而且已過期，機台抓到後會自動套用（交易閘門仍必過）。必須帶時區位移。

## 機台怎麼判定要不要更新

`src/POSAgentDotNet.Update/Engine/UpdateManager.cs` 的 `RunCheckAsync`，每一輪依序判斷：

1. `manifest.version <= 機台現版` → **已是最新**（所以不會降版）。
2. 該版本在機台的 `bad-versions.json` → 跳過（更新失敗被回滾過的版本，永久不再下載）。
3. `RolloutEvaluator.IsEligible`（`src/POSAgentDotNet.Update/Rollout/RolloutEvaluator.cs`）：
   - 機台 `Update:StoreId` 是空的 → 只有 `stores == null` 且 `percent == 100` 才符合；任何灰度規則一律跳過。
   - `stores` 不是 null 且不含本機 `StoreId`（不分大小寫）→ 跳過。
   - `SHA-256(storeId + version)` 取前 4 bytes（big-endian）除以 100 的餘數若 ≥ `percent` → 跳過。
4. 通過後下載 zip、驗 SHA-256、解壓到 staging，狀態變 **Ready**。
5. Tray 每 15 秒輪詢 `GET /update/status`，看到 Ready 就跳「有新版」對話框；店員按「要更新」→ `POST /update/apply` → 通過交易閘門 → 進入 draining → Updater 停服務、備份、覆蓋、重啟 → 60 秒內健檢版本。失敗自動回滾並把版本寫進壞版本名單。

檢查週期是每 60 分鐘加上 ±10 分鐘的隨機抖動（`Update:CheckIntervalMinutes`、`CheckJitterMinutes`）。端點：`GET /update/status`、`POST /update/check`（回 202，觸發背景檢查）、`POST /update/apply`、`POST /update/postpone`，預設埠 9001。

`/update/status` 的狀態快照（`UpdateStatusSnapshot`）有 `currentVersion`、`state`、`availableVersion`、`notes`、`readyToApply`、`stagedFolder`、`forceAfter`、`lastCheckAt`、`lastError`，**沒有 StoreId**，所以無法遠端驗證門市代號。

## 為什麼換回 manifest 的時機重要

`RunCheckAsync` 每一輪都用「當下的 manifest」重新評估，並以 `Conclude` 覆寫整個狀態快照：

- 機台已經 Ready、但店員還沒按「要更新」時，如果 manifest 已被換回舊版，下一輪檢查會得到「版本不比現版新」，狀態被改寫成 `UpToDate`，`availableVersion`、`stagedFolder` 都被清掉，更新入口就消失了（staging 資料夾還在，但狀態不見了）。
- 一旦進入 **Applying**，`Conclude` 會直接放棄該輪結論（Applying 是黏性終態），替換照常進行，不受 manifest 影響。

所以換回的最安全時點是「機台 `currentVersion` 已是新版」：此後 manifest 版本一定 ≤ 機台現版，永遠只會是 `UpToDate`。其次是店員已按下更新、進入替換之後。想加快就對機台打 `POST /update/check`，不必等一小時。

專案負責人說明：灰度發佈有一個 bug，新展店安裝較舊版本時會無法更新，暫時解法是發佈完把 manifest 換回原版。這是專案負責人的說明，根因沒有在原始碼驗證。

## 強制更新與退版

- 有 `forceAfter` 且已到期：有 Tray 在線（60 秒內輪詢過）時先倒數 60 秒，可延後一次 5 分鐘；沒有 Tray 就直接套用；交易閘門仍必過。試裝不要設。
- **退版不能重發舊版號**：版本比較是「manifest ≤ 現版就不更新」。做法是 checkout 舊程式碼、以**更高的版號**重新打包，再用 `force-release.sh` 讓各門市自動套用。壞版本名單優先於 force，已被寫進 `bad-versions.json` 的版本不會再被下載，所以退版一定要換新版號。

## 機台沒有跳更新時的檢查清單

1. 還沒到下一輪檢查？打 `POST /update/check`，再看 `lastCheckAt`、`lastError`。
2. `Update:StoreId` 是空的，或與白名單不符？啟動 log 在 StoreId 空白時會警告「本機只會收到全量推送、不參加灰度發布」。`Update:StoreId` 是可以熱套用的設定鍵，改了不必重啟服務。
3. 新版是否不比機台現版新？
4. 該版本是否已在機台的壞版本名單？
5. 機台是否缺 ASP.NET Core 10 或 .NET Desktop 10 執行期？（更新後起不來會自動回滾並列入壞版本。）
6. 機台的 `Update:Enabled` 是否為 true？`false` 時只掛精簡版 `/update/status`，不會檢查更新。
