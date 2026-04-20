# 狀態生命週期

## 六種狀態定義

```typescript
enum TodoJobStatus {
  IDLE = 'IDLE',           // 閒置：初始狀態或被重設
  WORKING = 'WORKING',     // 執行中：正在被 Worker 執行
  PENDING = 'PENDING',     // 暫停：等待下次執行（可設延遲）
  ERROR = 'ERROR',         // 錯誤：執行發生錯誤
  DONE = 'DONE',           // 完成：工作已完成
  CANCELLED = 'CANCELLED', // 已取消：被系統或使用者取消
}
```

## 狀態流轉圖

```
                      ┌──────────────────────────────────┐
                      │                                  │
    ┌─────┐     ┌─────▼───┐     ┌──────┐          ┌─────┴────┐
    │ IDLE ├────►│ WORKING ├────►│ DONE │          │ PENDING  │
    └──┬──┘     └────┬────┘     └──────┘          └─────┬────┘
       │             │                                  │
       │             ├─────►┌───────────┐               │
       │             │      │ CANCELLED │               │
       │             │      └───────────┘               │
       │             │                                  │
       │             ├─────►┌───────┐                   │
       │             │      │ ERROR ├───────────────────┘
       │             │      └───┬───┘                   │
       │             │          │                        │
       │             ◄──────────┴────────────────────────┘
       │             │
       └─────────────┘
```

## 進入 WORKING 的條件

Worker 只會在以下狀態下將工作設為 WORKING 並開始執行：

```typescript
if ([TodoJobStatus.IDLE, TodoJobStatus.WORKING, TodoJobStatus.ERROR, TodoJobStatus.PENDING]
  .includes(workingJob.body.status)) {
  workingJob.body.status = TodoJobStatus.WORKING;
}
```

也就是說 `DONE` 和 `CANCELLED` 的工作不會再被執行。

## 各狀態對工作佇列的影響

執行完畢後，Worker 根據狀態決定是否從佇列中**移除**該工作：

| 狀態 | 是否移除 | 說明 |
|------|---------|------|
| `IDLE` | 否（保留） | 重設狀態，保留在佇列中等待下次執行 |
| `WORKING` | 否（保留） | 多階段遞迴中，保留並繼續執行 |
| `PENDING` | 否（保留） | 暫停，保留但可設 `nextPickAt` 延遲取用 |
| `DONE` | **是** | 工作完成，從佇列移除 |
| `CANCELLED` | **是** | 工作取消，從佇列移除 |
| `ERROR` | 視 `onJobRetry` 而定 | 見下方錯誤處理規則 |

### ERROR 狀態的移除判斷

```typescript
if (onJobRetry <= -1) {
  // -1 代表永遠重試，不移除
  removeReason = '';
} else {
  if (errorCount >= onJobRetry + 1) {
    removeReason = `重試次數超過 ${onJobRetry} 次`;
  } else {
    removeReason = '';  // 還有重試機會，不移除
  }
}
```

- `onJobRetry = 0`（預設）：第一次錯誤就移除
- `onJobRetry = 3`：允許連續錯誤 3 次後才移除
- `onJobRetry = -1`：永遠重試，不會被移除

## 連續錯誤次數計算

`errorCount` 追蹤的是**連續**錯誤次數：

| 回傳狀態 | errorCount 變化 |
|---------|----------------|
| `ERROR` | +1 累加 |
| `IDLE` | 歸零（重設） |
| `WORKING` | 歸零（本次 stage 成功） |
| `DONE` | 歸零（全部完成） |
| `CANCELLED` | 不變 |
| `PENDING` | 不變 |

## 使用者中途修改

Worker 在執行完函數後，會重新讀取資料庫中的最新狀態。如果 `_updatedAt` 發生變化（代表使用者在執行期間修改了工作），Worker 會以使用者修改後的最新狀態為準：

```typescript
const latestJob = await this.docdb.get({ ... });
if (!dayjs(latestJob.body._updatedAt).isSame(workingJob.body._updatedAt)) {
  workingJob.body.status = latestJob.body.status;
}
```

這使得運維人員可以在工作執行期間手動將狀態改為 `CANCELLED` 來中止工作。

## PENDING 狀態的延遲取用

當函數回傳 `status: 'PENDING'` 並指定 `delaySeconds` 時，Worker 會計算 `nextPickAt` 時間：

```typescript
if (todoJobReturn.status === TodoJobStatus.PENDING && typeof todoJobReturn.delaySeconds === 'number') {
  workingJob.body.nextPickAt = new Date(Date.now() + todoJobReturn.delaySeconds * 1000);
}
```

`fetchOneTodoJob` 在取工作時，PENDING 狀態的工作只有 `nextPickAt <= now` 才會被取出：

```typescript
filters: [
  { body: { queueNo: ..., status: { $nin: ['PENDING'] } } },           // 非 PENDING 直接取
  { body: { queueNo: ..., status: { $in: ['PENDING'] }, nextPickAt: { $lte: now } } }  // PENDING 要檢查時間
]
```
