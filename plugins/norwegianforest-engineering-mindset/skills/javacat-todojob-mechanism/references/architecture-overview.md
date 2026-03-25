# Worker 排程架構

## 觸發流程

TodoJob Worker 是一個 AWS Lambda 函數，由 EventBridge 定時觸發（通常每分鐘一次）。每次觸發的完整流程如下：

1. **初始化**：`lambdaHandler` → 初始化全域上下文 → 建立 `MyTodoJobScheduleService` 單例
2. **取得佇列清單**：從系統變數表（`__sysvar__`）查詢所有類型為 `todoJob` 的佇列定義
3. **排程調度**：依佇列優先權產生加權隨機排序的執行計劃
4. **逐佇列處理**：依序處理每個佇列，直到 10 分鐘超時

```
EventBridge (每分鐘)
  → Lambda Handler
    → getJobQueueList()      // 從 __sysvar__ 取得佇列
    → genQueueSchedule()     // 加權隨機排序
    → process()              // 主處理迴圈
```

## 佇列優先權調度

每個佇列有 1~10 的優先權值。調度演算法使用**加權隨機**：

```typescript
// 優先權 5 的佇列會被複製 5 次放入候選池
duplicatedByPriority.push(...Array(queue.priority).fill(queue));
// 隨機洗牌後去重，確保高優先權更容易排在前面
return uniqBy(shuffle(duplicatedByPriority), (q) => `${q.tableName}/${q.queueId}`);
```

這不是嚴格的優先權排序，而是一種概率性的調度：優先權越高的佇列被排在前面的機率越大，但不保證一定在前面。

## 佇列佔用機制（樂觀鎖）

為避免多個 Worker 同時處理同一個佇列，使用 `findOneAndUpdate` 實現樂觀鎖：

- **佔用（Running）**：將 `value2`（佔用時間）和 `value3`（awsRequestId）從 `null` 更新為實際值。只有 `value2=null && value3=null` 時才能成功。
- **釋放（Idle）**：將 `value2` 和 `value3` `$unset`，但只有 `value3` 等於自己的 `awsRequestId` 時才能成功。

如果佔用失敗（該佇列正被其他 Worker 執行），則跳過該佇列繼續處理下一個。

## 佇列啟用檢查

Worker 會在兩個時機點檢查佇列是否啟用（`checkSysVarEnabled`）：
1. 進入佇列前
2. 佇列內部每 15 秒檢查一次（`cCheckEnabledInterval`）

如果佇列在【系統變數】中被設為停用，Worker 會放棄該佇列。這個機制讓運維人員可以即時停止特定佇列的執行。

## 超時保護

Worker 有 10 分鐘的最大執行時間（`cMaxExecutionMs`）。在兩個層級都有檢查：
- 外層迴圈：切換到下一個佇列前檢查
- 內層迴圈：取出下一個工作前檢查

超時後會記錄 `E3007_TODO_JOB_TIMEOUT` 錯誤並結束執行。

## 原始碼位置

| 檔案 | 說明 |
|------|------|
| `JavaCat/src/lib2/MyScheduleService/todoJob.ts` | Worker 主程式（`MyTodoJobScheduleService`） |
| `JavaCat/src/lib2/@type/enum.ts` | `TodoJobStatus` 列舉定義 |
| `JavaCat/src/lib2/@type/tables/todoJob.ts` | `TodoJobBody`、`TodoJobRecord` 型別 |
| `JavaCat/src/lib2/@type/MyScript.ts` | `TodoJobFunctionReturn` 型別 |
| `JavaCat/src/lib2/@type/const.ts` | `EXECUTE_COUNT_LIMIT = 200` |
