# Table Lifecycle Hooks 種類與觸發時機

## 六種 Hook 對照表

| Hook | 觸發時機 | 對應 DB 操作 | ignorePolicy 效果 |
|------|---------|------------|-----------------|
| `policy` | DB 寫入之**後** | `updateV2` / `insertV2` | `ignorePolicy: true` → **跳過** |
| `batchPolicy` | DB 寫入之**後** | `batchUpdateV2` / `batchInsertV2` | `ignorePolicy: true` → **跳過** |
| `beforeInsert` | DB 寫入之**前** | `insertV2` | `ignorePolicy: true` → **⚠️ 無法跳過！** |
| `beforeUpdate` | DB 寫入之**前** | `updateV2` | `ignorePolicy: true` → **⚠️ 無法跳過！** |
| `batchBeforeInsert` | DB 寫入之**前** | `batchInsertV2` | `ignorePolicy: true` → **⚠️ 無法跳過！** |
| `batchBeforeUpdate` | DB 寫入之**前** | `batchUpdateV2` | `ignorePolicy: true` → **⚠️ 無法跳過！** |

## 關鍵差異：before hook 無法被 ignorePolicy 跳過

這是最常被忽略的陷阱。`ignorePolicy: true` 只跳過 policy/batchPolicy，`beforeInsert`、`beforeUpdate`、`batchBeforeInsert`、`batchBeforeUpdate` 這四個 before hook 一律執行。以 `MyModel.batchUpdateV2` 為例：

```typescript
// JavaCat/src/lib2/MyModel/MyModel.ts（簡化）
async batchUpdateV2(input) {
  // ① BATCH_BEFORE_UPDATE：不管 ignorePolicy，一定執行
  const processedData = await this.triggerBatchBeforeUpdateHooks(...); // line ~3100

  // ② 實際寫入 DB
  await db.batchUpdate(processedData);

  // ③ batchPolicy：ignorePolicy 時跳過
  if (!input.ignorePolicy) await this.triggerBatchPolicy(...); // line ~3319

  // ④ policy（每筆）：ignorePolicy 時跳過
  if (!input.ignorePolicy) await this.triggerPolicies(...); // line ~3331
}
```

**實際案例**：

```typescript
// 對 transferorder 執行 batchUpdateV2，即使 ignorePolicy: true
await ctx.query.batchUpdateV2({
  table: 'transferorder',
  updates: [...],
  ignorePolicy: true,  // ← 只跳過 batchPolicy 和 policy
  // transferorder 的 batchBeforeUpdate 仍然執行！（所有 before hook 皆無法跳過）
});
```

## 各 Hook 的腳本 context 參數

### policy / beforeUpdate
```typescript
const main: PolicyScript<SafeRecord> = async (record, ctx, oldRecord) => {
  // record: 當前（新）紀錄
  // ctx: 執行上下文
  // oldRecord: 舊紀錄（INSERT 時為 undefined）
};
```

### batchPolicy
```typescript
const main: BatchPolicyScript<SafeRecord> = async ({ ctx, records, oldRecords }) => {
  // records: 當前（新）紀錄陣列
  // oldRecords: 舊紀錄陣列（INSERT 時為 undefined）
};
```

### batchBeforeUpdate
```typescript
const main: BatchBeforeUpdateScript<SafeRecord> = async ({ ctx, records, oldRecords }) => {
  // records: 待更新的 NormUpdateRecord 陣列（包含 keyName/keyValue/bodyFields/pushLineRows/setLineRows/pullLineRows）
  // oldRecords: 更新前的原始紀錄陣列
  // 回傳 records（可修改）或拋出錯誤阻止更新
};
```

## 腳本在 table 定義中的註冊方式

```typescript
// NorwegianForest/tables/someTable/index.ts
export default createTable({
  hooks: [
    {
      hookType: HookType.BATCH_BEFORE_UPDATE,
      name: '批次更新前掛勾',
      scriptPath: './scripts/someTable/batchBeforeUpdate',
    },
    {
      hookType: HookType.BATCH_POLICY,
      name: '批次政策',
      scriptPath: './scripts/someTable/batchPolicy',
    },
  ],
  policies: [
    {
      name: '政策',
      scriptPath: './scripts/someTable/policy',
    },
  ],
});
```
