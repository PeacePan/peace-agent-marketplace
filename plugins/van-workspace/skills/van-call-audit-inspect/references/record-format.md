# 稽核紀錄的格式與判讀

快照日期 2026-11-25（對應 `Van/src/logging/callAudit.ts` 與 `callAuditRules.ts`）。**以原始碼為準**；改版後先對照這兩個檔再用本表。

## 一行紀錄長什麼樣（已脫敏的 dev 樣本）

outbound：中台呼叫大哥付建立交易

```json
{
  "_aws": { "Timestamp": 1795572425371, "CloudWatchMetrics": [ "…EMF 宣告，見下方「指標」" ] },
  "timestamp": "2026-11-25T02:07:05.371Z",
  "requestId": "<uuid>",
  "direction": "outbound",
  "caller": "javacat",
  "service": "oppay",
  "action": "reserve",
  "env": "dev",
  "httpStatus": 200,
  "resultCode": "000",
  "outcome": "success",
  "request": {
    "order_id": "<order_id>",
    "amount": 85,
    "sms_to": "0935****76",
    "merchant": { "manual_check": false },
    "items": [ { "product_name": "門市消費", "product_price": 85, "product_qty": 1 } ]
  },
  "response": { "result": "000", "message": "success", "transaction_id": "<transaction_id>", "expiration_date": "<yyyyMMdd>", "expiration_time": "<hhmmss>" },
  "api_requests": 1, "errors": 0, "latency_ms": 704, "van_upstream_failures": 0
}
```

inbound：大哥付付款後通知（`notify`）

```json
{
  "direction": "inbound", "caller": "callback", "service": "oppay", "action": "notify",
  "httpStatus": 200, "resultCode": "005", "outcome": "success", "sourceIp": "<來源位址>",
  "request": { "result": "000", "message": "交易成功", "info_order": { "order_id": "<order_id>", "transaction_id": "<transaction_id>", "transaction_status": "005", "amount": 85 } }
}
```

inbound：被來源門禁擋下（`blocked`）——沒有 `request`、`response` 是 `{}`、`api_requests` 與 `errors` 都是 0

```json
{ "direction": "inbound", "caller": "callback", "service": "oppay", "action": "notify", "httpStatus": 403, "outcome": "blocked", "sourceIp": "<來源位址>", "response": {}, "api_requests": 0, "errors": 0 }
```

## 欄位字典

| 欄位 | 意義 | 備註 |
|---|---|---|
| `_aws.Timestamp`、`_aws.CloudWatchMetrics` | EMF 宣告 | Logs Insights 攤平後用 `_aws.Timestamp` 判斷是不是稽核行 |
| `timestamp` | 呼叫開始時間（ISO，UTC） | 台灣時間 +8 |
| `requestId` | 請求追蹤編號 | 等於 pino 的 `req.id`，可串回同一請求的請求日誌 |
| `direction` | `outbound`（Van → 第三方）／`inbound`（第三方 → Van） | |
| `caller` | `ragdoll`／`javacat`／`callback`／`unknown` | 由認證決定；`unknown` 代表沒經過會標記的認證 |
| `service` | `oppay`／`taishin`／`edenred`／`magento`／`petscare`／`gchat`／`sentry` | |
| `action` | 端點名 | 見下表 |
| `env` | `dev`／`staging`／`production` | 指標維度 |
| `httpStatus` | 第三方回的 HTTP 狀態（inbound 是 Van 回的） | `aborted` 沒有；逾時／連不上沒有 |
| `resultCode` | 第三方的業務結果碼 | 位置見下表；最長 32 字元；取不到就沒有這欄 |
| `outcome` | 結果分類 | 見下表 |
| `sourceIp` | 回呼的來源位址 | 只有 inbound；不要貼進回覆 |
| `request`、`response` | 白名單過濾後的內容 | 各最多 2048 字元；超過整段改成截斷後的字串並標 `truncated` |
| `truncated` | `true` 代表有截斷（或回應過大沒解析） | 回應超過 256 KB（台新 16 KB）不解析 |
| `api_requests`、`errors`、`latency_ms`、`van_upstream_failures` | EMF 指標值，同一行也是明細 | 見下方「指標」 |

## `outcome` 判定

| 值 | 條件 | 計入 `api_requests` | 計入 `errors` | 計入 `van_upstream_failures` |
|---|---|---|---|---|
| `success` | 2xx 且結果碼在成功值內（或沒有結果碼規則） | 1 | 0 | 0 |
| `business_failure` | 非 2xx，或結果碼不在成功值內；或收到狀態列後才失敗（回應過大、讀到一半斷線） | 1 | 1 | 0 |
| `timeout` | 對外逾時（`UPSTREAM_TIMEOUT`）；第三方可能已受理 | 1 | 1 | 1 |
| `unreachable` | 沒有收到狀態列（連不上） | 1 | 1 | 1 |
| `blocked` | 回呼被來源門禁擋下（以門禁自己的標記為準，不從狀態碼反推） | **0** | **0** | 0 |
| `aborted` | 回呼的回覆送完之前服務商已斷線 | 1 | 1 | 0 |

`blocked` 不計入指標，是因為任何人都能打回呼入口，計入就等於讓外人決定大哥付的錯誤率。

## 各第三方：端點名與結果碼位置

| service | `action`（outbound） | 結果碼來源 | 成功值 |
|---|---|---|---|
| `oppay` | `reserve`（建立交易）、`refund`（退款） | 回應 `result` | `000` |
| `oppay`（inbound） | `confirm`（付款前確認）、`notify`（付款後通知） | 請求 `info_order.transaction_status`（`notify` 才有） | 無清單：成敗看 Van 回的 HTTP 狀態 |
| `taishin` | 依台新端點而定（`routes/taishin.ts` 的 `entry`） | 回應資料區 `RtnCode` | `000` |
| `edenred` | `get-voucher`、`authorization`、`search` 等 | 回應 `meta.status` | `succeeded` |
| `magento` | `products`、`exchange-orders`、`exchange`、`cancel-exchange` | 回應 `code` | `success` |
| `petscare` | `reports`、`auth-token`（換權杖那筆不記內容） | 回應 `success` | `true` |
| `gchat` | `send-message` | 無規則，只記分類欄位 | — |
| `sentry` | `envelope` | 無規則，只記分類欄位 | — |

## 白名單概要（只列欄位類別；精確清單在 `callAuditRules.ts`）

| service | 會記 | 一律不記 |
|---|---|---|
| `oppay` 請求 | 交易編號、金額、遮罩門號、`merchant.manual_check`、商品名稱／單價／數量 | `buyer`／`shipping`（加密個資）、`payment_uri`／`qrcode_img`（拿到就能付款）、商戶底下的網址 |
| `oppay` 回應 | 結果碼與訊息、交易編號、到期日時、退款編號／時間／金額 | — |
| `oppay` 回呼 | 訂單編號、結果、交易編號、交易狀態、金額 | `state`（識別碼，排查用不到） |
| `taishin` | 特店交易編號、金額、門市與終端代號、交易日期時間、查詢與交易類型；回應的結果碼與交易摘要 | 付款條碼（`barcode1-5`）、備註類自由輸入欄位 |
| `edenred` | 受理點、模式、票券面額與品類；回應的狀態、授權編號、金額 | 票券編號（路徑與 `vouchers[].ref`），票券本身 |
| `magento` | 門市、機台、核銷人、實際品項與價格；回應的結果碼、訊息、庫存、數量 | 兌換條碼、兌換單號、回應裡的姓名／會員編號／電話 |
| `petscare` | 最大商品數、寵物品種／生日／物種／性別；回應的成敗與錯誤 | 會員編號、寵物名、報告本文 |
| `gchat`、`sentry` | 只有分類欄位 | 全部內容 |

照記的欄位只收單一值；收到物件或陣列時只記型別（如 `[object]`），避免第三方改格式時白名單外的內容藏在白名單欄位底下一起被記下。

## 指標

namespace `API_monitor`。EMF 宣告兩組：

- 維度 `[env, service]`、`[env, caller]`、`[env, caller, service]`；指標 `api_requests`（Count）、`errors`（Count）、`latency_ms`（Milliseconds）。
- 維度 `[env]`；指標 `van_upstream_failures`（Count）。告警只吃這一個，所以新增第三方不必回頭補告警。

同一個 namespace 另有 JavaCat 呼叫大智通的指標（維度 `project`、`full_path`、`outcome`），與 Van 的指標互不干擾；篩 Van 時用 `caller` 或 `service` 維度。

## 稽核行不會有的東西

- `/health`：不記日誌也不記稽核。
- 中台（JavaCat）的呼叫本身：中台不是第三方，`Van/src/http/javacat.ts` 明確傳 `null` 不記。
- 依程式碼推得、**dev 未實測**：沒有發生對外呼叫就沒有稽核行（例如門市密鑰錯誤的 401、第三方憑證缺漏回 503），這類只會出現在 pino 請求日誌。
- 白名單外的欄位，以及任何憑證、簽章、完整網址。
