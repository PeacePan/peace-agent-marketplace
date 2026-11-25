---
name: van-call-audit-inspect
description: Van（POS 對外 API 跳板機，pos-proxy）「對外呼叫與第三方回呼稽核紀錄」的唯讀查詢與驗收——查 Van 在什麼時間替哪個呼叫端（Ragdoll 門市機台／JavaCat 中台／第三方回呼）對哪個第三方（大哥付 oppay、台新、宜睿、Magento、PetsCare、Google Chat、Sentry）送了什麼、得到什麼結果（遮罩後內容、HTTP 狀態、業務結果碼、結果分類）。內含 EMF 紀錄欄位字典、已驗證的 Logs Insights 查詢、一次跑完的 aws-mcp 檢查腳本（部署狀態、紀錄分布、隱私掃描、API_monitor 指標、van-<env>-upstream-failures 告警）、三環境目前有沒有新版，以及驗收這類紀錄功能的對照與踩雷。當使用者問「大哥付回呼有沒有到 Van」「Van 送給大哥付的內容」「這筆交易 Van 實際送了什麼」「Van 對外呼叫紀錄」「依 caller／專案篩選」「van_upstream_failures」「API_monitor」「稽核紀錄有沒有個資」，或要驗收 RD-8258 一類的監控紀錄功能時使用。全程唯讀，不呼叫任何業務端點、不部署、不改設定。
---

# Van 對外呼叫稽核紀錄：查詢與驗收

第三方串接出問題時（大哥付回呼沒抵達、回傳業務失敗碼），要能直接回答「Van 在什麼時間、替誰、對哪個第三方送了什麼、得到什麼」，不必重現程式邏輯、不必請廠商查紀錄。RD-8258 讓 Van 每一次對外呼叫與每一次第三方回呼都留下一行 EMF 紀錄；這份 skill 讓你下次不必重新摸索怎麼查、怎麼判讀、怎麼驗收。

Van 的設計與契約見 Van 專案內的 `van-project-knowledge`（`Van/.claude/skills/`，「對外紀錄」一節）；紀錄核心在 `Van/src/logging/callAudit.ts`，白名單在 `Van/src/logging/callAuditRules.ts`。**欄位與白名單以原始碼為準**，本 skill 的欄位表是 2026-11-25 的快照。

## 與 `van-ops-inspect` 的分工

| | `van-ops-inspect` | 本 skill |
|---|---|---|
| 看什麼 | 請求流量、狀態碼分布、`/health`、ECS／ALB／存活告警 | 每一次對外呼叫與回呼的「內容與結果」、`API_monitor` 指標、`van-<env>-upstream-failures` 告警 |
| 資料來源 | pino 請求日誌（`req.*`、`res.statusCode`） | 稽核行（`_aws`、`direction`、`caller`、`service`…） |
| 共通點 | 同一個 log group `/ecs/van-<env>`，一律走 `aws-mcp` 的 `run_script`，全程唯讀 | 同左 |

**現成的 dashboard**：CloudWatch dashboard `Van-External-API`（RD 在 RD-8258 留言提供，用 CLI 建立、未納入 Terraform；2026-11-25 用 `GetDashboard` 確認存在，共 8 個圖表，有 `env` 切換變數）。內容是呼叫量／失敗數／平均耗時（依第三方）、呼叫量（呼叫端 × 第三方）、告警指標（逾時＋連不上）、最近 50 筆非成功紀錄、最近 100 筆紀錄。想「看一眼」先開它；要核對內容、做隱私掃描或對帳才用下面的查詢。驗收時沒有逐圖驗證圖表內容。

## 先記住的八件事

1. **稽核行與 pino 行混在同一個 log group。** 稽核行的判斷式是 `filter ispresent(_aws.Timestamp)`。⚠️ **不是 `ispresent(_aws)`**：2026-11-25 在 dev 實測，同一時段 `_aws.Timestamp` 查到 17 筆、`_aws` 查到 0 筆（Logs Insights 把巢狀 JSON 攤平成 `_aws.Timestamp`，父層不是欄位）。`Van/DEPLOY.md` 與 `van-project-knowledge` 寫的查法是後者，照貼會一筆都查不到，容易誤判成「沒有紀錄」。
2. **只寫 `service = 'oppay'` 會混進 pino 行**：pino 的 `req.log` 也帶 `service`、`action`。dev 實測 `service = 'oppay'` 有 25 行，稽核行只有 12。條件一律和第 1 條並用。
3. **兩個分類維度**：`caller`（`ragdoll` 門市機台、`javacat` 中台、`callback` 第三方回呼、`unknown`）與 `service`（`oppay`、`taishin`、`edenred`、`magento`、`petscare`、`gchat`、`sentry`）。`caller` 由通過的認證決定（門市密鑰、中台密鑰、來源位址門禁），不是呼叫端自報。
4. **`outcome` 六種**：`success`、`business_failure`（第三方回了非成功狀態或失敗結果碼）、`timeout`（結果未知，可能已受理）、`unreachable`（連不上）、`blocked`（回呼被來源門禁擋下）、`aborted`（回呼時服務商先斷線）。`httpStatus` 不等於業務結果，要連 `resultCode` 一起看。
5. **內容只記白名單欄位**，清單外一律不記：門號遮罩成前 4 碼＋後 2 碼（`0935****76`）；姓名、地址、身分證、卡號、條碼、憑證、簽章、完整網址都不記；單筆 request／response 各最多 2048 字元，超過截斷並標 `truncated: true`。新增第三方沒有清單就只記分類欄位。
6. **回呼（`direction = 'inbound'`）有自己的樣子**：多一個 `sourceIp`；`blocked` 那筆不解析內容（`request` 沒有、`response` 是 `{}`）且不計入 `api_requests`／`errors`；`notify` 的回應是 200 空本文，所以紀錄沒有 `response`，只有 `httpStatus`；`notify` 的 `resultCode` 取自請求的 `info_order.transaction_status`（dev 樣本：`005`、訊息「交易成功」）。
7. **可以串回同一個請求**：稽核行的 `requestId` 等於 pino 的 `req.id`。一個請求會有三行——pino 收到、稽核行、pino 完成（含 `res.statusCode`、`responseTime`）。實測見 `references/queries.md` 的「單筆追蹤」。
8. **指標與告警**：namespace `API_monitor`，維度 `[env, service]`、`[env, caller]`、`[env, caller, service]`，指標 `api_requests`／`errors`／`latency_ms`；告警用的 `van_upstream_failures`（逾時＋連不上）只有 `[env]` 維度。告警 `van-<env>-upstream-failures`：5 分鐘內加總 ≥ 5 送既有的 `alarm2sns2chat-<env>`，**dev 依設計不建**。同一個 namespace 還有 JavaCat 的大智通指標（維度 `project`、`full_path`），分析時用 `caller`／`service` 維度排除掉。

## 環境常數與目前部署狀態（2026-11-25 實測）

region `ap-northeast-1`；log group `/ecs/van-dev`、`/ecs/van-staging`、`/ecs/van-production`；ECS 叢集與服務同名 `van-<env>`。

| 環境 | 有沒有稽核紀錄功能 | 稽核行 | `API_monitor` 的 caller／service 指標 | `van-<env>-upstream-failures` | log 保留 |
|---|---|---|---|---|---|
| dev | 有（2026-11-23 09:28 UTC 部署，task definition `van-dev:25`） | 7 天內 17 筆 | 有 | 沒有（設計如此） | **7 天** |
| staging | 還沒（task definition `van-staging:4`，2026-11-03） | 0 | 無 | 不存在 | 7 天 |
| production | 還沒（task definition `van-production:4`，2026-11-03） | 0 | 無 | 不存在 | 30 天 |

- staging 與 production 要等 `staging/van`、`release/van` 分支帶到新版才會有紀錄；告警的 Terraform 在 `release/shiba`（RD-8258 的 Shiba PR 已合併），**apply 由人工執行**，還沒 apply 前告警不存在。
- 這張表會過時。**每次開工先跑 `references/queries.md` 的「一次跑完」腳本**重新確認，不要沿用這張表。
- dev 只留 7 天：驗收證據要當天存檔（`~/Documents/RD-XXXX-acceptance-evidence`），過了就查不到。

## 快速流程

### Step 0：先確認這個環境有沒有新版、有沒有資料
跑 `references/queries.md` 末段的「一次跑完」腳本，一次拿到部署時間、稽核行分布、隱私掃描、指標維度、告警是否存在、log 保留天數。**沒有稽核行時，先看部署狀態**（task definition 是不是舊的），不要直接下結論說「紀錄壞了」。

### Step 1：看分布（誰對誰、成敗如何）
```
filter ispresent(_aws.Timestamp)
| stats count(*) as n, min(@timestamp) as first_at, max(@timestamp) as last_at by direction, caller, service, action, outcome
| sort n desc | limit 100
```

### Step 2：看某一筆的內容（以大哥付建立交易為例）
```
fields @timestamp, direction, caller, service, action, httpStatus, resultCode, outcome, latency_ms, request.sms_to, request.items.0.product_name, response.transaction_id
| filter ispresent(_aws.Timestamp) and service = 'oppay' and direction = 'outbound'
| sort @timestamp desc | limit 20
```
巢狀欄位用 `request.sms_to`；陣列用 `request.items.0.product_name`（已實測）。**不要用 `fields @message` 取整行**，除非你確實要核對完整格式，且貼到回覆前先檢查內容。

### Step 3：依呼叫端、依回呼、依失敗分類
- 依專案：在條件加 `and caller = 'ragdoll'` 或 `and caller = 'javacat'`。
- 只看回呼：`and direction = 'inbound'`，欄位加 `sourceIp`（不要貼進回覆，只說明有值）。
- 失敗分類：`filter ispresent(_aws.Timestamp) and outcome != 'success' | stats count(*) as n by service, outcome`。
- 回呼有沒有到：看 `action = 'confirm'`、`'notify'` 的筆數與 `outcome`；被擋看 `outcome = 'blocked'`；服務商斷線看 `'aborted'`。

### Step 4：隱私掃描（只算筆數）
稽核行上跑五條計數查詢：憑證字樣、未遮罩的 `09` 開頭 10 碼、身分證格式、個資欄位名、網址。**預期全部 0 筆**。指令在 `references/queries.md`。注意這只證明「紀錄裡沒有已知形狀的個資」，姓名這類沒有固定格式的值，要靠對照白名單（`callAuditRules.ts`）確認沒有姓名欄位。

### Step 5：指標與告警
用 `references/queries.md` 的指標腳本讀 `api_requests`／`errors`／`latency_ms`／`van_upstream_failures`。**指標筆數要和稽核行對得上**（2026-11-25 dev：`javacat`＋`oppay` 指標 2＋3＝5、`ragdoll` 1＋4＝5，與 Logs Insights 完全一致），對不上才需要追。`GetMetricStatistics` 的 86400 秒區間以 `StartTime` 為起點切桶，不是 UTC 日界線，細節見該檔。

## 想自己造一筆新紀錄時（以下為 DEPLOY.md 記載，本次未實測）

- **本機出口 IP 直打 Van 主機會被共用 ALB 擋下**：2026-11-25 對 dev `/health` 回 `403`（`awselb`），與既有記憶一致。要打 `/proxy/*` 或 `/callbacks/*` 得先連公司網路／VPN。AWS 端的唯讀查詢（Logs Insights、CloudWatch、ECS）不受這個限制。
- `/proxy/oppay/*` 要中台專屬密鑰且來源位址在白名單；驗收者位址可暫時加進該環境 secret 的 `JAVACAT_EXTRA_SOURCE_IPS`（dev／staging 有效、production 忽略、約 60 秒生效），測完移除。`reserve` 會對大哥付測試環境建立真實交易，屬於寫入，要使用者同意。
- 最省事的是走既有真實流程（門市機台結帳選大哥付 → 中台 → Van）後再來查；dev 上已有 `javacat → oppay reserve` 與 `callback confirm／notify` 的紀錄，表示這條路會留紀錄。**不是你自己造的紀錄，報告要寫明來源與時間**。

## 驗收這類紀錄功能時

對照與判讀見 `references/acceptance-playbook.md`（RD-8258 的四條驗收條件如何對應到查詢、各自的證據等級、已知文件缺陷）。

## Anti-Rationalization

| 我想這樣 | 但不能，因為 |
|---|---|
| 照 `DEPLOY.md` 寫的 `filter ispresent(_aws) and service = 'oppay'` 查，查不到就說功能沒上 | `ispresent(_aws)` 永遠 0 筆。用 `ispresent(_aws.Timestamp)`，並先看部署狀態 |
| 只用 `service = 'oppay'` 篩，「這樣最簡單」 | 會混進 pino 行，筆數與內容都不是稽核行 |
| `outcome = success` 就當交易成功 | `success` 只代表第三方回了成功狀態與成功結果碼；`timeout` 是「結果未知，可能已受理」，不可當成失敗重試的依據 |
| 回呼沒有 `response` 欄位，就判定紀錄不完整 | `notify` 的回應是 200 空本文，沒有內容可記；`blocked` 依設計不記內容。看 `httpStatus` 與 `outcome` |
| 看到 `blocked` 就當成攻擊或事故 | 任何人都能打回呼入口；`blocked` 只表示來源不在白名單，不計入 `api_requests`／`errors`。是不是大哥付換了來源位址，要看 `sourceIp` 對不對得上 |
| 把 `sourceIp`、`order_id`、`transaction_id` 原樣貼進回覆或 Jira 留言 | 位址與單號能連回特定來源與交易；報告只寫「有值」或遮蔽後的形式 |
| staging／production 查到 0 筆就判「通過」或「失敗」 | 那兩個環境還沒部署新版，0 筆是預期；這是「無法驗證」，不是通過 |
| 用 Bash 跑 AWS CLI | AWS 工作一律走 `aws-mcp` 的 `run_script`（本機 aws CLI 是舊 v1、`jq`／`timeout` 沒裝）。腳本踩雷見 `van-ops-inspect/references/aws-mcp-pitfalls.md` |
| dev 的證據「之後再補」 | dev log 只留 7 天，過了就沒了；當天存檔 |

## 輸出建議

1. 先給結論表（環境 × 有沒有新版 × 稽核行筆數 × 指標 × 告警）。
2. 再給分布表（caller × service × action × outcome × 筆數、時間範圍，註明 UTC，台灣時間 +8）。
3. 附隱私掃描結果（五項各幾筆）與指標對帳結果（指標筆數 vs 稽核行筆數）。
4. 最後寫「沒查什麼」：沒有實際打 Van 端點、沒有對帳中台 `posthirdpartypayment`、沒有驗證告警是否真的送到 Google Chat。
