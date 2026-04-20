# 錯誤重試與取消策略

## 錯誤來源

待辦工作的錯誤分為兩種：

### 1. 函數回傳 ERROR

函數腳本主動回傳 `{ status: 'ERROR', result: '...' }`，代表業務邏輯層面的錯誤。

### 2. 系統內部錯誤（Exception）

函數執行過程中拋出未捕獲的例外。Worker 會在 catch 區塊中處理：

```typescript
catch (err: unknown) {
  workingJob.body.status = TodoJobStatus.ERROR;
  workingJob.body.errorCount = (workingJob.body.errorCount ?? 0) + 1;
}
```

另外，`executeOneTodoJob` 中如果 Sandbox 執行拋出例外，也會被正規化為 ERROR：

```typescript
catch (err: unknown) {
  await this.docdb.txAbort(session);
  return {
    status: TodoJobStatus.ERROR,
    result: err instanceof Error ? err.message : err + '',
  };
}
```

## onJobRetry 重試設定

每個表格函數定義中可設定 `onJobRetry`，控制錯誤重試策略：

```typescript
// 在表格定義的 functions 中
{
  name: '處理批次作業',
  script: readCompiledScript(...),
  onJobRetry: 3,  // 允許連續錯誤 3 次
}
```

| onJobRetry 值 | 行為 |
|--------------|------|
| `0`（預設） | 第一次錯誤就從佇列移除 |
| `N`（正整數） | 允許連續錯誤 N 次後才移除（`errorCount >= onJobRetry + 1` 時移除） |
| `-1` | 永遠不因錯誤而移除 |

## execCount 執行次數上限

不論錯誤重試如何設定，每筆工作都有全域的執行次數上限 `EXECUTE_COUNT_LIMIT = 200`：

```typescript
if (workingJob.body.execCount > EXECUTE_COUNT_LIMIT) {
  workingJob.body.status = TodoJobStatus.CANCELLED;
  jobExecCtx.removeReason = `執行次數已達上限 ${EXECUTE_COUNT_LIMIT} 次，系統自動取消此工作`;
}
```

到達上限時，工作會被強制取消並移除。這是防止有問題的工作無限期佔用系統資源的保護機制。

> **注意**：如果你的多階段處理可能超過 200 次迭代，必須使用 `Utils.saftyKeepTodoJobWorking` 來建立新工作接替，避免被自動取消。

## 連續錯誤次數（errorCount）

`errorCount` 追蹤的是**連續**錯誤次數，會在成功時歸零：

```typescript
if (todoJobReturn.status === TodoJobStatus.ERROR) {
  workingJob.body.errorCount = (workingJob.body.errorCount ?? 0) + 1;
} else if (
  todoJobReturn.status === TodoJobStatus.IDLE ||
  todoJobReturn.status === TodoJobStatus.WORKING ||
  todoJobReturn.status === TodoJobStatus.DONE
) {
  workingJob.body.errorCount = 0;  // 成功歸零
}
// CANCELLED 和 PENDING 不變動 errorCount
```

## 函數不存在的處理

如果待辦工作對應的函數腳本不存在（被刪除或更名）：

1. 如果工作狀態是 `CANCELLED` 或 `ERROR` → 直接移除
2. 其他狀態 → 拋出 `AssertionError`，中斷該佇列的執行，並發送 Chat 通知

## Commit / Rollback 行為

`executeOneTodoJob` 中，交易的 commit/rollback 行為取決於函數回傳：

```typescript
let shouldCommit = true;

// 1. 函數明確指定 commit
if (typeof todoJobReturn.commit === 'boolean') {
  shouldCommit = todoJobReturn.commit;
}
// 2. ERROR 狀態預設 rollback
else if (todoJobReturn.status === TodoJobStatus.ERROR && !todoJobReturn.disableRollback) {
  shouldCommit = false;
}

if (shouldCommit) {
  await this.docdb.txCommit(session);
} else {
  await this.docdb.txAbort(session);
}
```

### 各狀態的預設 commit 行為

| 狀態 | 預設行為 | 說明 |
|------|---------|------|
| `DONE` | commit | 工作成功完成 |
| `WORKING` | commit | 本階段成功，資料庫變更應保留 |
| `CANCELLED` | commit | 取消但已做的變更保留 |
| `ERROR` | **rollback** | 錯誤時預設回滾 |
| `IDLE` | commit | - |
| `PENDING` | commit | - |

### 覆蓋 commit 行為

函數可以回傳 `commit: false` 來強制 rollback（即使狀態是 WORKING）：

```typescript
return {
  status: 'WORKING',
  result: '驗證階段完成，不需要寫入',
  buffer: JSON.stringify(nextBuffer),
  commit: false,  // 本階段只做驗證，不需要 commit
};
```

也可以回傳 `commit: true` 讓 ERROR 狀態的變更被保留：

```typescript
return {
  status: 'ERROR',
  result: '部分資料已處理',
  commit: true,  // 即使錯誤，已處理的資料也要保留
};
```

> **注意**：`disableRollback` 是 `commit` 的前身（已棄用）。`disableRollback: true` 等同於 `commit: true`。如果同時定義 `commit` 和 `disableRollback`，以 `commit` 優先。
