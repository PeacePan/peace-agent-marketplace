---
name: van-add-proxy-endpoint
description: 在 Van（POS 對外 API 跳板機）新增或修改第三方代發端點的檢查清單——先判斷端點類型與認證掛載位置，再依序處理路由、憑證缺漏 fail-safe、upstream 位址、脫敏清單（日誌與 Sentry 兩處）、逾時巢狀、測試 fixture、DEPLOY.md 的 secret 表、Ragdoll 端同步與知識文件。當要為 Van 新增代發路由、接新第三方、改 secrets／upstreams／認證邊界、或審查 Van 端點的 PR 時使用。
---

# 在 Van 新增代發端點

Van 在 5 個月內陸續加了 Magento、台新、宜睿、Google Chat、PetsCare、Sentry、大哥付（建立交易與退款兩個轉發、兩個回呼）。每次都要同步十幾處，漏一處就會出事：憑證洩進日誌、缺一把金鑰整個服務停擺、環境打到正式站、機台白名單沒更新。這份清單把這些位置列出來。

**先讀 Van 專案內的 `van-project-knowledge`**（`Van/.claude/skills/`）：它有三環境契約、secret 契約、認證邊界與一組 Anti-Rationalization；本清單只補「新增端點時要做哪些事」。**完成標準（Exit Criteria）也沿用它那份**，不在這裡重複。

## Step 0：先判斷端點類型

類型決定掛在哪、用什麼憑證，選錯會造成安全問題。

| 類型 | 例子 | 掛載位置 | 憑證 |
|---|---|---|---|
| A. 門市代發，van 持有第三方憑證 | Magento、台新、PetsCare | `createServiceRouters()`，在 `createAuthMiddleware` **之後** | van 的 `ProxySecrets` |
| B. 門市代發，憑證或目標由呼叫端帶 | 宜睿（店家帳密隨請求）、Google Chat（呼叫端給 webhook 網址）、Sentry（目的地固定、不吃憑證） | 同 A，永遠掛載，不隨憑證缺漏停用 | 無，或請求自帶 |
| C. 伺服器對伺服器入口 | `/proxy/oppay/*`（中台呼叫） | `app.ts` 的認證**之前**，自己的把關：來源位址＋專屬密鑰 | 中台專屬密鑰（不是門市密鑰） |
| D. 服務商回呼 | `/callbacks/oppay/*` | `app.ts` 的認證**之前**，以來源位址白名單把關 | 無 |

**判斷準則**：這個入口能不能動錢、能不能對外發訊息？能，就不能用門市共享密鑰 `X-Ragdoll-Proxy-Token`——它寫死在 Ragdoll 程式碼裡隨安裝檔出貨，解開任一份安裝檔就取得得到，而且三個環境同值。這種入口屬 C 或 D。

## Step 1：路由檔 `src/routes/<vendor>.ts`

沿用現有檔的寫法（`gchat.ts` 最簡單，可當範本）：

- 匯出 `createXRouter({ base, token?, deps })`，路由用 `serviceBodyParser` 解析、`parseServiceBody` 驗證請求內容、`asyncHandler` 包裝、`callUpstream({ req, res, service, action, target, method, headers, payload, deps })` 送出。
- **目標網址一律由 van 組出**（`base` 來自環境表），呼叫端只送業務參數，無法指定網址。
- 若業務上一定要由呼叫端給網址（Google Chat 的 webhook），必須收窄：比對 `target.origin` 而非字首（`https://chat.googleapis.com.evil.example/` 的字首也會命中），不是目標就回 400。van 在 VPC 內，打得到門市機台打不到的內部服務，不能成為開放中繼。
- 內容不是 JSON 的（Sentry 的 envelope 是位元組）：用 `raw()` 解析、自己掛 `acceptRawEnvelope` 移除壓縮宣告，**不要整包解壓**（壓縮率可達千倍，van 是全門市共用出口，記憶體耗盡等於全門市無法刷卡）；只讀標頭那一行。
- 交易參數以查詢字串送出的（台新），不走 `callUpstream`，直接用 `forwardToUpstream`。
- 紀錄只留 `service` 與 `action`，**不要記目標網址與請求內容**：查詢字串裡可能有顧客卡號與簽章。
- 路由末端對「通過把關但路徑不存在」的請求回 404（見 `oppayProxy.ts`），否則會往下掉到門市認證、回一句誤導的「缺門市密鑰」401。

## Step 2：掛載與缺憑證的處置 `src/routes/services.ts`

- A 類：`proxy?.vendor ? createXRouter(...) : unconfiguredService('vendor')`。缺憑證時**只停用這一組**，回 503 `SERVICE_UNAVAILABLE` 並指名是設定未完成；不要讓整個 van 起不來，也不要回看起來像端點不存在的 404。
- B 類：直接掛載，不依賴 `ProxySecrets`。Google Chat 與 Sentry 正是門市異常的兩條回報通道，憑證沒配好時它們反而更需要能送出去。
- C 類：另建 `createXService`（比照 `createOppayProxyService`），在 `app.ts` 的認證之前掛載，未配好一律 401／403／503，不要放行。
- 改完要確認 `app.ts` 的掛載順序：`requestLogger` → `healthRouter` → 回呼與轉發入口（認證前）→ `createAuthMiddleware` → `createServiceRouters` → 錯誤處理。**`healthRouter` 必須在認證之前**（ALB 健康檢查不帶密鑰）。

## Step 3：憑證 `src/config/secrets.ts`

- 在 `ProxySecrets` 加**選用**欄位；`resolveProxySecrets` 把缺漏的鍵收進 `proxyDisabledReason`，缺漏只停用該組（`index.ts` 只 `warn`，服務照起）。服務級欄位（`SENTRY_DSN`、`RAGDOLL_PROXY_TOKEN`）才會缺漏就終止進程，**不要把第三方憑證拉齊成這一級**。
- 長度或格式有要求的金鑰（大哥付 AES 金鑰 32 bytes、初始向量 16 bytes），在開機時就視同缺漏並指名，不要等到第一筆交易才失敗。
- **`parseSecretString` 的錯誤訊息不可附 `JSON.parse` 的錯誤原文**：Node 22 的訊息會帶出錯誤位置附近的內容，那裡常常就是密鑰。
- Secrets Manager 的 `van/{env}/app` 三個環境都要補，值依環境不同（dev、staging 放測試參數，production 放正式參數）。
- 同步更新 `DEPLOY.md` 的 secret 缺漏後果表（鍵名、缺漏後果、長度要求）。Terraform 只驗 secret 存在，不驗內容齊全，`terraform apply` 會顯示成功。

## Step 4：服務位址 `src/config/upstreams.ts`

- 在 `UpstreamBases` 加欄位，**三個環境都要填**（`cUpstreamBasesByEnv`）。
- 位址由 van 自己的 `APP_ENV` 決定、呼叫端無從指定，目的是「非正式環境的門市操作打不到正式站」。PetsCare 是明文例外（只查不寫，三環境同用正式站）；新增其他例外要寫明理由。
- 廠商若沒有測試站，或測試站不穩（大哥付 dev 暫時改打 SIT），把原因寫在註解，並在知識文件記下「待廠商修好後改回」。
- 若廠商要回呼我們（需要填 van 的公開網址），用 `vanPublicBase(appEnv)`，**不要自己拼主機名稱**。

## Step 5：脫敏（兩處都要）

新增任何**標頭型**或**查詢字串型**的憑證，同步：

| 位置 | 清單 | 對應測試 |
|---|---|---|
| `src/logging/logger.ts` | `cRedactedHeaderPaths` | `test/request-logger.test.ts` |
| `src/logging/sentry.ts` | `cScrubbedRequestHeaders` | `test/sentry-scrub.test.ts` |

**這兩份清單目前不一致（2026-11-18 讀取程式碼）**：`logger.ts` 有宜睿的 `x-edenred-client-id`、`x-edenred-client-secret`，`sentry.ts` 沒有，`sentry-scrub.test.ts` 也沒有宜睿的案例。`scrubSensitiveRequestData` 只刪清單內的標頭，所以宜睿路徑的 5xx 事件送去 Sentry 時，請求標頭可能帶著店家的宜睿帳密。這是程式碼層面的判斷，**沒有實測是否真有事件帶出**；碰到宜睿或新增標頭型憑證時，先核實再補。

另外兩條已有的防線不要拆掉：`requestDataIntegration({ include: { data: false } })`（不附請求內容）與 `dropBreadcrumbs`（足跡會帶完整目標網址與查詢字串）。

## Step 6：逾時與回應語意

- 預設上限 `cUpstreamTimeoutMs = 25_000`（`src/http/forward.ts`），**必須短於呼叫端的等待上限**：門市機台等 30 秒，van 才能回帶追蹤編號的逾時，而不是被機台自己中斷後只看到「沒有回應」。
- 呼叫端若是中台（大哥付轉發，等 20 秒）、而中台又受 JavaCat Lambda 上限（28 秒）限制，就要巢狀：van 對廠商 15 秒 < 中台等 van 20 秒 < Lambda 28 秒。做法是路由內以 `Math.min(deps.timeoutMs, 該路由上限)` 壓低，只壓不拉高。
- 回應語意沿用共用層：**廠商有回應就原樣交回狀態碼與內容**（業務失敗碼也是 200）、廠商回 500 不重試、逾時回 504 `UPSTREAM_TIMEOUT`、連不上回 502 `UPSTREAM_UNAVAILABLE`。504 代表「結果未知，可能已受理」，呼叫端不得據此重試成不可逆的操作。

## Step 7：測試

新增 `test/<vendor>-routes.test.ts`，用 `test/helpers/serviceApp.ts`：`buildApp`、`proxySecrets`（用 `overrides` 抹掉要驗證的那一組）、`stubFetch`（每次回 `response.clone()`，因為 `Response` 的內容只能讀一次）、`hangingFetch`（模擬不回應直到逾時）、`createCaptureStream`（攔截日誌）。

至少涵蓋：

- 憑證缺漏回 503，且**不影響其他第三方**。
- 無或錯誤的 `X-Ragdoll-Proxy-Token` 回 401，且不對外發出任何請求。
- 目標位址依環境決定，呼叫端送的值無法覆寫。
- 上游 4xx／5xx 與業務失敗碼原樣交回；上游 500 只發一次請求。
- 逾時回 504（用 `timeoutMs: 20` 縮短）、連不上回 502。
- 日誌與錯誤上報的內容**不含憑證值**（用 `createCaptureStream` 斷言整段輸出不含密鑰字串）。

`npm run typecheck` 不涵蓋 `test/`（`tsconfig.json` 的 `include` 只有 `src`），測試檔的型別錯誤要另外看。

## Step 8：Ragdoll 端同步

| 項目 | 位置 | 說明 |
|---|---|---|
| IT 防火牆白名單對照 | `Ragdoll/electron/main/third-party/domains.ts` | 新增第三方要同步維護 domain（機台雖不直連，仍供 IT 白名單申請對照） |
| van 主機名稱 | `Ragdoll/electron/main/lib/utils/van-base-url.ts` | **硬契約，不可更動**；名稱不符時機台靜默退回 Maltese，門市毫無感覺 |
| 呼叫端的通道判定 | `Ragdoll/electron/main/lib/call-external-api.ts`、`.claude/skills/ragdoll-project-knowledge/references/modules/external-api-channel.md` | 哪些機台走 van 由中台【種子店家檔】`pospilot` 的關鍵字 `van` 決定，不是部署決定，環境建好不等於門市會用 |
| Ragdoll 端的呼叫與錯誤分類 | 依該廠商的呼叫模組 | 錯誤分類與 van 回傳的狀態碼、訊息要對得上（例：大哥付退款的 Ragdoll 錯誤分類與中台訊息文案耦合） |

## Step 9：文件

- `Van/DEPLOY.md`：secret 缺漏後果表。
- `Van/.claude/skills/van-project-knowledge/SKILL.md`：新增契約或踩雷。
- wiki（`/Users/peacepan/workspace/ai-toolkits/skills/petpetgo-llm-wiki/wiki/van/`）：`proxy-integrations`（代發端點）或新增專頁；另有大哥付專頁 `oppay-proxy`、`oppay-callbacks`、`source-allowlist` 可當範本。

## Anti-Rationalization（補充 `van-project-knowledge` 沒有的）

| 我想這樣 | 但不能，因為 |
|---|---|
| 讓呼叫端傳目標網址，比較有彈性 | van 位於 VPC 內，打得到門市機台打不到的內部服務；呼叫端給網址就照打會變成開放中繼。必要時只收窄到單一 origin（比對 `origin`，不比字首） |
| 新端點先重用 `RAGDOLL_PROXY_TOKEN`，之後再換 | 它隨安裝檔出貨，擋的是隨機掃描、不是有心人。能動錢或能發訊息的入口要伺服器端專屬密鑰加來源位址 |
| 日誌多記請求內容，除錯比較方便 | 查詢字串裡有顧客卡號與簽章；只留 `service` 與 `action`，診斷靠網域、路徑與追蹤編號 |
| 只在 `logger.ts` 加脫敏，Sentry 那邊「應該不會帶標頭」 | `scrubSensitiveRequestData` 只刪清單內的標頭，Sentry 事件預設會帶請求標頭；兩處清單都要加 |
| 非正式環境直接打廠商正式站，省得申請測試帳號 | 「非正式環境的門市操作打不到正式站」是環境表的設計目的；例外必須明文寫理由（PetsCare 只查不寫） |
| 逾時設長一點，避免誤判失敗 | van 的上限必須短於呼叫端的等待上限，否則呼叫端先放棄、拿不到帶追蹤編號的 504 |
| 用 `typecheck` 全綠當作測試檔沒有型別問題 | `typecheck` 不涵蓋 `test/` |
