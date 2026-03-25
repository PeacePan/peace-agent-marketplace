# batchPolicy 的 INSERT vs UPDATE 情境

## 核心機制

`triggerBatchPolicy` 的呼叫方式決定腳本收到的 `oldRecords`：

```typescript
// JavaCat/src/lib2/MyModel/MyModel.ts

// INSERT 情境（batchInsertV2，line ~2672）
if (!input.ignorePolicy)
  await this.triggerBatchPolicy(newRecords, session, currentUser);
// arguments 傳入：[newRecords]
// → script 接收：records = newRecords，oldRecords = undefined

// UPDATE 情境（batchUpdateV2，line ~3319）
if (!input.ignorePolicy)
  await this.triggerBatchPolicy(alignedOldRecords, session, currentUser, alignedUpdatedRecords);
// arguments 傳入：[updatedRecords, oldRecords]
// → script 接收：records = updatedRecords，oldRecords = alignedOldRecords
```

## 在腳本中判斷情境

```typescript
const main: BatchPolicyScript<SafeRecord2<MyTableBody>> = async ({ ctx, records, oldRecords }) => {
  const isInsertContext = oldRecords === undefined;
  const isUpdateContext = oldRecords !== undefined;
};
```

## 常見陷阱：INSERT 情境中的「變動」判斷

batchPolicy 常見邏輯：「找出數量有變動的紀錄，更新相關表格」。但在 INSERT 情境下，`oldRecords` 為 `undefined`，這個判斷會讓所有紀錄都被視為「有變動」：

```typescript
// ❌ 危險寫法
const quantityChangedDetails = records.filter(record => {
  const oldRecord = oldRecords?.find(old => old.body.name === record?.body.name);
  // INSERT 情境：oldRecord 永遠是 undefined
  // !oldRecord = true → 所有 records 都通過篩選
  return !!(record && (!oldRecord || oldRecord.body.quantity !== record?.body.quantity));
});

if (dsvOrderNames.length) {
  // INSERT 情境：這裡會觸發所有 dsvOrderNames 的 policy，造成冗餘執行
  await ctx.query.batchUpdateV2<DSVOrderBody>({ ... });
}
```

```typescript
// ✅ 正確寫法：明確排除 INSERT 情境
const quantityChangedDetails = records.filter(record => {
  const oldRecord = oldRecords?.find(old => old.body.name === record?.body.name);
  return !!(record && (!oldRecord || oldRecord.body.quantity !== record?.body.quantity));
});

// 加上 && oldRecords 條件，INSERT 情境直接跳過
if (dsvOrderNames.length && oldRecords) {
  await ctx.query.batchUpdateV2<DSVOrderBody>({ ... });
}
```

## INSERT 情境需要特殊處理的另一個原因

INSERT 新建的紀錄在後續的 `policy` / `batchPolicy` 中，它的「初始狀態」本身已觸發必要的更新（例如 dsvorderdetail INSERT → upsertDSVOrder 已處理了 dsvorder 的更新）。在 INSERT 的 batchPolicy 中再度觸發同樣的 policy 通常是冗餘的，且可能造成效能問題。

## 相關的實際修正記錄

`dsvorderdetail/batchPolicy.ts` 中的 `quantityChangedDetails` 區塊曾因此問題導致 WH 調撥單 push 一筆表身列就超過 50 秒逾時。修正方式即為加上 `&& oldRecords` 條件（見 [transferorder-wh-lifecycle.md](transferorder-wh-lifecycle.md)）。
