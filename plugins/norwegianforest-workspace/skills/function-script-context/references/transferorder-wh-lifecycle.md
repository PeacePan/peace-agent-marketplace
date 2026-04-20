# WH 調撥單 push 表身列的完整觸發鏈

## 背景

WH（總倉調撥）類型的調撥單，當人工 push 一筆表身列時，會觸發一連串的跨表更新。
此鏈路分析源自一個真實的效能問題：push 1 筆表身列導致執行超過 50 秒逾時。

## 問題：修正前的完整觸發鏈

```
[人工操作] push 1 筆表身列
  │
  ├─ [A1] transferorder.batchBeforeUpdate（WH+push 時為 no-op，直接跳過）
  │
  └─ [C1] transferorder.policy
        ├─ 查詢 dsvorder、item、hqcuft
        ├─ updateV2 transferorder（system fields, ignorePolicy）
        └─ upsertDSVOrder()
              ├─ 查詢 dsvorder（重複查詢！）
              ├─ insertV2 dsvorder（若新建）
              ├─ updateV2 transferorder（dsvOrderName, ignorePolicy）
              ├─ 查詢 dsvorderdetail（existedMap）
              │
              ├─ [W4] batchInsertV2 dsvorderdetail（新建明細，無 batchSerial）
              │     └─ [B1] dsvorderdetail.batchPolicy（INSERT，oldRecords=undefined）
              │           ├─ 查詢 dsvorder、transferorder、dsvinventory
              │           ├─ getStoreLocationDSVOrderNames（查詢 transferorder）
              │           ├─ getDSVInTransitInfo（查詢 dsvorderdetail + dsvorder）
              │           ├─ [W6] batchUpdateV2 dsvorderdetail（填批號/效期，ignorePolicy:true）
              │           │
              │           ├─ [W7] batchUpdateV2 transferorder rowSetUpdates
              │           │      （ignorePolicy:true，user 帶 isFromDSVOrderDetailBatchPolicy:true）
              │           │       └─ [A2] transferorder.batchBeforeUpdate（偵測到 setLineRows）
              │           │               ├─ 查詢 dsvorderdetail（for dsvOrderDetailMap）
              │           │               ├─ [W10] batchUpdateV2 dsvorderdetail（同步數量，ignorePolicy:true）
              │           │               │        [修正前 ignorePolicy:undefined → 觸發 B2]
              │           │               │        [B2 → quantityChangedDetails → W12 → D3 ❌冗餘]
              │           │               └─ [W11] batchUpdateV2 dsvorder（updatedAtByTransferOrder）
              │           │                        [修正後：偵測 isFromDSVOrderDetailBatchPolicy → 跳過]
              │           │                        [修正前：觸發 D4 ❌冗餘]
              │           │
              │           └─ [W9] batchUpdateV2 dsvorder（totalQuantity:0）
              │                   [修正後：oldRecords=undefined → 跳過]
              │                   [修正前：觸發 D1 ❌冗餘]
              │
              └─ [W5] updateV2 dsvorder（updatedAtByTransferOrder）← 這是必要的！
                      └─ [D2] dsvorder.policy ✅ 唯一必要執行
                              ├─ 查詢 dsvorderdetail（此時已有完整數量）
                              ├─ getDSVInventoryAmounts
                              ├─ getDSVInTransitInfo
                              ├─ getStoreLocationDSVOrderNames × 2
                              └─ updateV2 dsvorder（最終結果）
```

## 修正前的問題

`dsvorder.policy` 被觸發 4 次（D1、D2、D3、D4），每次包含 6~8 個 DB 查詢：

| 觸發 | 來源 | 是否必要 |
|-----|-----|---------|
| D1 | B1 的 `quantityChangedDetails` 更新 dsvorder | ❌ 冗餘（D2 在 B1 完成後才執行，能看到最終狀態） |
| D2 | W5 的 `updateV2 dsvorder (updatedAtByTransferOrder)` | ✅ 必要 |
| D3 | B2（由 A2 的 dsvorderdetail 更新觸發，ignorePolicy:undefined） | ❌ 冗餘 |
| D4 | A2 的 `batchUpdateV2 dsvorder (updatedAtByTransferOrder)` | ❌ 冗餘 |

**為什麼 D2 能涵蓋 D1/D3/D4？**

執行順序：W4 → B1（完整執行含 A2）→ W5 → D2

D2 在所有更新（包含 B1 內的 A2）完全結束後才執行，此時 dsvorderdetail 已是最終狀態，D2 計算的結果是正確的。

## 三個修正點

### Fix 1：A2 更新 dsvorderdetail 時硬寫 ignorePolicy:true
**位置**：`transferorder/batchBeforeUpdate.ts`

```typescript
// 修正前：ignorePolicy 依賴 userContent.ignoreDSVOrderDetailPolicy，人工觸發時為 undefined → 觸發 B2
ignorePolicy: typeof userContent === 'object' && userContent && 'ignoreDSVOrderDetailPolicy' in userContent
    ? userContent.ignoreDSVOrderDetailPolicy
    : void 0,

// 修正後：硬寫 true，消除 B2 → D3
ignorePolicy: true,
```

**效果**：消除 D3

### Fix 2：B1 rowSetUpdates 帶旗標，A2 偵測後跳過 dsvorder 更新
**位置 A**：`dsvorderdetail/batchPolicy.ts`

```typescript
user: JSON.stringify({
    ...userContent,
    functions: userContent.functions?.filter(fn => fn !== '總倉自動調撥'),
    isFromDSVOrderDetailBatchPolicy: true,  // ← 加入旗標
}),
```

**位置 B**：`transferorder/batchBeforeUpdate.ts`

```typescript
// 拆分原本的 .then() 鏈
await ctx.query.batchUpdateV2<DSVOrderDetailBody>({ ..., ignorePolicy: true });

if (!userContent.isFromDSVOrderDetailBatchPolicy) {
    await ctx.query.batchUpdateV2<DSVOrderBody>({
        body: { totalQuantity: 0, updatedAtByTransferOrder: new Date() },
        ...
    });
}
```

**效果**：消除 D4

### Fix 3：B1 quantityChangedDetails 排除 INSERT 情境
**位置**：`dsvorderdetail/batchPolicy.ts`

```typescript
// 修正前
if (dsvOrderNames.length) { ... }

// 修正後：INSERT 情境（oldRecords=undefined）跳過
if (dsvOrderNames.length && oldRecords) { ... }
```

**效果**：消除 D1

## 修正後的效能對比

| 指標 | 修正前 | 修正後 |
|-----|-------|-------|
| dsvorder.policy 執行次數 | 4 次 | 1 次 |
| DB 查詢總次數 | ~40-50 次 | ~20-25 次 |
| 執行時間 | >50 秒（逾時） | ~15-20 秒 |
| 預期加速 | — | ~4x |
