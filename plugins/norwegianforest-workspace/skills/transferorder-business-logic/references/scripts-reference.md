# 調撥單腳本參考

## 腳本清單

路徑：`NorwegianForest/tables/inventory/scripts/transferorder/`

| 腳本 | 類型 | 用途 |
|-----|-----|------|
| `policy.ts` | policy | 建立/更新調撥單時的主要業務邏輯 |
| `batchBeforeUpdate.ts` | batchBeforeUpdate hook | 批量更新前的驗證與跨表同步 |
| `hqWareHouseCheck.ts` | function | 非同步檢查總倉可分配數（todoJob） |
| `hqWareHouseCheckResult.ts` | function | 讀取檢查結果並更新狀態（todoJob） |
| `hqWareHouseReCheck.ts` | function | 手動重新觸發可分配數檢查（Bulk） |
| `hqTransferApprove.ts` | function | 總倉調撥核准 |
| `to2ir.ts` | function | 調轉驗收（Retry: 3） |
| `cancel.ts` | function | 作廢調撥單（Public） |
| `reserveArchive.ts` | function | 預約封存（Bulk, Call） |
| `executeArchive.ts` | function | 執行封存（Retry: 2） |
| `executeArchive.cron.ts` | cron | 每日台灣時間 03:00 執行封存 |
| `unlock.ts` | function | 釋放鎖庫 |
| `unlock.cron.ts` | cron | 每 5 分鐘釋放鎖庫 |

---

## policy.ts 重點邏輯

policy 在每次 `insertV2` / `updateV2` 後觸發（`ignorePolicy:true` 時跳過）。

### 執行順序

1. **讀取 dsvorder**（若有 `dsvOrderName`）
2. **基本驗證**：`from !== to`、明細不可為空、捐贈料件/藥品檢查、skipLogistics 合法性
3. **鎖庫檔驗證**（WH 有 `unlock` 時）：14 天內同鎖庫別數量不得超過保留數
4. **預計出貨日期驗證**：至少 +2 天（含），不可為六日
5. **更新 hqWareHouseStatus**（詳見 hq-warehouse-status.md）
6. **計算並更新 expectedAmount**（應收量 = 所有 items.amount 加總）
7. **計算並更新 totalCuft**（從 hqcuft 表取得每料件材積）
8. **系統 updateV2 回寫**（`ignorePolicy:true`）：寫入 hqWareHouseStatus、expectedAmount、totalCuft、每筆 cuft/minShippingAmountMemo
9. **大智通在途庫存更新**（isWdsHqLocation 時）
10. **upsertDSVOrder**（hqWareHouseStatus=可調撥 + WH/WHAT + isHqWareHouseTransfer + !skipLogistics）

### isFromDSVUpdateStatus 旗標

當 `dsvorder.policy` 執行「更新訂單狀態」時，回寫 transferorder，此時 transferorder.policy 會再次觸發。
`isFromDSVUpdateStatus` 旗標用於識別這個情境，避免觸發不必要的邏輯。

---

## batchBeforeUpdate.ts 重點邏輯

hook 在每次 `batchUpdateV2` **前**觸發（`ignorePolicy:true` **無法跳過**）。

### 早期退出條件

```typescript
// 1. 批量作業超過 20 筆（非 batchmutation 觸發時）
if (isTriggerByHuman && records.length > cMaxBatchUpdate && !isFromBatchMutation)
  throw BatchBlockError

// 2. 總倉自動調撥任務觸發且有 skipBeforeUpdate 旗標
if (isFromHQReorderTask && userContent.skipBeforeUpdate)
  return records  // 直接跳過所有邏輯
```

### 主要功能

**① 驗證類**

- 已轉驗收的調撥單不得修改明細/備註
- 單次 push 超過 `cHQMaxItemsInsertPerTime`（100 筆）時拒絕
- `検査中` 狀態的調撥單拒絕人工更新
- 沒有合法送貨地址時拒絕更新（非明細操作時）

**② 同步 dsvorderdetail 數量（setLineRows）**

當表身列被修改（`setLineRows`）且有對應的 dsvorderdetail 時：
- 比對 `amount` 或 `cuft` 是否有變動
- 若有變動 → 加入 `dsvDetailUpdate`

```typescript
// 執行更新
await ctx.query.batchUpdateV2<DSVOrderDetailBody>({
  table: 'dsvorderdetail',
  updates: Object.values(dsvDetailUpdate).flat(),
  ignorePolicy: true,  // 不觸發 dsvorderdetail.batchPolicy
});

// 若非來自 dsvorderdetail.batchPolicy：更新 dsvorder 觸發重算
if (!userContent.isFromDSVOrderDetailBatchPolicy) {
  await ctx.query.batchUpdateV2<DSVOrderBody>({
    body: { totalQuantity: 0, updatedAtByTransferOrder: new Date() },
    ...
  });
}
```

**③ 同步 fromTransferOrder 數量（WHAT + push/set 明細）**

當 WHAT 調撥單有 `fromTransferOrderName` 且有新增/修改明細時：
- 在來源調撥單（WH）的表身列中找到對應料件
- 更新來源調撥單的數量（加/減差值）
- 記錄目標倉庫到 `systemMemo`

**④ 封存 dsvorderdetail（pullLineRows）**

當表身列被移除（`pullLineRows`）時，自動封存對應的 dsvorderdetail。

### dsvDetailUpdate 與 fromTransferOrderItemsUpdate 的差異

| | dsvDetailUpdate | fromTransferOrderItemsUpdate |
|--|--|--|
| 觸發條件 | `setLineRows`（修改既有表身列） | `pushLineRows` 或 `setLineRows`（WHAT + fromTransferOrderName） |
| 目標表格 | `dsvorderdetail` | 來源 `transferorder`（WH 調撥單） |
| 適用類型 | WH, WHAT | 僅 WHAT |

---

## hqWareHouseCheck.ts 重點

- 非同步執行，在 todoJob 中處理
- 計算各料件在 14 天內的在途數量
- 查詢 dsvinventory/其他調撥單等確認可調撥數
- 結果寫入 todoJob，由 hqWareHouseCheckResult.ts 讀取後更新狀態

---

## 腳本間的依賴關係

```
policy.ts
  ├─ imports: batchBeforeUpdate.ts (TransferorderUserContent 型別, cHQMaxItemsInsertPerTime 常數)
  ├─ imports: executeArchive.ts (reserveArchive 邏輯)
  └─ imports: isHqWareHouseTransfer (自身 export)

hqWareHouseCheckResult.ts
  └─ 讀取 hqWareHouseCheck.ts 的 todoJob 結果

hqWareHouseReCheck.ts
  └─ 呼叫 hqWareHouseCheck + hqWareHouseCheckResult 流程
```
