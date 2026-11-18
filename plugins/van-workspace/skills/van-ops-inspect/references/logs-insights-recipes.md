# Logs Insights 查詢樣板（Van）

log group：`/ecs/van-dev`、`/ecs/van-staging`、`/ecs/van-production`。已在 production 驗證（2026-11-18）。

日誌欄位（pino-http，JSON 自動展開）：`req.method`、`req.url`、`res.statusCode`、`responseTime`，另有 `req.headers.*`、`reason`、`service`、`action`、`compressed`。**每個請求兩行**：收到請求（沒有 `res.statusCode`）與回應完成（有）。

## 共用樣板：啟動查詢並輪詢結果

整段貼進 `aws-mcp` 的 `run_script`。只回傳字串，原因見 `aws-mcp-pitfalls.md`。

```python
region = 'ap-northeast-1'
now = int(time.time())
days = 30
start = now - days * 86400

async def run_query(group, qs):
    s = await call_boto3(service_name='logs', operation_name='StartQuery', region_name=region,
                         params={'logGroupName': group, 'startTime': start, 'endTime': now, 'queryString': qs})
    qid = s.get('queryId')
    res = None
    for i in range(60):
        await asyncio.sleep(2)
        res = await call_boto3(service_name='logs', operation_name='GetQueryResults', region_name=region, params={'queryId': qid})
        if res.get('status') in ('Complete', 'Failed', 'Cancelled', 'Timeout'):
            break
    out = ['status=%s matched=%s rows=%s' % (res.get('status'), res.get('statistics', {}).get('recordsMatched'), len(res.get('results', [])))]
    for row in res.get('results', []):
        out.append(' | '.join('%s=%s' % (c.get('field'), str(c.get('value'))[:60]) for c in row if c.get('field') != '@ptr'))
    if not res.get('results'):
        out.append('(no rows)')
    return out

groups = ['/ecs/van-production']   # 要比對三環境就列三個
results = await asyncio.gather(*[run_query(g, QUERY) for g in groups], return_exceptions=True)
report = []
for g, r in zip(groups, results):
    report.append('##### ' + g)
    report.extend(['ERR ' + str(r)] if isinstance(r, Exception) else r)
'\n'.join(report)
```

把下面任一條查詢字串指定給 `QUERY`。**Python 字串裡的反斜線要寫成雙反斜線**（如下）。

## 1. 路徑 × 方法 × 狀態碼（全部請求的分布）

```python
QUERY = ("filter ispresent(res.statusCode) "
         "| parse req.url /^\\/(?<p1>[^\\/?]*)\\/?(?<p2>[^\\/?]*)\\/?(?<p3>[^?]*)/ "
         "| stats count(*) as n, count_distinct(p3) as d3 by req.method, p1, p2, res.statusCode "
         "| sort n desc | limit 200")
```

`p3` 在這裡包含第三段之後的整串（可能是 SKU、條碼、禮券號），**只用 `count_distinct(p3)` 看有幾種，不要把 `p3` 列出來**。

## 2. 動作層級（排除 sentry，第三段只取固定動作名）

```python
QUERY = ("filter ispresent(res.statusCode) and req.url not like /sentry/ "
         "| parse req.url /^\\/(?<p1>[^\\/?]*)\\/?(?<p2>[^\\/?]*)\\/?(?<p3>[^\\/?]*)/ "
         "| stats count(*) as n by req.method, p2, p3, res.statusCode | sort p2 asc, n desc | limit 100")
```

這裡 `p3` 只到第一個 `/` 為止，結果是 `products`、`exchange-orders`、`exchange`、`payment`、`refund`、`reserve`、`notify` 這類固定名稱，可以安全列出。

## 3. 大哥付：路徑 × 狀態碼，與每日分布

```python
QUERY = "filter ispresent(res.statusCode) and req.url like /oppay/ | stats count(*) as n by req.url, res.statusCode | sort n desc"
# 每日分布
QUERY = "filter ispresent(res.statusCode) and req.url like /oppay/ | stats count(*) as n by bin(1d) as day, req.url | sort day asc"
```

## 4. `/proxy/sentry`：每日 × 狀態碼

```python
QUERY = ("filter ispresent(res.statusCode) and req.url like /sentry/ "
         "| stats count(*) as n by bin(1d) as day, res.statusCode | sort day asc, res.statusCode asc | limit 300")
```

## 5. `dsn_rejected` 筆數（403 的主要原因）

```python
QUERY = "filter @message like /dsn_rejected/ | stats count(*) as n"
```

## 6. 依機台版本看 `/proxy/sentry` 的狀態碼

```python
QUERY = ("filter ispresent(res.statusCode) and req.method = 'POST' and req.url = '/proxy/sentry' "
         "| parse req.headers.baggage /sentry-release=(?<rel>[^,]*)/ "
         "| stats count(*) as n by rel, res.statusCode | sort n desc | limit 40")
```

`rel` 的值長得像 `ragdoll%401.5.1`（`@` 被編碼成 `%40`）。

## 7. 只看欄位的取樣（確認欄位長相）

```python
QUERY = ("fields @timestamp, req.method, req.url, res.statusCode, responseTime "
         "| filter @message like /oppay/ | sort @timestamp desc | limit 5")
```

不要用 `fields @message` 取整行：被拒收事件的整行帶有請求標頭（含門市公網 IP、機台識別），不需要時不要拉。

## 讀結果的規則

- 各列加總要等於 `recordsMatched`；對不上先查查詢條件。
- 日期是 UTC（`bin(1d)`），台灣時間差 8 小時，報告註明。
- `/health` 不記日誌（`autoLogging.ignore`），日誌量不含 ALB 健康檢查。
- 查詢區間內的「今天」是不完整的一天，比對時要排除或註明。
- 含連字號的標頭欄位（如 `req.headers.user-agent`、`content-encoding`）用反引號分組時，2026-11-18 的實測回傳的是空值，原因未查明；`content-encoding` 另外是 van 在解析前就刪掉了，日誌本來就看不到。要看這類欄位改用 `parse` 從 `@message` 取，或用取樣查詢（第 7 條）看實際長相。
