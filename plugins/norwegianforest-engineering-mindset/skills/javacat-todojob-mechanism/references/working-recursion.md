# WORKING 遞迴執行機制

## 核心概念

當待辦工作函數回傳 `status: 'WORKING'` 時，代表「本次階段成功完成，但整體工作尚未結束，請繼續執行」。Worker 會將該工作**保留在佇列中**，並在同一個 while 迴圈的下一輪迭代中再次取出並執行。

這形成了一個**遞迴執行**模式：同一筆待辦工作會被反覆執行，每次處理一個階段，直到回傳 `DONE` 或其他終止狀態為止。

## 執行流程

```
while (未超時) {
  workingJob = fetchOneTodoJob()  // 取出工作（可能取到同一筆）
  if (!workingJob) break;

  // 設定 status = WORKING 並寫入 DB
  result = executeOneTodoJob()    // 執行函數

  if (result.status === 'WORKING') {
    // 保留在佇列中，更新 buffer
    // keepQueue 預設 true → 繼續 while 迴圈
    // → 下一輪會再次取到這筆工作
  }
  if (result.status === 'DONE') {
    // 從佇列移除，while 繼續處理下一筆工作
  }
}
```

## 多階段處理模式

WORKING 遞迴最常見的用途是**多階段批次處理**。每個階段透過 `buffer` 傳遞進度和狀態：

```typescript
// 第一次執行
const main: FunctionScript<...> = async (record, _, ctx) => {
  const buffer = JSON.parse(ctx.todoJob?.body.buffer || 'null');

  if (!buffer) {
    // 階段 1：初始化
    return {
      status: 'WORKING',
      result: '初始化完成',
      buffer: JSON.stringify({ stage: '處理資料', startIndex: 0 }),
    };
  }

  if (buffer.stage === '處理資料') {
    // 階段 2：批次處理資料
    const endIndex = Math.min(buffer.startIndex + 100, totalRows);
    // ... 處理 startIndex ~ endIndex 的資料 ...

    if (endIndex >= totalRows) {
      return { status: 'DONE', result: '全部完成' };
    }
    return {
      status: 'WORKING',
      result: `已處理 ${endIndex}/${totalRows}`,
      buffer: JSON.stringify({ stage: '處理資料', startIndex: endIndex }),
    };
  }
};
```

## saftyKeepTodoJobWorking 安全工具

定義在 `NorwegianForest/tables/common/utils.ts`，用來防止單一待辦工作佔用佇列過久。

### 問題背景

當一筆工作持續回傳 `WORKING` 時，`execCount` 會不斷累加。如果達到 `EXECUTE_COUNT_LIMIT`（200 次），系統會自動取消該工作。但在此之前，如果工作已經執行了很多次仍未完成，可能代表有問題。

### 解決方案

`saftyKeepTodoJobWorking` 在 `execCount` 達到指定上限（預設 100）時，不是直接繼續回傳 WORKING，而是**建立一筆新的待辦工作**來接替：

```typescript
async function saftyKeepTodoJobWorking(
  ctx: Context,
  functionReturn: TodoJobFunctionReturn,
  limitExecCount = 100
): Promise<TodoJobFunctionReturn> {
  const execCount = ctx.todoJob?.body.execCount || 0;

  // 還沒到上限，或不是 WORKING 狀態，直接回傳
  if (functionReturn.status !== 'WORKING' || execCount < limitExecCount) {
    return functionReturn;
  }

  // 到達上限：建立新的待辦工作，繼承 buffer、targetName 等
  const [nextTodoJobId] = await ctx.query.todoJobsV2({
    method: 'todoJobsV2',
    data: [{
      body: {
        tableName,
        functionName: todoJob.body.functionName,
        source: todoJob.body.source,
        param: todoJob.body.param,
        buffer: functionReturn.buffer,  // 繼承 buffer
        queueNo: todoJob.body.queueNo,
        status: 'WORKING',
      },
      lines: { items: targetName ? [{ targetName }] : [] },
    }],
  });

  // 當前工作回傳 DONE（會被移除），新工作接替繼續執行
  return { status: 'DONE', result: `${functionReturn.result} & keep working - ${nextTodoJobId}` };
}
```

### 使用方式

在函數腳本中，不直接回傳 `{ status: 'WORKING', ... }`，而是透過此工具：

```typescript
return Utils.saftyKeepTodoJobWorking(ctx, {
  status: 'WORKING',
  result: '已處理 500/10000 筆',
  buffer: JSON.stringify(nextBuffer),
});
```

### 為什麼需要它

1. **避免 execCount 達到 200 被自動取消**：新工作 execCount 從 0 開始
2. **避免單筆工作佔用佇列過久**：新工作會重新排隊
3. **安全地延續多階段處理**：buffer 完整繼承，不中斷流程

## 實際案例：批次作業（batchmutation/process.ts）

批次作業函數展示了完整的多階段 WORKING 遞迴：

```
階段 1: 更新處理狀態 → WORKING
  ↓ (buffer 帶入 fileURL, stage)
階段 2: 資料操作合法性驗證 → WORKING (分批驗證)
  ↓ (buffer 帶入 avgTimeMs, errors)
階段 3: 資料操作處理 → WORKING (分批操作)
  ↓ (buffer 帶入 errors, 進度)
階段 4: 操作完成 → DONE
```

每個階段都透過 `Utils.saftyKeepTodoJobWorking` 回傳，確保長時間批次處理不會被系統取消。
