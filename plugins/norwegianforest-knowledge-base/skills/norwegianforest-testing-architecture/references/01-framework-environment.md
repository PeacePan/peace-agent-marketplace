# 測試框架與環境

NorwegianForest 使用 **Mocha + Chai + NYC** 框架，以 TypeScript 撰寫測試，透過自定義的 Sandbox 工具執行腳本。

## 測試框架清單

| 工具 | 用途 |
|------|------|
| Mocha 9.1.1 | 測試框架（describe / it 結構） |
| Chai 4.3.4 | 斷言庫（expect 風格） |
| ts-node | TypeScript 即時編譯（transpile-only，不做型別檢查） |
| NYC (Istanbul) | 程式碼覆蓋率儀表化 |
| lodash cloneDeep | Mock 數據防污染 |

## 測試執行指令

```bash
# 執行所有測試
npm test

# 執行單一模組目錄
npm test -- tests/<module>/

# 執行單一測試檔
npm test -- tests/<module>/policy.test.ts
```

**注意：** `npm test` 會先建置 JavaCat 和 NorwegianForest，再執行 mocha。實際執行的是 `bin/test.sh`。

## 重要環境設定（bin/test.sh）

- `TZ=Greenwich` — 統一所有測試的時區，避免日期計算因時區差異失敗
- `SANDBOX_QUIET=1` — 關閉 Sandbox VM 的詳細日誌
- `--parallel --jobs 2` — 2 個 worker 並行執行測試
- `-s 5000 -t 30000` — 慢速門檻 5s、逾時 30s
- 先執行 `npm run build` — 部分測試需要預編譯的表格定義

## global-setup.ts 說明

```typescript
// tests/global-setup.ts
import dayjs from '@norwegianForestTables/common/dayjs';
import * as Procurement from '@norwegianForestTables/common/procurement';
import * as Utils from '@norwegianForestTables/common/utils';

global.dayjs = dayjs;
global.Procurement = Procurement;
global.Utils = Utils;
```

**原因：** JavaCat Sandbox VM 在執行腳本時，會將表格 `libs` 中的模組注入為全域變數（如 `dayjs`、`Utils`）。測試環境必須手動宣告這些全域變數，否則腳本在 VM 內執行時會找不到這些名稱。

## 工具函式 API（從 tests/utils.ts 匯入）

### 匯入路徑

```typescript
// 從 tests/<module>/ 層級
import { generateExecuteFunc, executeFuncUntilDoneOrError, writeRecord, sortRecords, QueryEventEmitter } from '../utils';

// 從 tests/<module>/functions/ 層級
import { generateExecuteFunc, executeFuncUntilDoneOrError, writeRecord, sortRecords, QueryEventEmitter } from '../../utils';
```

---

### generateExecuteFunc

讀取腳本並回傳可反覆呼叫的測試執行函式。會對腳本進行 NYC 儀表化以收集覆蓋率。

```typescript
function generateExecuteFunc<Args extends unknown[]>(configs: {
  /** 腳本的絕對路徑（指向 .ts 原始檔，編譯由工具自動處理） */
  scriptPath: string;
  /** 額外注入的 lib（對應表格定義中的 libs） */
  libs?: { name: string; path: string }[];
  /** 是否跳過 NYC 儀表化（預設 false） */
  skipCoverage?: boolean;
  /** 注入在腳本前面的程式碼（用於注入 process.env 環境變數） */
  scriptPrefix?: string;
}): (options: {
  args: Args;
  user?: { name: string };
  todoJob?: TodoJobRecord;
  env?: Record<string, string>;
}) => Promise<unknown>
```

**使用範例（Policy / Approval / Hook）：**

```typescript
const executeFunc = generateExecuteFunc<[SafeRecord2<MyBody, MyLines>]>({
  scriptPath: resolve(__dirname, '../../tables/module/scripts/tablename/policy.ts'),
  libs: [
    { name: 'Utils', path: resolve(__dirname, '../../tables/common/utils.ts') },
  ],
});
const result = await executeFunc({ args: [testRecord] });
```

**使用範例（Function 腳本）：**

```typescript
// 第二個 Args 型別必須是 null，對應 FunctionScript 的 param 參數
const executeFunc = generateExecuteFunc<[SafeRecord2<MyBody, MyLines>, null]>({
  scriptPath: resolve(__dirname, '../../../tables/module/scripts/tablename/funcName.ts'),
  libs: [
    { name: 'dayjs', path: resolve(__dirname, '../../../tables/common/dayjs.ts') },
    { name: 'Utils', path: resolve(__dirname, '../../../tables/common/utils.ts') },
  ],
});
// 呼叫時也要傳 null
const result = await executeFunc({ args: [testRecord, null] });
```

> ⚠️ **常見錯誤：** Function 腳本的簽章為 `async (record, param, ctx)`，其中 `ctx` 由 Sandbox 在 `param` 之後注入。若 `args` 少傳一個位置（只傳 `[record]` 而非 `[record, null]`），`ctx` 會是 `undefined`，導致 `ctx.todoJob` 出現 `TypeError: Cannot read properties of undefined (reading 'todoJob')`。

**使用範例（注入環境變數）：**

```typescript
const executeFunc = generateExecuteFunc({
  scriptPath: resolve(__dirname, '../../../tables/meta/scripts/metasaletask/upload.ts'),
  scriptPrefix: "process.env.META_DATASET_ID = 'test_id'; process.env.META_ACCESS_TOKEN = 'test_token';",
  libs: [...],
});
```

---

### executeFuncUntilDoneOrError

反覆執行 TodoJob 腳本，直到 `status` 變為 `DONE`、`CANCELLED` 或 `ERROR`。

```typescript
async function executeFuncUntilDoneOrError<Args extends unknown[]>(params: {
  executeFunc: ReturnType<typeof generateExecuteFunc>;
  args: Args;
  todoJob: TodoJobRecord;
}): Promise<{ status: 'DONE' | 'CANCELLED' | 'ERROR'; buffer?: unknown }>
```

**使用範例：**

```typescript
const result = await executeFuncUntilDoneOrError({
  executeFunc,
  args: [testRecord, null],
  todoJob: cloneDeep(mockTodoJob), // 必須 cloneDeep，因為函式會修改 todoJob.body
});
expect(result.status).to.equal('DONE');
```

---

### writeRecord

模擬 `updateV2` 查詢對 record 的修改效果（直接修改傳入的 source）。

```typescript
function writeRecord<R extends SafeRecord | SafeRecord2>(
  source: R,
  query: Omit<UpdateQuery, 'table' | 'method'> | Omit<UpdateV2Query, 'table' | 'method'>
): R
```

**使用範例：**

```typescript
MySandbox.queryProcessor = async (query) => {
  if (query.method === 'updateV2' && query.table === 'mytable') {
    writeRecord(testRecord, query); // 將 query.body 合併進 testRecord.body
    return [1];
  }
};
```

---

### sortRecords

依 `FindV2Query.multiSort` 格式排序 records 陣列，用於 mock 返回排序後的結果。

```typescript
function sortRecords<R extends SafeRecord2>(
  records: R[],
  sortings: FindV2Query['multiSort']
): R[]
```

---

## 目錄結構慣例

```
tests/
└── <module>/
    ├── mocks.ts               # 所有 Mock 數據定義
    ├── policy.test.ts         # Policy 腳本測試
    ├── batchPolicy.test.ts    # BatchPolicy 腳本測試
    ├── beforeInsert.test.ts   # BeforeInsert Hook 測試
    ├── beforeUpdate.test.ts   # BeforeUpdate Hook 測試
    ├── approval.test.ts       # Approval 簽核鏈測試
    └── functions/
        ├── mocks.ts           # Function 專用 Mock（選用）
        ├── <funcName>.test.ts
        └── ...
```

**命名規則：**
- 測試檔名稱與腳本檔名稱一致，加上 `.test.ts` 後綴
- `mocks.ts` 與使用它的測試檔放同一層
- 若 `functions/` 目錄需要頂層 mock，直接 import `../mocks`

## 覆蓋率（NYC）

- `generateExecuteFunc` 預設對腳本進行 NYC 儀表化（`nyc instrument`）
- 測試結束後，覆蓋率資料存入全域 `__coverage__` 物件
- 設定 `skipCoverage: true` 可跳過儀表化（用於已知無法儀表化的腳本）
- 執行 `npm run test:coverage` 可產生覆蓋率報告（若有設定此指令）
