# keepQueue 佇列控制機制

## 用途

`keepQueue` 控制的是：**當前這筆待辦工作執行完畢後，Worker 是否繼續處理同一個佇列中的下一筆工作**。

- `keepQueue = true`：繼續執行佇列中的下一筆工作（或同一筆的下一階段）
- `keepQueue = false`：放棄當前佇列，Worker 去處理排程中的下一個佇列

注意：keepQueue 只影響 Worker 是否**繼續在同一個佇列中處理**，不影響工作是否被移除。移除由 `removeReason` 決定（取決於狀態）。

## 預設值邏輯

如果函數沒有明確回傳 `keepQueue`，系統會根據狀態給予預設值：

```typescript
if (jobExecCtx.keepQueue === undefined) {
  jobExecCtx.keepQueue =
    workingJob.body.status === TodoJobStatus.ERROR ||
    workingJob.body.status === TodoJobStatus.PENDING ||
    workingJob.body.status === TodoJobStatus.IDLE
      ? false
      : true;
}
```

| 狀態 | 預設 keepQueue | 原因 |
|------|--------------|------|
| `WORKING` | `true` | 多階段遞迴，需要繼續處理 |
| `DONE` | `true` | 工作完成後繼續處理佇列中的下一筆 |
| `ERROR` | `false` | 發生錯誤時避免立即重試浪費資源 |
| `PENDING` | `false` | 暫停狀態，沒必要繼續佔用佇列 |
| `IDLE` | `false` | 重設狀態，讓出佇列 |
| `CANCELLED` | `true` | 取消的工作會被移除，佇列繼續處理其他工作 |

## 已棄用的 disableBurst

`disableBurst` 是 `keepQueue` 的反義前身：

```typescript
keepQueue = typeof jobResult.keepQueue === 'boolean'
  ? jobResult.keepQueue
  : typeof jobResult.disableBurst === 'boolean'
    ? !jobResult.disableBurst
    : undefined;
```

優先使用 `keepQueue`。如果兩者都未定義，由預設邏輯決定。

## keepQueue 與移除的交互

keepQueue 只在工作**未被移除**的情況下才有意義。流程如下：

```
函數執行完畢
  ├─ removeReason 非空 → 移除工作，不看 keepQueue，繼續 while 迴圈
  └─ removeReason 為空 → 保留工作
       ├─ ERROR 且 keepQueue=false → break（放棄佇列）
       ├─ keepQueue=false → break（放棄佇列）
       └─ keepQueue=true → continue（繼續 while 迴圈）
```

## 使用場景

### 場景 1：多階段處理（WORKING + keepQueue=true）

```typescript
return {
  status: 'WORKING',
  result: '處理中',
  buffer: JSON.stringify(nextStage),
  keepQueue: true,  // 預設就是 true，可省略
};
```

### 場景 2：暫停等待外部資源（PENDING + keepQueue=false）

```typescript
return {
  status: 'PENDING',
  result: '等待外部 API 回應',
  delaySeconds: 60,
  keepQueue: false,  // 預設就是 false，可省略
};
```

### 場景 3：錯誤但想立即重試（ERROR + keepQueue=true）

```typescript
return {
  status: 'ERROR',
  result: '暫時性錯誤',
  keepQueue: true,  // 覆蓋預設的 false，讓 Worker 立即重試
};
```

### 場景 4：完成但不想佔用佇列（DONE + keepQueue=false）

```typescript
return {
  status: 'DONE',
  result: '完成但此工作佔用太多時間',
  keepQueue: false,  // 覆蓋預設的 true，讓佇列讓給其他佇列
};
```
