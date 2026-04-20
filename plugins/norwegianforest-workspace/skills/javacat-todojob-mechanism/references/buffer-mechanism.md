# Buffer 傳遞機制

## 用途

`buffer` 是待辦工作的**跨執行階段暫存區**。每次函數執行完畢後，可以將資料寫入 buffer，下次執行同一筆工作時，函數可以從 `ctx.todoJob?.body.buffer` 讀取上次寫入的 buffer 內容。

## 傳遞流程

```
第 1 次執行:
  ctx.todoJob.body.buffer = null    ← 首次執行，buffer 為空
  return { status: 'WORKING', buffer: JSON.stringify({ stage: 'A', data: ... }) }

                ↓ Worker 將回傳的 buffer 寫入 DB

第 2 次執行:
  ctx.todoJob.body.buffer = '{"stage":"A","data":...}'    ← 上次寫入的 buffer
  return { status: 'WORKING', buffer: JSON.stringify({ stage: 'B', progress: ... }) }

                ↓ Worker 將回傳的 buffer 寫入 DB

第 N 次執行:
  ctx.todoJob.body.buffer = '{"stage":"B","progress":...}'
  return { status: 'DONE', result: '完成' }
```

## Worker 端的處理

在 `todoJob.ts` 中，Worker 會將函數回傳的 buffer 寫回待辦工作紀錄：

```typescript
// 執行函數後
workingJob.body.buffer = todoJobReturn.buffer;

// 保留工作時，更新 DB（setJob 會寫入 buffer）
await this.setJob({ todoJob: workingJob, awsRequestId });
```

`setJob` 中只有 buffer **有值**時才會更新：

```typescript
$set: {
  ...(buffer ? { 'body.buffer': buffer } : null),
}
```

## 使用方式

### 讀取 buffer

```typescript
const main: FunctionScript<...> = async (record, _, ctx) => {
  const buffer: MyBuffer | null = JSON.parse(ctx.todoJob?.body.buffer || 'null');

  if (!buffer) {
    // 第一次執行，初始化
  } else if (buffer.stage === 'xxx') {
    // 根據 stage 執行對應邏輯
  }
};
```

### 寫入 buffer

```typescript
return {
  status: 'WORKING',
  result: '階段完成',
  buffer: JSON.stringify({
    stage: '下一階段',
    startIndex: 100,
    errors: [],
  }),
};
```

## 限制與注意事項

### 1. 必須是字串

buffer 欄位型別是 `string`，所有資料必須 `JSON.stringify` 序列化。讀取時需要 `JSON.parse` 反序列化。

### 2. 大小限制

buffer 儲存在 DocumentDB 文件中，受限於單一文件 16MB 的限制。實務上應避免在 buffer 中存放大量資料，建議：
- 只存放**進度指標**（如 `startIndex`、`stage`）和**少量中繼資料**
- 大量資料應存在外部（如 S3 檔案），buffer 中只存 URL 或參考

### 3. 空 buffer 不會清除

`setJob` 中 `buffer` 為 falsy 時不會更新 DB。這表示：
- 回傳 `buffer: ''`（空字串）不會清除既有 buffer（因為空字串是 falsy）
- 回傳 `buffer: undefined`（或不帶 buffer 欄位）也不會清除
- 如果需要「清除」buffer 的效果，通常是在最後回傳 `DONE` 讓工作被移除

### 4. saftyKeepTodoJobWorking 會繼承 buffer

當使用 `Utils.saftyKeepTodoJobWorking` 建立新工作時，buffer 會被完整複製到新工作中，確保多階段流程不中斷。

## 設計模式：Stage-based Buffer

最常見的 buffer 使用模式是「階段式」設計，以一個 `stage` 欄位作為流程控制：

```typescript
type StageBuffer =
  | { stage: '更新處理狀態' }
  | { stage: '資料驗證'; fileURL: string; startRowIndex: number }
  | { stage: '資料處理'; fileURL: string; startRowIndex: number; batchLimit: number }
  | { stage: '操作完成'; errors: string[] };
```

函數根據 `buffer.stage` 決定要執行哪一段邏輯，並在完成後更新 stage 進入下一階段：

```typescript
const buffer: StageBuffer | null = JSON.parse(ctx.todoJob?.body.buffer || 'null');

if (!buffer || buffer.stage === '更新處理狀態') {
  // ... 初始化 ...
  return Utils.saftyKeepTodoJobWorking(ctx, {
    status: 'WORKING',
    buffer: JSON.stringify({ stage: '資料驗證', fileURL, startRowIndex: 0 }),
  });
}

if (buffer.stage === '資料驗證') {
  // ... 分批驗證 ...
  if (allValidated) {
    return Utils.saftyKeepTodoJobWorking(ctx, {
      status: 'WORKING',
      buffer: JSON.stringify({ stage: '資料處理', fileURL, startRowIndex: 0, batchLimit }),
    });
  }
  return Utils.saftyKeepTodoJobWorking(ctx, {
    status: 'WORKING',
    buffer: JSON.stringify({ ...buffer, startRowIndex: nextIndex }),
  });
}
```
