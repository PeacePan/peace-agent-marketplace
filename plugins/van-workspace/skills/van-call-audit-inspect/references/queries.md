# Logs Insights 查詢、指標與一次跑完腳本

全部已在 2026-11-25 對 `/ecs/van-dev`、`/ecs/van-staging`、`/ecs/van-production` 與 CloudWatch 實跑驗證。用法：整段貼進 `aws-mcp` 的 `run_script` 的 `code`。**一律不用 Bash 跑 AWS CLI。**

寫腳本的規則（細節見 `van-ops-inspect/references/aws-mcp-pitfalls.md`）：

- 只回傳純字串與清單，不在腳本裡建巢狀的自訂 dict；驗證器會把 `targets`、`error`、`arn` 這類鍵名誤判成 API 回應欄位而整段拒絕。
- 最後一個運算式單獨一行當回傳值；Python 字串裡的反斜線要寫成雙反斜線。
- `StartQuery` 是非同步，要輪詢 `GetQueryResults` 到 `Complete`。
- 時間一律 UTC，台灣時間 +8。

## 共用樣板（單一環境、可同時跑多條）

```python
region = 'ap-northeast-1'
ENV = 'dev'          # dev / staging / production
DAYS = 7             # dev、staging 的 log 只保留 7 天；production 30 天
now = int(time.time())
start = now - DAYS * 86400
group = '/ecs/van-' + ENV

async def run_query(label, qs, width=48, max_rows=50):
    s = await call_boto3(service_name='logs', operation_name='StartQuery', region_name=region,
                         params={'logGroupName': group, 'startTime': start, 'endTime': now, 'queryString': qs})
    qid = s.get('queryId')
    res = None
    for i in range(60):
        await asyncio.sleep(2)
        res = await call_boto3(service_name='logs', operation_name='GetQueryResults', region_name=region, params={'queryId': qid})
        if res.get('status') in ('Complete', 'Failed', 'Cancelled', 'Timeout'):
            break
    out = ['##### %s status=%s matched=%s rows=%s' % (label, res.get('status'), res.get('statistics', {}).get('recordsMatched'), len(res.get('results', [])))]
    for row in res.get('results', [])[:max_rows]:
        out.append(' | '.join('%s=%s' % (c.get('field'), str(c.get('value'))[:width]) for c in row if c.get('field') != '@ptr'))
    if not res.get('results'):
        out.append('(no rows)')
    return out

# 把要跑的查詢放進清單；Q_* 見下方
queries = [('分布', Q_DIST), ('依呼叫端與第三方', Q_BY_CALLER)]
results = await asyncio.gather(*[run_query(label, q) for label, q in queries], return_exceptions=True)
report = []
for r in results:
    report.extend(['ERR ' + str(r)] if isinstance(r, Exception) else r)
'\n'.join(report)
```

**所有查詢都以 `filter ispresent(_aws.Timestamp)` 起頭**：這是稽核行的判斷式。`ispresent(_aws)` 查 0 筆，只寫 `service = 'oppay'` 會混進 pino 行（見 `SKILL.md`「先記住的八件事」）。

## 查詢（Python 字串寫法）

```python
# 1. 分布：誰對誰、成敗如何、第一筆與最後一筆時間
Q_DIST = ("filter ispresent(_aws.Timestamp) "
          "| stats count(*) as n, min(@timestamp) as first_at, max(@timestamp) as last_at by direction, caller, service, action, outcome "
          "| sort n desc | limit 100")

# 2. 明細：大哥付建立交易（巢狀欄位 request.sms_to；陣列 request.items.0.product_name）
Q_DETAIL = ("fields @timestamp, direction, caller, service, action, httpStatus, resultCode, outcome, latency_ms, "
            "request.sms_to, request.items.0.product_name, response.transaction_id "
            "| filter ispresent(_aws.Timestamp) and service = 'oppay' and direction = 'outbound' "
            "| sort @timestamp desc | limit 20")

# 3. 依呼叫端與第三方：筆數、失敗數、平均與最大耗時
Q_BY_CALLER = ("filter ispresent(_aws.Timestamp) "
               "| stats count(*) as n, sum(errors) as err, avg(latency_ms) as avg_ms, max(latency_ms) as max_ms by caller, service "
               "| sort n desc")

# 4. 回呼：有沒有到、結果碼（notify 才有）。sourceIp 只確認有值，不要貼進回覆
Q_INBOUND = ("filter ispresent(_aws.Timestamp) and direction = 'inbound' "
             "| fields @timestamp, action, outcome, httpStatus, resultCode, request.info_order.transaction_status "
             "| sort @timestamp desc | limit 20")

# 5. 非成功的分類
Q_NON_SUCCESS = ("filter ispresent(_aws.Timestamp) and outcome != 'success' "
                 "| stats count(*) as n by service, outcome")

# 6. 每日（UTC）依呼叫端
Q_DAILY = ("filter ispresent(_aws.Timestamp) "
           "| stats count(*) as n by bin(1d) as day_utc, caller | sort day_utc asc")

# 7. 單筆追蹤：稽核行的 requestId 等於 pino 的 req.id，一個請求會有三行
#    （pino 收到、稽核、pino 完成含 res.statusCode 與 responseTime）。把 RID 換成要查的 requestId
RID = '<requestId>'
Q_TRACE = ("filter req.id = '%s' or requestId = '%s' "
           "| fields @timestamp, req.method, res.statusCode, responseTime, direction, outcome "
           "| sort @timestamp asc | limit 10" % (RID, RID))

# 8. 驗證「只篩 service 會混進 pino 行」：n 是全部、audit_lines 是稽核行
Q_MIX = "filter service = 'oppay' | stats count(*) as n, count(_aws.Timestamp) as audit_lines by action | sort n desc"
```

不要在查詢裡取 `req.url`：它會帶 SKU、條碼、禮券號（見 `van-ops-inspect` 的原則）。要取整行 `@message` 時，只對稽核行取（`filter ispresent(_aws.Timestamp)`），且貼出前先檢查內容。

## 隱私掃描（只算筆數，預期全部 0）

在稽核行上跑五條計數，**只回筆數、不印命中的內容**：

```python
AUDIT = "filter ispresent(_aws.Timestamp)"
SCANS = [
    ('憑證字樣', "(@message like /Authorization/ or @message like /[Bb]earer/ or @message like /[Tt]oken/ or @message like /[Ss]ecret/ or @message like /[Ss]ignature/)"),
    ('未遮罩門號', "@message like /09[0-9]{8}/"),
    ('身分證格式', "@message like /[A-Z][12][0-9]{8}/"),
    ('個資欄位名', "@message like /\"(buyer|shipping|name|address|email|barcode|url)\"/"),
    ('網址', "@message like /https?:\\/\\//"),
]
queries = [('隱私掃描-' + label, AUDIT + " and " + cond + " | stats count(*) as n") for label, cond in SCANS]
```

放進「共用樣板」的 `queries` 即可。解讀：

- 0 筆只證明「稽核行裡沒有這些已知形狀」。姓名、備註這類沒有固定格式的值掃不出來，要對照 `callAuditRules.ts` 的白名單確認沒有這類欄位。
- 個資欄位名那條用 `"name"` 這種「引號包住的整個欄位名」比對，`product_name` 不會誤中；若白名單日後加了名為 `name` 的欄位，這條會誤報，要先看白名單。
- 掃整個 log group（含 pino 行）是另一件事：拿掉 `AUDIT and`。2026-11-25 對 dev 與 production 掃 `Authorization`／`proxy-token`／`Bearer`：dev 45 行、production 26 行含 `authorization` 字樣，但全部同一個形狀（字樣後接 `","q`，像是標頭名稱出現在某個值裡），`proxy-token` 與 `Bearer` 兩個字樣是 0 筆；沒有看到憑證值，**也沒有再往下追**。

## 指標（CloudWatch）

```python
region = 'ap-northeast-1'
now = int(time.time())

async def metric(dims, name, stat):
    r = await call_boto3(service_name='cloudwatch', operation_name='GetMetricStatistics', region_name=region,
                         params={'Namespace': 'API_monitor', 'MetricName': name, 'Dimensions': dims,
                                 'StartTime': now - 3 * 86400, 'EndTime': now, 'Period': 86400, 'Statistics': [stat]})
    pts = sorted(r.get('Datapoints', []), key=lambda p: p.get('Timestamp'))
    return ['##### %s %s %s: ' % (name, stat, ','.join('%s=%s' % (d['Name'], d['Value']) for d in dims))
            + '; '.join('%s=%s' % (str(p.get('Timestamp'))[:10], p.get(stat)) for p in pts)]

tasks = [
    metric([{'Name': 'env', 'Value': 'dev'}, {'Name': 'caller', 'Value': 'javacat'}, {'Name': 'service', 'Value': 'oppay'}], 'api_requests', 'Sum'),
    metric([{'Name': 'env', 'Value': 'dev'}, {'Name': 'caller', 'Value': 'ragdoll'}], 'api_requests', 'Sum'),
    metric([{'Name': 'env', 'Value': 'dev'}], 'van_upstream_failures', 'Sum'),
]
results = await asyncio.gather(*tasks, return_exceptions=True)
report = []
for r in results:
    report.extend(['ERR ' + str(r)] if isinstance(r, Exception) else r)
'\n'.join(report)
```

- **維度要完整對上**：`api_requests` 只存在 `[env, service]`、`[env, caller]`、`[env, caller, service]` 三種組合；`van_upstream_failures` 只有 `[env]`。維度給多或給少都會查到空。
- **日期標籤不是 UTC 日界線**：`Period` 86400 秒時，區間以 `StartTime`（`now - 3 天`）為起點切桶，`str(Timestamp)[:10]` 是「桶的起點日期」。2026-11-25 的對帳就是這樣：標籤 `11-23` 的桶涵蓋 11-23 03:23 到 11-24 03:23 UTC。要對齊 UTC 日界線，把 `StartTime` 設成 UTC 午夜（`(now // 86400) * 86400 - 3 * 86400`；依 CloudWatch 文件，起點會對齊到分鐘，本次未實測這個寫法）。
- **對帳**：指標總和要等於稽核行筆數（`blocked` 例外，它的 `api_requests` 是 0）。2026-11-25 dev：`javacat`＋`oppay` 2＋3＝5（稽核行 5）、`ragdoll` 1＋4＝5（稽核行 5）。
- 列出某環境有哪些維度組合：`ListMetrics`，`Namespace='API_monitor'`、`MetricName='api_requests'`、`Dimensions=[{'Name': 'env', 'Value': <env>}]`，再保留維度名含 `caller` 或 `service` 的（一次跑完腳本已含）。

## 一次跑完腳本（開工先跑這個）

部署狀態、log 保留天數、稽核行分布、隱私掃描、指標維度組合、告警是否存在，三個環境一次拿齊。**2026-11-25 實跑成功。** `ENVS` 與 `DAYS` 可改。

```python
region = 'ap-northeast-1'
ENVS = ['dev', 'staging', 'production']
DAYS = 7
now = int(time.time())
start = now - DAYS * 86400
AUDIT = "filter ispresent(_aws.Timestamp)"

async def run_query(group, label, qs):
    s = await call_boto3(service_name='logs', operation_name='StartQuery', region_name=region,
                         params={'logGroupName': group, 'startTime': start, 'endTime': now, 'queryString': qs})
    qid = s.get('queryId')
    res = None
    for i in range(60):
        await asyncio.sleep(2)
        res = await call_boto3(service_name='logs', operation_name='GetQueryResults', region_name=region, params={'queryId': qid})
        if res.get('status') in ('Complete', 'Failed', 'Cancelled', 'Timeout'):
            break
    out = ['[%s] %s: status=%s matched=%s' % (group.split('/')[-1], label, res.get('status'), res.get('statistics', {}).get('recordsMatched'))]
    for row in res.get('results', []):
        out.append('   ' + ' | '.join('%s=%s' % (c.get('field'), str(c.get('value'))[:40]) for c in row if c.get('field') != '@ptr'))
    return out

SCANS = [
    ('憑證字樣', "(@message like /Authorization/ or @message like /[Bb]earer/ or @message like /[Tt]oken/ or @message like /[Ss]ecret/ or @message like /[Ss]ignature/)"),
    ('未遮罩門號', "@message like /09[0-9]{8}/"),
    ('身分證格式', "@message like /[A-Z][12][0-9]{8}/"),
    ('個資欄位名', "@message like /\"(buyer|shipping|name|address|email|barcode|url)\"/"),
    ('網址', "@message like /https?:\\/\\//"),
]

async def env_report(env):
    group = '/ecs/van-' + env
    out = ['========== %s ==========' % env]
    r = await call_boto3(service_name='ecs', operation_name='DescribeServices', region_name=region, params={'cluster': 'van-' + env, 'services': ['van-' + env]})
    for s in r.get('services', []):
        for d in s.get('deployments', []):
            out.append('部署 %s rollout=%s td=%s created=%s' % (d.get('status'), d.get('rolloutState'), d.get('taskDefinition', '').split('/')[-1], str(d.get('createdAt'))[:19]))
    lg = await call_boto3(service_name='logs', operation_name='DescribeLogGroups', region_name=region, params={'logGroupNamePrefix': group})
    for g in lg.get('logGroups', []):
        if g.get('logGroupName') == group:
            out.append('log 保留天數=%s' % g.get('retentionInDays'))
    out.extend(await run_query(group, '稽核紀錄分布(%dd)' % DAYS, AUDIT + " | stats count(*) as n, min(@timestamp) as first_at, max(@timestamp) as last_at by direction, caller, service, action, outcome | sort n desc | limit 50"))
    scan_results = await asyncio.gather(*[run_query(group, '隱私掃描-' + label, AUDIT + " and " + cond + " | stats count(*) as n") for label, cond in SCANS])
    for rr in scan_results:
        out.extend(rr)
    m = await call_boto3(service_name='cloudwatch', operation_name='ListMetrics', region_name=region,
                         params={'Namespace': 'API_monitor', 'MetricName': 'api_requests', 'Dimensions': [{'Name': 'env', 'Value': env}]})
    lines = []
    for x in m.get('Metrics', []):
        names = [d.get('Name') for d in x.get('Dimensions', [])]
        if 'caller' in names or 'service' in names:
            lines.append(','.join('%s=%s' % (d.get('Name'), d.get('Value')) for d in x.get('Dimensions', []) if d.get('Name') != 'env'))
    out.append('API_monitor api_requests 維度組合(%d): %s' % (len(lines), ' ; '.join(sorted(lines))))
    a = await call_boto3(service_name='cloudwatch', operation_name='DescribeAlarms', region_name=region, params={'AlarmNames': ['van-%s-upstream-failures' % env]})
    out.append('告警 van-%s-upstream-failures: %s' % (env, ','.join('%s state=%s' % (x.get('AlarmName'), x.get('StateValue')) for x in a.get('MetricAlarms', [])) or '不存在'))
    return out

results = await asyncio.gather(*[env_report(e) for e in ENVS], return_exceptions=True)
report = []
for r in results:
    report.extend(['ERR ' + str(r)] if isinstance(r, Exception) else r)
'\n'.join(report)
```

讀法：

- 某環境「部署」的 `td` 還是舊版（例如 `van-staging:4`、`created` 在新功能合併之前）且稽核行是 0 筆 → 那個環境還沒部署新版，0 筆是預期。
- 「稽核行」有筆數但「指標維度組合」是 0 → 查指標的環境維度值、namespace 與區域；有指標沒稽核行 → 看 log 保留期是不是已過期。
- 「告警」不存在：dev 是設計如此；staging、production 是 Terraform 還沒 apply（人工執行）。
- 掃描有命中時，**先不要貼內容**：改用 `fields @timestamp, direction, service, action` 只取分類欄位定位是哪一筆，再對照白名單判斷是哪個欄位漏出來。
