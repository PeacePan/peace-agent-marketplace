# ECS、ALB target、告警狀態腳本

已在 `aws-mcp` 的 `run_script` 驗證可跑（2026-11-18）。用法：整段貼進 `run_script` 的 `code`。

**寫法上刻意只回傳純字串與清單，不用巢狀的自訂 dict**——原因見 `aws-mcp-pitfalls.md`（驗證器會把自訂鍵名誤判成 API 回應欄位）。

```python
region = 'ap-northeast-1'
envs = [('dev', 'van-dev'), ('staging', 'van-staging'), ('production', 'van-production')]

async def svc_info(env, name):
    r = await call_boto3(service_name='ecs', operation_name='DescribeServices', region_name=region,
                         params={'cluster': name, 'services': [name]})
    lines = []
    tg_list = []
    for f in r.get('failures', []):
        lines.append('ECS failure: ' + str(f))
    for s in r.get('services', []):
        lines.append('status=%s desired=%s running=%s pending=%s' % (s.get('status'), s.get('desiredCount'), s.get('runningCount'), s.get('pendingCount')))
        lines.append('taskDef=' + str(s.get('taskDefinition')))
        for d in s.get('deployments', []):
            lines.append('deploy %s rollout=%s desired=%s running=%s failed=%s created=%s' % (
                d.get('status'), d.get('rolloutState'), d.get('desiredCount'), d.get('runningCount'), d.get('failedTasks'), d.get('createdAt')))
        for e in s.get('events', [])[:4]:
            lines.append('event %s | %s' % (e.get('createdAt'), e.get('message')))
        for lb in s.get('loadBalancers', []):
            if lb.get('targetGroupArn'):
                tg_list.append(lb.get('targetGroupArn'))
    return env, lines, tg_list

async def tg_info(tg):
    th = await call_boto3(service_name='elbv2', operation_name='DescribeTargetHealth', region_name=region,
                          params={'TargetGroupArn': tg})
    rows = []
    for t in th.get('TargetHealthDescriptions', []):
        h = t.get('TargetHealth', {})
        rows.append('%s az=%s state=%s reason=%s desc=%s' % (t.get('Target', {}).get('Id'), t.get('Target', {}).get('AvailabilityZone'), h.get('State'), h.get('Reason'), h.get('Description')))
    return tg, rows

async def alarm_info():
    r = await call_boto3(service_name='cloudwatch', operation_name='DescribeAlarms', region_name=region,
                         params={'AlarmNamePrefix': 'van-'})
    return ['%s = %s (%s) updated=%s' % (a.get('AlarmName'), a.get('StateValue'), a.get('StateReason'), a.get('StateUpdatedTimestamp')) for a in r.get('MetricAlarms', [])]

first = await asyncio.gather(*[svc_info(e, n) for e, n in envs], alarm_info(), return_exceptions=True)
report = []
all_tgs = []
for item in first[:3]:
    if isinstance(item, Exception):
        report.append('ERR ' + str(item))
        continue
    env, lines, tgs = item
    report.append('=== ' + env + ' ===')
    report.extend(lines)
    for t in tgs:
        all_tgs.append((env, t))
tg_results = await asyncio.gather(*[tg_info(t) for _, t in all_tgs], return_exceptions=True)
for (env, t), res in zip(all_tgs, tg_results):
    report.append('--- target health [%s] %s' % (env, t.split('/')[-2] if '/' in t else t))
    if isinstance(res, Exception):
        report.append('ERR ' + str(res))
    else:
        report.extend(res[1])
report.append('=== CloudWatch alarms (prefix van-) ===')
if isinstance(first[3], Exception):
    report.append('ERR ' + str(first[3]))
else:
    report.extend(first[3] if first[3] else ['(no alarms found)'])
final_text = '\n'.join(report)
final_text
```

## 讀結果

| 看什麼 | 判讀 |
|---|---|
| `desired` ≠ `running` | 服務在縮放或有任務起不來，看 `events` |
| `rollout=COMPLETED` 且 `failed=0` | 最近一次部署正常 |
| `events` 最新一則 | 應為 `has reached a steady state`；若是 `unable to place` 或 `failed` 開頭，要深查 |
| target `state=healthy` | ALB 健康檢查（打 `/health`）通過 |
| target `state=unhealthy` | 看 `reason` 與 `desc`；`Target.FailedHealthChecks`、`Target.Timeout` 常見 |
| 告警 `OK` | `van-` 告警目前沒觸發；告警的 `StateReason` 可能有看起來嚇人的字樣（缺資料視為 Breaching），以 `StateValue` 為準 |

## 2026-11-18 當時的結果（僅供比對）

dev、staging、production 都是 `ACTIVE`、各 `desired=1 running=1`、部署 `COMPLETED`（自 2026-11-03）、target 皆 `healthy`；production 在 `ap-northeast-1a`。兩個告警皆 `OK`（狀態自 2026-09-21 起未變）。
