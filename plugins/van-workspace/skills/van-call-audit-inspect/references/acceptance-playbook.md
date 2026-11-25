# 驗收劇本：Van 對外呼叫稽核紀錄（以 RD-8258 為例）

2026-11-25 依 RD-8258 實際驗收整理。下次驗收同類功能（新增第三方的紀錄、改白名單、改告警）可以照這個順序走；數字是當天快照，只用來比對「現在比當時多還是少」，不是規格。

## 範圍與工具

- Van 的卡**不在** `ragdoll-workspace:ragdoll-acceptance-workflow`（只適用父系 Epic 為 RD-7600 的 POS-R 卡）範圍內。RD-8258 的 Jira 回傳沒有 `parent`，是使用者明確指定才驗。
- 驗收主戰場是 CloudWatch（Logs Insights、指標、告警），不是 Ragdoll 畫面；Ragdoll 只是其中一個「呼叫端」。
- 本機出口 IP 直打 Van 主機會被 ALB 擋下（403），所以預設用 AWS 端唯讀查詢驗收，不需要 VPN；要自己造新紀錄才需要（見 `SKILL.md`）。
- PR 狀態：Van 的程式在 `master`（PR #26661 已合併），告警 Terraform 在 `release/shiba`（PR #26662 已合併、apply 人工）。已合併的程式用含該 commit 的 checkout 驗即可（`git merge-base --is-ancestor <PR head> HEAD`）。

## 順序

1. 讀卡：`customfield_10030`（驗收條件）、`customfield_10057`（規格；任務卡的驗收細節常只寫在規格）。
2. diff-first：讀 `callAudit.ts`、`callAuditRules.ts`，確認「誰標呼叫端」（`auth.ts`→`ragdoll`、`javacatProxyAuth.ts`→`javacat`、`oppaySourceGuard.ts`→`callback`）。
3. 跑 PR 的測試作獨立證據：Van 的主 repo 沒有 `node_modules`，要在 worktree 內直接 `npm ci`（不要 symlink）；`npm test -- test/call-audit.test.ts test/call-audit-routes.test.ts`，再跑整套 `npm test` 與 `npm run typecheck`。2026-11-25：兩個新檔 31 項、整套 32 檔 416 項全過，`typecheck` 無錯誤輸出（`typecheck` 不涵蓋 `test/`）。
4. 跑「一次跑完」腳本（`queries.md`）：先確認哪個環境有新版、有沒有資料。
5. 逐條對照驗收條件（下表），每條記下查詢與結果。
6. **當天把證據存檔**（dev log 只留 7 天）：`~/Documents/RD-XXXX-acceptance-evidence/`。
7. 預設只回報、附留言草稿，使用者明確要求才留言。

## 驗收條件對照（RD-8258）

| # | 驗收條件重點 | 查什麼 | 通過的樣子 | 證據等級 |
|---|---|---|---|---|
| 1 | dev 呼叫一次大哥付建立交易，Logs Insights 以 `oppay` 查到時間、端點、HTTP 狀態、業務結果碼、遮罩後請求與回應 | `Q_DETAIL` | 有 `direction=outbound`、`service=oppay`、`action=reserve`、`httpStatus=200`、`resultCode=000`、`request.sms_to` 為遮罩格式、`response.transaction_id` | 實機·真實資料 |
| 2 | 門市機台與中台各呼叫一次，能以呼叫端專案分開篩選 | `Q_BY_CALLER`、`Q_DAILY`，並讀 `auth.ts`／`javacatProxyAuth.ts` 的 `markCaller` | `caller=ragdoll` 與 `caller=javacat` 各有自己的列；呼叫端由認證決定 | 實機·真實資料＋程式碼追蹤 |
| 3 | 手機門號遮罩（`0935****76`），找不到 Authorization、token、姓名、地址、身分證字號 | 隱私掃描五條＋對照白名單 | 掃描全 0；`sms_to` 是 `前 4 碼＋****＋後 2 碼`；白名單沒有姓名／地址欄位 | 實機·真實資料＋自動測試 |
| 4 | 大哥付回呼（confirm／notify）抵達或被門禁擋下，都有一筆 `inbound`，含來源位址與 Van 的回應 | `Q_INBOUND`（再加 `outcome = 'blocked'` 看被擋的那筆） | 抵達：`confirm`、`notify` 各有 `success` 且 `sourceIp` 有值；被擋：`outcome=blocked`、`httpStatus=403`、`sourceIp` 有值 | 實機·真實資料；`aborted` 只有自動測試 |

**判讀要點**

- 條件 2 的字面是「同一段時間內各呼叫一次」。若是拿既有紀錄對照（不是自己造一組），報告要寫明「紀錄不是驗收者產生、時間範圍是 X 到 Y」，並說明要不要補一組受控呼叫（需要 VPN 與中台流程）。
- 條件 4 的「Van 的回應」：`confirm` 的回應是 `{result: bool}`，記在 `response`；`notify` 的回應是 200 空本文，只有 `httpStatus`；`blocked` 依設計不記內容，只有 `httpStatus=403` 與 `outcome=blocked`。三種都算「有 Van 的回應」，不要因為 `response` 空就判不通過。
- 條件 3 的掃描只涵蓋稽核行；姓名等無固定格式的值靠白名單比對，報告要寫清楚這個限制。

## 補充查核（規格有寫、驗收條件沒單獨列）

| 規格 | 怎麼查 | 備註 |
|---|---|---|
| 每筆紀錄的必要欄位（時間、請求追蹤編號、方向、呼叫端、第三方、端點、HTTP 狀態、結果碼、結果分類、耗時、遮罩內容） | `Q_DETAIL`＋`record-format.md` | 實機看得到 |
| 兩個維度都是 EMF 指標維度 | 一次跑完腳本的「維度組合」＋指標對帳 | dev 有；staging／production 還沒部署 |
| 七個第三方一次涵蓋 | `call-audit-routes.test.ts` 七個第三方各一條 | dev 只有 `oppay`、`gchat`、`sentry`、`magento` 有真實呼叫，`taishin`、`edenred`、`petscare` 只有自動測試證據 |
| 內容過大截斷、單筆有上限 | `call-audit.test.ts` | 只有自動測試；dev 沒有真實大回應 |
| 對外失敗可觸發告警，沿用 Google Chat 轉發 | 一次跑完腳本的「告警」＋ `DEPLOY.md`「對外紀錄與告警」第 3、4 條 | 告警沒建出來前標「無法驗證」；`set-alarm-state` 只驗「告警→聊天室」，不驗指標，且只能在 staging 做 |

## 2026-11-25 的正常長相（dev，7 天內 17 筆）

| caller | service | action | outcome | 筆數 |
|---|---|---|---|---|
| javacat | oppay | reserve | success | 5 |
| callback | oppay | confirm | success | 3 |
| callback | oppay | notify | success | 3 |
| callback | oppay | notify | blocked | 1 |
| ragdoll | gchat | send-message | success | 2 |
| ragdoll | sentry | envelope | success | 2 |
| ragdoll | magento | products | business_failure（404，商品不存在） | 1 |

- 耗時：`oppay reserve` 平均約 434 ms、最大 704 ms；`callback` 平均約 191 ms。
- `van_upstream_failures` 為 0。dev 的 log 只留 7 天，這批紀錄約 2026-11-30 起陸續過期。
- staging、production：稽核行 0 筆、`API_monitor` 沒有 `caller`／`service` 指標、`van-<env>-upstream-failures` 不存在（還沒部署新版、Terraform 還沒 apply）。

## 已知文件缺陷（2026-11-25 發現，尚未修）

`Van/DEPLOY.md`「對外紀錄與告警」第 1 條與 `Van/.claude/skills/van-project-knowledge/SKILL.md`「對外紀錄」的查法寫 `filter ispresent(_aws) and service = 'oppay'`：
- `ispresent(_aws)` 永遠 0 筆，要改 `ispresent(_aws.Timestamp)`；
- 單寫 `service = 'oppay'` 會混進 pino 行，必須與稽核行判斷式並用。

照文件操作的人會查不到任何紀錄，容易誤判成功能沒上線。修正屬於 Van 程式庫的文件變更，驗收時只回報、不順手改。

## 沒驗證到的（報告要寫）

- 沒有實際打 Van 端點（本機被 ALB 擋、也不屬於唯讀）；dev 的紀錄不是驗收者產生。
- `timeout`、`unreachable`、`aborted` 的實機紀錄（dev 沒有）；只有自動測試。
- 告警是否真的送到 Google Chat；staging、production 全部。
- 沒有對帳中台 `posthirdpartypayment`（`request.order_id` 對應交易紀錄的 `name`；可用 `mcp-wonderpet-table-usage` 的 JavaCat MCP 唯讀對帳，登入需使用者提供 OTP）。

## 留言與證據的注意

- 不貼 `sourceIp`、`order_id`、`transaction_id`；寫「有值」或遮蔽後的形式。
- 留言內文寫給 PM／QA：操作什麼、看到什麼、哪些靠自動測試、哪些尚未部署。
- dev 證據當天存檔；資料夾慣例 `~/Documents/RD-XXXX-acceptance-evidence/`。
