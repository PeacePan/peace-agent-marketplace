# 案例研究：WH 調撥單 push 表身列的冗餘觸發分析

## 問題描述

**系統**：NorwegianForest（內部 ERP）
**操作**：人工對 WH（總倉調撥）類型的調撥單 push 1 筆表身列
**症狀**：執行時間 >50 秒，超過 Sandbox VM 的 50 秒觸發警戒線（最高 120 秒 timeout）
**根因**：`dsvorder.policy`（每次 6~8 個 DB 查詢）被觸發 4 次

---

## Step 1：確認操作邊界

```
人工 → batchUpdateV2 transferorder（push 1 筆 items）
```

## Step 2 & 3：完整觸發鏈（修正前）

```
[人工操作] batchUpdateV2 transferorder（push）
  │
  ├─ [A1] transferorder.batchBeforeUpdate
  │     WH + 純 push：沒有 setLineRows → dsvDetailUpdate 為空 → no-op
  │
  └─ [C1] transferorder.policy（ignorePolicy:false）
          ├─ findV2 dsvorder × 2（重複查詢）
          ├─ findAll item, hqcuft
          ├─ updateV2 transferorder（system fields, ignorePolicy:true）
          └─ upsertDSVOrder()
                ├─ insertV2 dsvorder（建立新的）
                ├─ updateV2 transferorder（dsvOrderName, ignorePolicy:true）
                ├─ findAll dsvorderdetail（existedMap）
                │
                ├─ [W4] batchInsertV2 dsvorderdetail（無批號）
                │       ↓（ignorePolicy:false → INSERT 觸發 batchPolicy）
                │       [B1] dsvorderdetail.batchPolicy（oldRecords=undefined）
                │             ├─ findAll dsvorder, transferorder, dsvinventory
                │             ├─ getStoreLocationDSVOrderNames（findAll transferorder）
                │             ├─ getDSVInTransitInfo（findAll dsvorderdetail + dsvorder）
                │             │
                │             ├─ [W6] batchUpdateV2 dsvorderdetail（填批號，ignorePolicy:true）
                │             │       ↓ batchBeforeUpdate 仍觸發，但 no-op
                │             │
                │             ├─ [W7] batchUpdateV2 transferorder rowSetUpdates
                │             │       （ignorePolicy:true，user 無特殊旗標）
                │             │       ↓ batchBeforeUpdate 仍觸發！
                │             │       [A2] transferorder.batchBeforeUpdate
                │             │             ├─ findAll dsvorderdetail
                │             │             ├─ [W10] batchUpdateV2 dsvorderdetail
                │             │             │         （ignorePolicy:undefined → batchPolicy 觸發）
                │             │             │         [B2] dsvorderdetail.batchPolicy（UPDATE）
                │             │             │               └─ quantityChanged → batchUpdateV2 dsvorder
                │             │             │                   ↓
                │             │             │                   [D3] dsvorder.policy ❌ 冗餘
                │             │             │
                │             │             └─ [W11] batchUpdateV2 dsvorder（updatedAtByTransferOrder）
                │             │                       ↓
                │             │                       [D4] dsvorder.policy ❌ 冗餘
                │             │
                │             └─ [W9] batchUpdateV2 dsvorder（totalQuantity:0）
                │                     oldRecords=undefined → quantityChanged 全部通過！
                │                     ↓
                │                     [D1] dsvorder.policy ❌ 冗餘
                │
                └─ [W5] updateV2 dsvorder（updatedAtByTransferOrder）
                          ↓（此時 B1/A2 全部完成，dsvorderdetail 已有最終數量）
                          [D2] dsvorder.policy ✅ 必要且正確
```

## Step 4：標記必要性

| 觸發 | 標記 | 原因 |
|-----|-----|-----|
| D2（W5 觸發） | ✅ | B1 全部完成後才執行，看到最終狀態，計算正確 |
| D1（W9 觸發） | ❌ | B1 內部，比 D2 更早，結果被 D2 覆蓋；oldRecords=undefined 導致誤觸發 |
| D3（B2/W12 觸發） | ❌ | A2 內部，由 W10 的 batchPolicy 觸發，D2 已涵蓋 |
| D4（W11 觸發） | ❌ | A2 內部，由 batchBeforeUpdate 觸發 dsvorder，D2 已涵蓋 |

## Step 5：最小化修正方案

### Fix 1：消除 D3（B2 被 A2 觸發）

**問題**：A2（batchBeforeUpdate）更新 dsvorderdetail 時 `ignorePolicy: undefined`，觸發 B2
**修正**：`transferorder/batchBeforeUpdate.ts` 硬寫 `ignorePolicy: true`

```typescript
// Before
ignorePolicy: typeof userContent === 'object' && 'ignoreDSVOrderDetailPolicy' in userContent
    ? userContent.ignoreDSVOrderDetailPolicy : void 0,

// After
ignorePolicy: true,
```

### Fix 2：消除 D4（A2 觸發 dsvorder 更新）

**問題**：A2 在 batchBeforeUpdate 中執行了 dsvorder 的 `updatedAtByTransferOrder` 更新
**修正**：B1 傳遞旗標 `isFromDSVOrderDetailBatchPolicy: true`，A2 偵測後跳過 dsvorder 更新

```typescript
// B1（dsvorderdetail/batchPolicy.ts）
user: JSON.stringify({
    ...userContent,
    functions: userContent.functions?.filter(fn => fn !== '總倉自動調撥'),
    isFromDSVOrderDetailBatchPolicy: true,  // ← 新增
}),

// A2（transferorder/batchBeforeUpdate.ts）
if (!userContent.isFromDSVOrderDetailBatchPolicy) {
    await ctx.query.batchUpdateV2<DSVOrderBody>({
        body: { totalQuantity: 0, updatedAtByTransferOrder: new Date() },
        ...
    });
}
```

### Fix 3：消除 D1（B1 的 quantityChanged 誤觸發）

**問題**：B1 是 INSERT 情境，`oldRecords = undefined`，所有 records 都被視為「數量有變動」
**修正**：加上 `&& oldRecords` 條件

```typescript
// Before
if (dsvOrderNames.length) { ... }

// After
if (dsvOrderNames.length && oldRecords) { ... }
```

---

## 修正效果驗證

```
修正前：dsvorder.policy × 4 = ~28-32 次 DB 查詢（僅 policy 部分）
修正後：dsvorder.policy × 1 = ~7-8 次 DB 查詢

總查詢數：~40-50 次 → ~20-25 次
執行時間：>50 秒 → ~15 秒
加速倍數：~4x
```

---

## 可複用的洞察

1. **越晚的觸發越準確**：在鏈路末端的觸發（W5 → D2）比中間的觸發（W9 → D1）更準確，因為它能看到完整的最終狀態。消除中間的冗餘觸發是安全的。

2. **INSERT 情境的特殊性**：`oldRecords = undefined` 時，任何「比較新舊值」的邏輯都要加上 `&& oldRecords` 保護，否則所有 records 都會通過篩選。

3. **旗標的傳遞是阻斷循環的標準手段**：`batchBeforeUpdate` 無法被 `ignorePolicy` 跳過，必須靠旗標讓 hook 自身決定跳過特定邏輯。

4. **修正要最小化**：每個 Fix 只解決一個冗餘點，互不干涉。不要為了圖方便而整個跳過 hook。
