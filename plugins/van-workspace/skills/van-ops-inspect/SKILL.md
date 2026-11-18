---
name: van-ops-inspect
description: Van（POS 對外 API 跳板機，pos-proxy）的唯讀營運巡檢與流量查詢——三環境 /health 健康檢查、ECS／ALB target／CloudWatch 告警狀態、用 Logs Insights 依路徑與狀態碼統計請求量、大哥付（OPPay）請求漏斗、/proxy/sentry 狀態碼判讀。內含環境常數、已驗證的查詢與 aws-mcp 腳本踩雷。當使用者問「Van 狀態」「Van 主機正常嗎」「Van 有哪些請求」「大哥付請求量」「van 流量」「van 日誌怎麼查」「/proxy/sentry 為什麼 403」，或要做 Van 巡檢時使用。全程唯讀，不部署、不改設定。
---

# Van 營運巡檢與流量查詢

把「Van 現在好不好、有多少請求、請求長什麼樣」做成可重複的流程。這份 skill 的價值在於：環境常數不用再找、查詢語法已驗證過、`aws-mcp` 腳本的踩雷點已列出。

Van 本身的設計與契約（認證邊界、secret 契約、三環境）見 Van 專案內的 `van-project-knowledge`（`Van/.claude/skills/`）；wiki 在 `/Users/peacepan/workspace/ai-toolkits/skills/petpetgo-llm-wiki/wiki/van/`（`overview`、`deployment`、`proxy-integrations`、`oppay-proxy`、`oppay-callbacks`、`source-allowlist`）。本 skill 只管「怎麼查」。

## 原則

- **全程唯讀**：只打公開的 `GET /health`、AWS 的 `Describe*`／`List*`、Logs Insights 的 `StartQuery`／`GetQueryResults`。不呼叫任何業務端點（`/proxy/*`、`/callbacks/*`），不部署、不改 secret、不改 DNS／ALB／ECS。
- **AWS 一律走 `aws-mcp` 的 `run_script`**，不要用 Bash 跑 AWS CLI；健康檢查用 Bash `curl`。
- **不把識別資訊帶出來**：Magento 的 SKU、條碼、宜睿禮券號都在網址第三段之後；統計只取前兩段路徑與固定的動作名稱，不列出個別值。門市 IP、人員姓名也不貼進回覆。
- **回報時一定附「沒查什麼」**：沒查的項目（CPU、記憶體、5xx 延遲、各第三方是否真的通）要明講，不要讓「`/health` 200」被讀成「代發都正常」。

## 環境常數（2026-11-18 實測）

region `ap-northeast-1`。

| 環境 | 對外主機 | ECS 叢集／服務 | log group | target group |
|---|---|---|---|---|
| dev | `pos-proxy-development.wonderpet.asia` | `van-dev` / `van-dev` | `/ecs/van-dev` | `van-dev-tg` |
| staging | `pos-proxy-staging.wonderpet.asia` | `van-staging` / `van-staging` | `/ecs/van-staging` | `van-staging-tg` |
| production | `pos-proxy.wonderpet.asia` | `van-production` / `van-production` | `/ecs/van-production` | `van-production-tg` |

- CloudWatch 告警（前綴 `van-`）：`van-production-no-healthy-target`、`van-staging-no-healthy-target`。dev 當時沒有對應告警。
- Container Insights 的 log group 另有 `/aws/ecs/containerinsights/van-{env}/performance`，要看 CPU、記憶體時才用，本 skill 的標準流程沒有查它。
- 主機名稱是寫死在門市機台程式裡的硬契約，不可更動（見 `van-project-knowledge`）。

## Step 1：健康檢查

```bash
for h in pos-proxy-development.wonderpet.asia pos-proxy-staging.wonderpet.asia pos-proxy.wonderpet.asia; do
  printf '%s -> ' "$h"; curl -sS -m 10 -o - -w ' [HTTP %{http_code}, %{time_total}s]\n' "https://$h/health" 2>&1
done
```

期待三個都是 `200 {"status":"ok"}`。

`/health` 的限制要一併說明：

- 它只證明進程活著、ALB 打得到。
- 第三方憑證缺漏（Magento、台新、PetsCare、大哥付）只會停用該組代發、該組回 503，**`/health` 仍然是 200**。
- 所以「`/health` 200」不等於「各第三方代發都能用」。要確認代發，看 Step 3 的狀態碼分布。

## Step 2：ECS、ALB target、告警

用 `references/aws-status-script.md` 的腳本（已驗證可跑）。看這幾項：

- 服務 `desired` 與 `running`、`pending` 是否一致。
- 部署 `rolloutState` 是否為 `COMPLETED`、`failedTasks` 是否為 0。
- 最近事件是不是 `has reached a steady state`。
- target group 的每個目標是否 `healthy`、在哪個可用區。
- `van-` 告警的狀態。

**要對照 wiki 回報落差**：`van/deployment` 寫 production 是 2 台、跨可用區；2026-11-18 實測 production 是 1 台（單一可用區）。巡檢時若台數與 wiki 不同，如實回報並註明不知道是刻意縮減還是設定漂移。

## Step 3：流量統計（Logs Insights）

查詢語法與 Python 輪詢樣板在 `references/logs-insights-recipes.md`。讀結果前先記住這幾條：

1. **只計「完成」那行**：van 的 pino-http 每個請求記兩行，收到請求一行、回應完成一行，只有完成行有 `res.statusCode`。查詢一律加 `filter ispresent(res.statusCode)`，否則量會重複計算一倍。
2. **`/health` 不記日誌**（`autoLogging.ignore`），所以日誌量不含 ALB 健康檢查。
3. **日期是 UTC**：`bin(1d)` 以 UTC 切日，台灣時間差 8 小時，報告要註明。
4. **路徑只取前兩段加固定動作**：用 recipes 裡的 `parse` 運算式，第三段只取到第一個 `/` 為止（`products`、`exchange-orders`、`payment` 這類），不要取到 SKU 或條碼。
5. **加總要對得上**：各列加總應等於 `recordsMatched`；對不上代表查詢條件或解析有問題。
6. 以 `req.url` 分類時，注意 `HEAD /proxy/sentry` 的 401 是 Ragdoll 連線預檢（只看有沒有網路錯誤），屬設計，分析時獨立列出。

## Step 4：大哥付（OPPay）漏斗

四個入口：

| 路徑 | 方向 | 意義 |
|---|---|---|
| `/proxy/oppay/reserve` | 中台 → van → 大哥付 | 建立交易 |
| `/callbacks/oppay/confirm` | 大哥付 → van | 付款前確認訂單效用 |
| `/callbacks/oppay/notify` | 大哥付 → van | 付款後回報交易結果 |
| `/proxy/oppay/refund` | 中台 → van → 大哥付 | 退款 |

- 筆數看 recipes 的「大哥付」那條查詢；日分布用 `bin(1d)`。
- **狀態碼不等於業務結果**：van 對大哥付有回應就原樣交回（業務失敗碼如 `017` 也是 HTTP 200）；逾時是 504、連不上是 502。要看交易成功、取消、逾時各多少，得查中台 `posthirdpartypayment`（用 `mcp-wonderpet-table-usage` 的 JavaCat MCP，登入需要使用者提供 OTP），本 skill 不做。
- 504 的語意是「結果未知，可能已受理」，不能當成失敗重試的依據（見 wiki `van/oppay-proxy`）。

## Step 5：`/proxy/sentry` 狀態碼判讀

| 狀態碼 | 意義 | 備註 |
|---|---|---|
| 401 | 缺或錯共享密鑰，認證層擋下 | `HEAD` 的 401 多半是連線預檢 |
| 403 | 事件標頭宣告的來源專案不在白名單，日誌有 `reason: dsn_rejected` | 標頭沒有 `dsn` 欄位也是 403，見下 |
| 400 | 標頭讀不出來或解壓失敗（`malformed_header`／`decompress_failed`） | |
| 413 | 單封超過 8 MB | |
| 429 | Sentry 限流或配額用盡，van 原樣帶回 | 與 Sentry 後台的 `error_usage_exceeded` 對得上 |
| 502／503／504 | van 往 Sentry 這段有問題 | |

**403 的一個已知成因**：Ragdoll 的 renderer 端 `Sentry.init` 沒設 `tunnel`，SDK 因此不把 `dsn` 寫進 envelope 標頭，van 的 `readSourceProject` 回空字串，白名單比對失敗回 403。2026-11-18 的調查見 `ragdoll-workspace:ragdoll-sentry-triage`（需安裝 `ragdoll-workspace` plugin）與 Jira RD-8632。**遇到大量 403 時，不要直接建議放寬 van 的檢查**：Sentry 配額每月只有 5,000 筆，放行會讓進 Sentry 的量最多放大約 6 倍。

## 基準線（production，30 天，UTC 2026-10-19～11-18，僅供比對）

| 路徑 | 筆數 |
|---|---|
| `POST /proxy/sentry` | 333,159（403：271,011；200：52,965；429：9,170） |
| `HEAD /proxy/sentry`（401） | 12,232 |
| Magento | 3,636 |
| 台新 ONE 碼 | 695 |
| 大哥付 | 306（reserve 134、notify 90、confirm 77、refund 5） |
| PetsCare 報告 | 89 |
| 宜睿 | 64 |
| Google Chat | 11 |
| 全部 | 350,196 |

這是某一天的快照，不是規格。數字用來判斷「現在比當時多還是少」，不是用來判斷對錯。

## Anti-Rationalization

| 我想這樣 | 但不能，因為 |
|---|---|
| 「`/health` 是 200，代發都正常」 | 第三方憑證缺漏只停用該組並回 503，`/health` 不受影響 |
| 用 Bash 跑 AWS CLI，比 `run_script` 直接 | AWS MCP 的指示是 AWS 工作一律走它；CLI 版本與憑證也不保證可用（本機 aws CLI 是舊 v1） |
| 把 `HEAD /proxy/sentry` 的 401 當成攻擊 | 那是 Ragdoll 連線預檢，每天約 350～400 筆，屬設計 |
| 日誌筆數直接當請求數 | 沒過濾 `res.statusCode` 會重複計算一倍；`/health` 又不在日誌裡 |
| 用 SKU、條碼、禮券號當分組欄位，「想看哪個商品最多」 | 那是識別資訊，不該帶出日誌；只看動作層級 |
| 看到大量 403 就建議放寬 van 的 dsn 檢查 | 配額每月 5,000 筆，放行最多放大約 6 倍；先處理機台端判定清單（RD-8632） |

## 輸出建議

1. 先給結論表（三個環境 × 健康／ECS／target／告警）。
2. 再給流量表（路徑 × 筆數 × 狀態碼），註明時間區間與 UTC。
3. 列出異常與落差（例如 production 台數）。
4. 最後寫「沒查什麼」與下一步，並做一次加總核對（各列加總 = `recordsMatched`）。
