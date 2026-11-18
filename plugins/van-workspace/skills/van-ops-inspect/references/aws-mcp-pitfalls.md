# aws-mcp `run_script` 與相關工具的踩雷

2026-11-18 巡檢 Van 時實際遇到的問題。每一條都有對應的做法。

## 1. 驗證器把自訂的鍵名誤判成 API 回應欄位

`run_script` 在執行前會先驗證程式碼。如果你在腳本裡自己組的 dict 用了「看起來像 AWS 回應欄位」的鍵名，驗證器會把它們當成 API 回應的欄位去檢查，然後拒絕。

實際被拒的訊息：

```
Line 31: "targets" is not a valid field in the response
Line 36: "error" is not a valid field in the response
...
"targets" is not a valid field for Failure. Valid fields: arn, detail, reason.
Line 30: "tgArn" is not a valid field in the response
```

被擋過的鍵名：`targets`、`error`、`tgArn`、`tgMembers`、`tgErr`。連 `arn` 這種和回應欄位同名的也會被牽連。

**做法**：不要在腳本裡建巢狀的自訂 dict 去裝結果。把結果格式化成純字串（`'%s state=%s' % (...)`），放進清單，最後 `'\n'.join(...)` 回傳。`aws-status-script.md` 與 `logs-insights-recipes.md` 都是這個寫法。

## 2. 一次寫完，別逐步補

驗證失敗不會執行任何 API，但每次重送都要重寫整段。腳本一次涵蓋所有查詢，用 `asyncio.gather(..., return_exceptions=True)` 平行跑，單一失敗不影響其他。

## 3. 回傳值

- 最後一個運算式要單獨一行，作為回傳值（不要 `print`）。
- 預先匯入的模組有 `asyncio`、`time`、`json`、`re` 等；沙箱裡除了 `call_boto3` 沒有網路。
- `operation_name` 要用 PascalCase 的 API 名稱（`DescribeServices`、`StartQuery`）。

## 4. Logs Insights 是非同步的

`StartQuery` 回 `queryId`，要用 `GetQueryResults` 輪詢到 `status` 為 `Complete`。腳本裡用 `await asyncio.sleep(2)` 搭配迴圈即可，樣板在 `logs-insights-recipes.md`。

## 5. 不要用 Bash 跑 AWS CLI

AWS MCP 伺服器的指示是 AWS 工作一律走它的工具。本機的 `aws` CLI 也是舊的 v1，`jq` 與 `timeout` 沒裝。

## 6. zsh 的未引號 glob 會讓整條指令消失

`grep -r pattern . --include=*.md` 在 zsh 會因為 `*.md` 沒有符合的檔案而回 `no matches found`，整個指令不執行，連 `&&` 後面的也不跑。**一律引號**：`--include='*.md'`。

## 7. 路徑與工作目錄

- wiki 的 Van 頁面路徑是 `/Users/peacepan/workspace/ai-toolkits/skills/petpetgo-llm-wiki/wiki/van/`，**不是** `wiki/wiki/van/`（多寫一層會回「File does not exist」）。
- Bash 的工作目錄每次呼叫後會重設，一律用絕對路徑，不要依賴 `cd`。

## 8. 工具輸出太大

- 分組統計時明確加 `limit 200`，取樣時加 `limit 5`，避免回傳量失控。
- 不要用 `fields @message` 取整行：一行就可能上千字，而且含請求標頭（門市公網 IP 等）。
