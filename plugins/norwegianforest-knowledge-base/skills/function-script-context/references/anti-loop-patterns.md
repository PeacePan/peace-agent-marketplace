# 防無限迴圈：userContent 旗標機制

## 問題背景

跨表更新時，A 表 hook → 更新 B 表 → B 表 hook → 更新 A 表 → A 表 hook → ... 造成無限循環。

NorwegianForest 的解決方案：在 `user` 欄位（JSON 字串）中傳遞旗標，讓下游 hook 識別來源並決定跳過特定邏輯。

## userContent 的結構

```typescript
// FunctionScriptUserContent（基礎型別）
type FunctionScriptUserContent = {
  user?: string;           // 實際執行操作的使用者 ID
  functions?: string[];    // 觸發此操作的功能名稱堆疊
  tables?: string[];       // 觸發此操作的來源表格堆疊
};
```

## 讀取 userContent

```typescript
// Utils.prepareContextUser 會：
// 1. 解析 ctx.user（JSON 字串）
// 2. 附加 functionName 到 functions 陣列
// 3. 重新序列化為新的 user 字串
const { userContent, user } = Utils.prepareContextUser<MyUserContent>(ctx, {
  functionName: '我的功能名稱',
});

// userContent: 解析後的物件（包含自訂旗標）
// user: 重新序列化的字串（用來傳給下一層的 DB 操作）
```

## 傳遞旗標到下游

```typescript
await ctx.query.batchUpdateV2({
  table: 'someTable',
  updates: [...],
  ignorePolicy: true,
  user: JSON.stringify({
    ...userContent,           // 保留上游的旗標和 functions 堆疊
    functions: userContent.functions?.filter(fn => fn !== '某功能'),  // 移除不需要的功能標記
    isFromMyHook: true,       // 加入自訂旗標
  }),
});
```

## 在 batchBeforeUpdate 中偵測旗標

```typescript
const main: BatchBeforeUpdateScript<...> = async ({ ctx, records, oldRecords }) => {
  const { userContent, user } = Utils.prepareContextUser<MyUserContent>(ctx, {
    functionName: '批次更新前掛勾',
  });

  // 偵測旗標，跳過會造成循環的邏輯
  if (userContent.isFromMyHook) {
    // 不執行跨表更新
    return records;
  }

  // 一般邏輯...
};
```

## 已知旗標清單

### transferorder 相關

| 旗標 | 型別 | 設定位置 | 偵測位置 | 效果 |
|-----|-----|---------|---------|-----|
| `skipBeforeUpdate` | `boolean` | `hqreorder.ts`（WHAT 自動調撥任務） | `transferorder/batchBeforeUpdate.ts` | `true` 時整個 batchBeforeUpdate 直接 return，跳過所有前檢查 |
| `ignoreDSVOrderDetailPolicy` | `boolean` | `hqreorder.ts` | `transferorder/batchBeforeUpdate.ts` | 控制更新 dsvorderdetail 時的 `ignorePolicy` 值 |
| `isFromDSVOrderDetailBatchPolicy` | `boolean` | `dsvorderdetail/batchPolicy.ts` rowSetUpdates | `transferorder/batchBeforeUpdate.ts` | `true` 時 batchBeforeUpdate 跳過 dsvorder 的 `updatedAtByTransferOrder` 更新，避免觸發冗餘的 dsvorder.policy |

### 識別來源的 functions 堆疊用法

```typescript
// 判斷是否由總倉自動調撥任務觸發
const isFromHQReorderTask = !!(
  userContent.functions?.length &&
  /總倉自動調撥任務/.test(userContent.functions.join(','))
);

// 判斷是否由 batchmutation 觸發
const isFromBatchMutation = !!(
  userContent.tables?.includes('batchmutation') &&
  userContent.functions?.includes('處理批次作業')
);
```

## 型別定義範例

```typescript
// NorwegianForest/tables/inventory/scripts/transferorder/batchBeforeUpdate.ts
export type TransferorderUserContent = FunctionScriptUserContent &
  Partial<{
    skipBeforeUpdate: boolean;
    ignoreDSVOrderDetailPolicy: boolean;
    isFromDSVOrderDetailBatchPolicy: boolean;
  }>;
```

## 設計原則

1. **旗標命名應反映來源**：如 `isFromDSVOrderDetailBatchPolicy` 而非 `skipDsvorderUpdate`，方便 debug 時追蹤觸發路徑
2. **只跳過必要的邏輯**：旗標偵測後應只跳過會造成循環的特定更新，不要 return 掉整個 hook 的所有邏輯
3. **保留上游旗標**：傳遞時 `...userContent` 確保上游的旗標不被清除
4. **Sentinel 欄位優於旗標**：若能透過 sentinel 欄位（如 `updatedAtByTransferOrder`）讓目標 policy 自行判斷是否執行，優先用這種方式，更清晰且不依賴旗標傳遞順序
