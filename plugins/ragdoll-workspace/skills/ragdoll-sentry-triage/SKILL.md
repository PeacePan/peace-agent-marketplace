---
name: ragdoll-sentry-triage
description: Ragdoll（Sentry 專案 ragdoll-local-pos）的錯誤分流與配額檢查——先查額度與被丟棄的事件、依事件數排名、用 storeName／configName 找單機洪水、把錯誤分成連線類／顧客端預期內／應處理三類，並對照 van 的 /proxy/sentry 狀態碼與 Jira 巡查卡。內含 org／project／Jira 常數與配額限制（每月 5,000 筆、公司不提升）。當要做「Sentry Ragdoll x.y.z~latest」巡查、查 Ragdoll 錯誤、Sentry 配額用盡或事件暴增、查不到事件懷疑被丟棄，或要判斷哪些錯誤該送、不該送 Sentry 時使用。
---

# Ragdoll Sentry 分流與配額檢查

Ragdoll（Electron POS）的錯誤經 van 的 `/proxy/sentry` 轉到 Sentry。本 skill 把「先看配額 → 排名 → 找洪水 → 分類 → 對照程式與 van → 產出」做成固定流程。

Maltese 的對應流程是 `maltese-workspace` 的 `maltese-sentry-triage`（專案 `pos`）；本 skill 是 Ragdoll 版，且多了**配額與洪水**的檢查，這是 Ragdoll 目前最大的問題（見下「配額限制」）。

## 配額限制（先記住）

- **公司不提升 Sentry 配額，每月只有 5,000 筆錯誤**（使用者定調，2026-11-18）。所以任何建議**不得包含「提升配額」**，降量只能走機台端：不相干的錯誤只留本地、同一種錯誤重複時只送最初幾筆。追蹤卡 RD-8632。
- **額度用盡時，新事件整批被 Sentry 丟棄**（`rate_limited／error_usage_exceeded`），搜尋結果會是空的，**空的不代表沒發生**。所以每一次調查的第一步都是查配額（Phase 0）。
- 2026-11-18 的狀況：額度在 10/29 用盡，之後約 3 週所有新錯誤都被丟棄；主因是單一機台的 `pilotPing` 洪水（細節與數字見 `references/baseline-2026-11-18.md`）。

## 環境常數

| 項目 | 值 |
|---|---|
| Sentry org slug | `wonderpet-dy` |
| Sentry region URL | `https://us.sentry.io` |
| 專案 | `ragdoll-local-pos`（Ragdoll）；`pos`（Maltese）；`van-proxy` |
| Jira 站台／cloudId | `wonderpet.atlassian.net`／`f338306a-4b54-421e-9209-2e9f451c67f7` |
| Jira 專案、Epic | `RD`、`RD-7600`（POS-R，Ragdoll 的卡掛這裡） |
| 巡查卡命名 | `Sentry Ragdoll <版本區間>`（例：RD-8442「Sentry Ragdoll 1.3.3~latest」），類型為任務 |

Sentry MCP 的工具都要先用 `ToolSearch` 載入；若只看到 `authenticate`，代表還沒登入，請使用者在 Claude Code 輸入 `/mcp` 登入 `plugin:sentry-mcp:sentry`。所有呼叫都帶 `organizationSlug: "wonderpet-dy"` 與 `regionUrl: "https://us.sentry.io"`。

## Phase 0：配額與被丟棄的事件（一定先做）

```
find_dropped_events(organizationSlug="wonderpet-dy", regionUrl="https://us.sentry.io",
                    projectSlug="ragdoll-local-pos", dataset="errors", statsPeriod="30d", interval="1d")
```

再查一次不帶 `projectSlug`（全組織）。判讀：

| outcome／reason | 意義 |
|---|---|
| `accepted` | 實際收進來、計入額度的錯誤 |
| `rate_limited`／`error_usage_exceeded` | **額度用盡被丟棄**（非預期）。出現就代表那天之後的事件看不到 |
| `client_discard`／`ratelimit_backoff` | SDK 收到 429 後退避，自己不送（非預期） |
| `client_discard`／`event_processor`（intentional） | `ignoreErrors` 等機台端過濾生效（預期） |

要抓的重點：

- `accepted` 的日期範圍：只出現在週期開頭幾天，之後全是 `rate_limited`，就是額度用盡；用盡當天可以估出額度週期。
- 全組織 `accepted` 加總 ≈ 5,000，代表額度正好用完。
- 額度週期**推斷是每月 26 日（UTC）重置**（上一週期 10/07 用盡、本週期 10/26 重置後 10/29 用盡），**沒有在 Sentry 帳務頁確認**；回報時註明是推斷。
- `dataset="spans"` 是另一個類別（非錯誤），不佔錯誤額度；要確認非錯誤類的量才查。

## Phase 1：依事件數排名

```
search_issues(organizationSlug="wonderpet-dy", regionUrl="https://us.sentry.io",
              projectSlugOrId="ragdoll-local-pos", query="environment:production",
              period="30d", sort="freq", limit=40)
```

- 上限 100 筆且無分頁；總數逼近上限時用「處理 → 重查」迴圈。
- 各 issue 的 `occurrences` 加總應約等於 Phase 0 的 `accepted`；差很多代表有 issue 沒被列出。
- **已封存（`ignored／archived_until_escalating`）的 issue 仍然計入額度**：封存只是不通知，事件照樣進來；要降量得在機台端不送，或在 Sentry 端設 inbound filter。
- 清單裡的 `firstSeen` 是查詢區間內的第一筆；用 `get_issue_details` 看到的才是整個保留期的第一筆，兩者可能不同。

## Phase 2：找單機洪水

對排名第一、第二的 issue 取標籤分布：

```
get_issue_tag_values(organizationSlug=..., regionUrl=..., issueId="RAGDOLL-LOCAL-POS-xx", tagKey="storeName")
# 再依序：configName、scope、networkClass、release
```

判斷準則：**單一 issue 佔已接收的三成以上，且單一 `configName`（機台）佔該 issue 九成以上**，就是單機洪水。這種情況不是分類問題，而是需要「重複抑制」（同機台、同 scope、同 errorCode 短時間內只送最初幾筆）。

可用的標籤：`scope`（如 `InvoiceDevice.pilotPing`）、`action`、`vendor`、`errorCode`、`networkClass`、`storeName`（3 碼）、`configName`（5 碼）、`release`（`ragdoll@x.y.z`）、`sentry_tunnel`（`van`／`maltese`）、`external_api_channel`。用 `search_errors` 取標籤要寫 `tags[storeName]`（寫 `tags.store` 查不到）。

## Phase 3：分類

依標題與標籤把剩下的 issue 分成三桶。這是人工判讀，不是 Sentry 欄位，**回報時要註明是人工分類**。

| 類別 | 判斷依據 | 2026-11-18 的例子 | 處置建議 |
|---|---|---|---|
| 連線／逾時類 | `networkClass`（如 `CONNECTION_REFUSED`、`DNS_BLOCKED`，完整分類見 `shared/utils/classify-network-error.ts`）、標題含 `fetch failed`、`ERR_NAME_NOT_RESOLVED`、`timeout`、`aborted`、`jwt expired`、`HTTP 503` | `TypeError: fetch failed`、`net::ERR_NAME_NOT_RESOLVED`、`The operation was aborted due to timeout` | 候選只留本地 |
| 顧客端預期內／僅供紀錄 | 業務錯誤碼（台新 `31288` 餘額不足、`31150` 查無交易、`31163` 超過退款期限）、折扣碼不存在、門市設定不存在；以錯誤層級上報的紀錄事件 | 台新 31288；大哥付「交易已建立」「被放棄」 | 候選只留本地 |
| 應處理 | 刷卡機通訊異常或無法確認交易結果、寫入衝突、查無更新、客顯視窗載入失敗、原生崩潰 | 「信用卡交易使用者放棄等待後…」；`Write Conflict`；`ERR_FAILED loading customer-display`；`OnRenderProcessLaunched` | 一律照送（第一筆） |

**付款、刷卡、發票、離線交易資料與當機類，永遠不屏蔽。**分類清單最終要由 PM 與工程確認，不是本 skill 單方決定。

## Phase 4：對照程式與 van

Ragdoll 端的上報路徑：

| 路徑 | 位置 | 備註 |
|---|---|---|
| main 進程 | `electron/main/lib/report-error.ts` 的 `reportError()` | 同時做 `logError`、`captureToSentry()`、寫 `logs/sentry-events/{date}.ndjson` 本地副本；本地產生的 `eventId` 店員回報要用 |
| renderer | `next/components/elements/app-initializer/index.tsx` 的 `Sentry.init` | 自行 `captureException`；main 的 `cRendererErrorChannels.ERROR` 只做本地落地 |
| 全域 | `electron/main/lib/init-sentry.ts` 的 `ignoreErrors`、`beforeSend` | `ignoreErrors` 目前只有 `/^Client destroyed$/`（`sentry-ignore-errors.ts`） |

**要屏蔽，就在 `captureToSentry` 之前判定**，`logError`、NDJSON 與 `eventId` 照留，店員回報流程（`findSentryEventByEventId`）才不受影響。

van 端要對照 `/proxy/sentry` 的狀態碼，見 `van-workspace:van-ops-inspect` 的 Step 5（需安裝 `van-workspace` plugin）。**特別注意**：renderer 事件目前因為標頭沒有 `dsn`，被 van 的白名單擋成 403（日誌 `reason: dsn_rejected`）；也就是 renderer 的事件目前是「意外」進不了 Sentry。**在機台端判定清單完成並確認用量前，不要建議放行**（van 放寬檢查或 renderer 加 `tunnel` 都算），放行最多讓進 Sentry 的量放大約 6 倍。

## Phase 5：產出

回報順序：

1. 配額狀態（用盡日期、丟棄量、推斷的下次重置日）。
2. 洪水（哪個 issue、哪台機台、占比）。
3. 分類表（三桶的筆數與例子，註明人工分類與樣本期間）。
4. 建議：不需發版的止血（處理該機台的根因、在 Sentry 端對特定 `scope` 設 inbound filter 或金鑰速率限制，被丟棄事件是否計額度要先確認）、需發版的修法（判定清單、重複抑制）。
5. 沒查什麼與不確定處。

**開卡**：使用者明確要求才開（不自行建票），流程用 `wonderpet-general:jira-create-issue-rule`。Ragdoll 在 Jira 的「代碼庫名稱」選單沒有對應值，所以類型用「任務」、標題前綴 `[Ragdoll]`、掛 `RD-7600`。巡查卡的驗收條件慣例是「檢查 sentry 無錯誤」「檢查新開啟的 related issue」兩條。

## 隱私

- 事件的標籤含 `salerName`（員編加姓名）與 `user.geo`，日誌樣本含門市公網 IP。**不要複製進 Jira、回覆或記憶**；只引用 `storeName`、`configName` 這類機台定位。
- `get_issue_details` 會回完整事件（含堆疊與 context），讀完只摘要結論。

## 踩雷

- **查不到事件先查 Phase 0**，不要直接下「沒發生」的結論。
- 用 Google Chat 回報的定位碼（Sentry event id）去 Sentry 查回 `No issue found`，不代表沒上報，可能被額度丟棄。
- 某些訊息只寫本機日誌、不進 Sentry（例如 `body.error` 的「total 和 items 加總不一致」），查不到是設計如此。
- Sentry 保留期有限（2026-11-11 的調查是只到 10/13），查更早的歷史要改用 git 歷史與正式站資料。
- `search_issues` 有 100 筆上限，且回傳量大時工具輸出會爆；分類時只取 `shortId`、標題、`occurrences`、`lastSeen`。
- 分類用的樣本只有額度內的事件（用盡後的事件看不到），**月化推算要保守看待**。
