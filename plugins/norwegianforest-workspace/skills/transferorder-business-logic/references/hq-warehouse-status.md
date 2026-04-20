# hqWareHouseStatus 狀態機

## 狀態值

| 狀態 | 意義 | 誰設定 |
|-----|-----|-------|
| `可調撥` | 已確認可以調撥，可進行 DSV 出貨 | policy（各種情境） |
| `検査中` | 等待非同步可分配數檢查完成 | policy（人工更新 WH 調撥單時） |
| `不可調撥` | 檢查完成，庫存不足或有其他問題 | hqWareHouseCheck.ts |
| `錯誤` | 檢查任務執行失敗 | hqWareHouseCheckResult.ts |

> 注意：狀態字串是中文，直接比對字串值，沒有 Enum 封裝。

## 狀態轉換邏輯

### 建立時（INSERT，`!oldTo`）

```
WH + DSV上線後 + isHqWareHouseTransfer(from)
  → 沒有 hqWareHouseStatus 時
  → policy 建立 todoJob（「檢查總倉調撥可分配數」）
  → 設 hqWareHouseStatus = '検査中'

WH + DSV上線後 + 已有 hqWareHouseStatus = '検査中'
  → 不重複建立 todoJob

WH + DSV上線前 OR 非 isHqWareHouseTransfer
  → 直接設 hqWareHouseStatus = '可調撥'

WHAT（系統建立）
  → 直接設 hqWareHouseStatus = '可調撥'

WHAT（明細為空）
  → 設 hqWareHouseStatus = '不可調撥' + reserveArchive = true

ST / DN
  → 設 hqWareHouseStatus = '可調撥'
```

### 更新時（UPDATE，`oldTo` 存在）

```
WH（或 WHAT 被人工更新）+ DSV上線後 + isHqWareHouseTransfer(from)
  ├─ DSV 已拋單且已出貨：
  │   人工修改明細 → return 錯誤（不可更新）
  ├─ DSV 未拋單 + 以下任一條件：
  │   - 沒有 hqWareHouseStatus
  │   - skipLogistics 改變
  │   - 明細（items）有變動
  │   - shippingAddress 改變
  │   → 建立 todoJob，設 hqWareHouseStatus = '検査中'
  └─ 其他情況：不改變狀態

WH + DSV上線前 OR 非 isHqWareHouseTransfer
  → 若狀態不是 '可調撥' 則設為 '可調撥'
```

## 非同步檢查流程

```
policy 建立 todoJob：
  ① 「檢查總倉調撥可分配數」（hqWareHouseCheck.ts）
      → 執行庫存計算，寫入結果
  ② 「檢查總倉調撥可分配數結果」（hqWareHouseCheckResult.ts）
      → 讀取結果，更新 hqWareHouseStatus
      → 可調撥 → '可調撥'
      → 不可調撥 → '不可調撥' + hqWareHouseBlockReason
      → 執行失敗 → '錯誤'

兩個 todoJob 使用 queueNo=9（高優先佇列），
且第二個 todoJob 的 param 填第一個的 job.name，確保順序執行。
```

## 與 DSV 出貨的關係

```typescript
// policy.ts 第 546-554 行
const hqWareHouseStatus = systemUpdateBody.hqWareHouseStatus || to.body.hqWareHouseStatus || '可調撥';
if (
  to._id &&
  (to.body.type === 'WH' || to.body.type === 'WHAT') &&
  hqWareHouseStatus === '可調撥' &&                 // ← 只有可調撥才建立 DSV 出貨單
  isHqWareHouseTransfer(fromLocation) &&
  !to.body.skipLogistics
) {
  await upsertDSVOrder(ctx, { to, user });
}
```

**重點**：`upsertDSVOrder` 只在 `hqWareHouseStatus === '可調撥'` 時執行。
- `検査中` 狀態不會建立 DSV 出貨單
- 狀態變為 `可調撥` 後的下一次 policy 觸發才會建立

## batchBeforeUpdate 的狀態防護

```typescript
// batchBeforeUpdate.ts：人工操作時若狀態仍為 '検査中' 則拒絕更新
if (
  cConditionMap['需要檢查的總倉自動調撥條件'](ctx, item) &&
  preview.body.hqWareHouseStatus === '検查中' &&
  original.body.hqWareHouseStatus === '検查中'
) {
  throw new Error('總倉調撥單請等待檢查完畢後再進行更新操作');
}
```

## 重新檢查

有一個「重新檢查總倉調撥可分配數」（hqWareHouseReCheck.ts）的 Bulk 函式，
可由使用者手動觸發對已建立的調撥單重新執行可分配數檢查。
