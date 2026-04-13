# 各類型腳本的測試寫法

本章節提供 NorwegianForest 六種腳本類型的標準測試模板。

---

## 1. Policy 測試

**腳本位置：** `tables/<module>/scripts/<tablename>/policy.ts`
**測試位置：** `tests/<module>/policy.test.ts`

**回傳值：**
- 驗證通過 → `undefined`
- 驗證失敗 → `'Error: ...'` 字串（不 throw）

```typescript
import { expect } from 'chai';
import { cloneDeep } from 'lodash';
import { resolve } from 'path';
import { MySandbox } from '@javaCat/MySandbox';
import { MyStatus } from '@norwegianForestTables/enum';
import { MyBody, MyLines } from '@norwegianForestTables/module/_type';
import { SafeRecord2 } from '@norwegianForestTypes/index';
import { generateExecuteFunc, writeRecord, QueryEventEmitter } from '../utils';
import { mockRecord, mockRelated } from './mocks';

describe('MyTable Policy 測試', () => {
  let testRecord = cloneDeep(mockRecord);
  const originQueryProcessor = MySandbox.queryProcessor;
  const eventEmitter = new QueryEventEmitter();

  const executeFunc = generateExecuteFunc<[SafeRecord2<MyBody, MyLines>]>({
    scriptPath: resolve(__dirname, '../../tables/module/scripts/mytable/policy.ts'),
    libs: [
      { name: 'Utils', path: resolve(__dirname, '../../tables/common/utils.ts') },
    ],
  });

  before(() => {
    MySandbox.queryProcessor = async (query): Promise<unknown> => {
      eventEmitter.emit(query.method, query);
      if (query.method === 'findV2') {
        if (query.table === 'related') return [mockRelated];
      } else if (query.method === 'updateV2') {
        if (query.table === 'mytable') {
          writeRecord(testRecord, query);
          return [1];
        }
      } else if (query.method === 'echo') {
        return;
      }
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
  });

  beforeEach(() => {
    testRecord = cloneDeep(mockRecord);
  });

  after(() => {
    MySandbox.queryProcessor = originQueryProcessor;
  });

  it('必填欄位為空時拒絕', async () => {
    testRecord.body.fieldA = '';
    const result = await executeFunc({ args: [testRecord] });
    expect(result).to.include('Error: 欄位 A 不可為空');
  });

  it('金額不符時拒絕', async () => {
    testRecord.body.total = -1;
    const result = await executeFunc({ args: [testRecord] });
    expect(typeof result === 'string' && result.startsWith('Error:')).to.be.true;
  });

  it('驗證通過', async () => {
    const result = await executeFunc({ args: [testRecord] });
    expect(result).to.be.undefined;
  });

  it('通過後有更新欄位 X', async () => {
    let hasUpdate = false;
    eventEmitter.addListener('updateV2', (query) => {
      hasUpdate ||= query.table === 'mytable' && query.body?.fieldX != null;
    });
    await executeFunc({ args: [testRecord] });
    eventEmitter.removeAllListeners('updateV2');
    expect(hasUpdate).to.be.true;
    expect(testRecord.body.fieldX).to.equal('expectedValue');
  });
});
```

---

## 2. BatchPolicy 測試

**腳本位置：** `tables/<module>/scripts/<tablename>/batchPolicy.ts`
**測試位置：** `tests/<module>/batchPolicy.test.ts`

**特點：** 接受 `Record[]` 陣列作為輸入，通常用於批次驗證或批次更新。

```typescript
import { expect } from 'chai';
import { cloneDeep } from 'lodash';
import { resolve } from 'path';
import { MySandbox } from '@javaCat/MySandbox';
import { SafeRecord2 } from '@norwegianForestTypes/index';
import { generateExecuteFunc } from '../utils';
import { mockRecord } from './mocks';

describe('MyTable BatchPolicy 測試', () => {
  let testRecords = [cloneDeep(mockRecord)];
  const originQueryProcessor = MySandbox.queryProcessor;

  const executeFunc = generateExecuteFunc<[SafeRecord2[]]>({
    scriptPath: resolve(__dirname, '../../tables/module/scripts/mytable/batchPolicy.ts'),
    libs: [
      { name: 'Utils', path: resolve(__dirname, '../../tables/common/utils.ts') },
    ],
  });

  before(() => {
    MySandbox.queryProcessor = async (query): Promise<unknown> => {
      if (query.method === 'batchUpdateV2') {
        return testRecords.map(r => r._id);
      } else if (query.method === 'findV2') {
        return [];
      }
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
  });

  beforeEach(() => {
    testRecords = [cloneDeep(mockRecord)];
  });

  after(() => {
    MySandbox.queryProcessor = originQueryProcessor;
  });

  it('INSERT 情境（oldRecords 為空）：執行批次更新', async () => {
    const result = await executeFunc({ args: [testRecords] });
    // batchPolicy 通常沒有回傳值
    expect(result).to.be.undefined;
  });
});
```

---

## 3. Approval 測試

**腳本位置：** `tables/<module>/scripts/<tablename>/approval.ts`
**測試位置：** `tests/<module>/approval.test.ts`

**回傳值：** 符合條件的簽核規則 `ruleName` 字串（`string`）。

```typescript
import { expect } from 'chai';
import { cloneDeep } from 'lodash';
import { resolve } from 'path';
import { SafeRecord2 } from '@norwegianForestTypes/index';
import { MyBody, MyLines } from '@norwegianForestTables/module/_type';
import { generateExecuteFunc } from '../utils';
import { mockRecord } from './mocks';

describe('MyTable Approval 測試', () => {
  let testRecord = cloneDeep(mockRecord);

  // Approval 腳本通常不需要 mock queryProcessor（純邏輯判斷）
  const executeFunc = generateExecuteFunc<[SafeRecord2<MyBody, MyLines>]>({
    scriptPath: resolve(__dirname, '../../tables/module/scripts/mytable/approval.ts'),
  });

  beforeEach(() => {
    testRecord = cloneDeep(mockRecord);
  });

  it('子公司 WP + 金額 > 100000 → 主管簽核', async () => {
    testRecord.body.subsidiary = 'WP';
    testRecord.body.total = 150000;
    const result = await executeFunc({ args: [testRecord] });
    expect(result).to.equal('主管簽核');
  });

  it('子公司 SG → SG 主管簽核', async () => {
    testRecord.body.subsidiary = 'SG';
    const result = await executeFunc({ args: [testRecord] });
    expect(result).to.equal('SG 主管簽核');
  });

  it('無對應規則 → 預設簽核鏈', async () => {
    testRecord.body.subsidiary = 'UNKNOWN';
    const result = await executeFunc({ args: [testRecord] });
    expect(result).to.equal('default');
  });
});
```

**注意：** 若 Approval 腳本需要查詢，再依 Mock 策略章節加入 queryProcessor。

---

## 4. BeforeInsert Hook 測試

**腳本位置：** `tables/<module>/scripts/<tablename>/beforeInsert.ts`
**測試位置：** `tests/<module>/beforeInsert.test.ts`

**回傳值：**
- 成功 → 修改後的 `record` 物件（**不是 undefined**）
- 失敗 → `'Error: ...'` 字串

```typescript
import { expect } from 'chai';
import { cloneDeep } from 'lodash';
import { resolve } from 'path';
import { MySandbox } from '@javaCat/MySandbox';
import { SafeRecord2 } from '@norwegianForestTypes/index';
import { MyBody, MyLines } from '@norwegianForestTables/module/_type';
import { generateExecuteFunc } from '../utils';
import { mockRecord, mockRelated } from './mocks';

describe('MyTable BeforeInsert 測試', () => {
  let testRecord = cloneDeep(mockRecord);
  const originQueryProcessor = MySandbox.queryProcessor;

  const executeFunc = generateExecuteFunc<[SafeRecord2<MyBody, MyLines>]>({
    scriptPath: resolve(__dirname, '../../tables/module/scripts/mytable/beforeInsert.ts'),
    libs: [
      { name: 'Utils', path: resolve(__dirname, '../../tables/common/utils.ts') },
    ],
  });

  before(() => {
    MySandbox.queryProcessor = async (query): Promise<unknown> => {
      if (query.method === 'findV2') {
        if (query.table === 'related') return [mockRelated];
      } else if (query.method === 'echo') {
        return;
      }
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
  });

  beforeEach(() => {
    testRecord = cloneDeep(mockRecord);
  });

  after(() => {
    MySandbox.queryProcessor = originQueryProcessor;
  });

  it('插入前自動計算總計', async () => {
    testRecord.body.quantity = 5;
    testRecord.body.unitPrice = 200;
    const result = await executeFunc({ args: [testRecord] }) as SafeRecord2<MyBody, MyLines>;
    // BeforeInsert 成功時回傳修改後的 record
    expect(result.body.total).to.equal(1000);
  });

  it('找不到關聯資料時拒絕', async () => {
    MySandbox.queryProcessor = async (query) => {
      if (query.method === 'findV2' && query.table === 'related') return [];
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
    const result = await executeFunc({ args: [testRecord] });
    expect(typeof result === 'string' && result.startsWith('Error:')).to.be.true;
  });
});
```

---

## 5. BeforeUpdate Hook 測試

**腳本位置：** `tables/<module>/scripts/<tablename>/beforeUpdate.ts`
**測試位置：** `tests/<module>/beforeUpdate.test.ts`

結構與 BeforeInsert 相同。若 BeforeUpdate 接收新舊兩個 record：

```typescript
// 若 beforeUpdate 腳本有兩個 record 參數（新舊各一）
const executeFunc = generateExecuteFunc<[SafeRecord2<MyBody, MyLines>, SafeRecord2<MyBody, MyLines>]>({
  scriptPath: resolve(__dirname, '../../tables/module/scripts/mytable/beforeUpdate.ts'),
  libs: [...],
});

it('狀態不可倒退', async () => {
  const oldRecord = cloneDeep(mockRecord);
  oldRecord.body.status = MyStatus.DONE;
  testRecord.body.status = MyStatus.PENDING; // 嘗試從 DONE 倒退到 PENDING
  const result = await executeFunc({ args: [testRecord, oldRecord] });
  expect(result).to.include('Error: 狀態不可倒退');
});

it('正常更新', async () => {
  testRecord.body.memo = '更新備註';
  const result = await executeFunc({ args: [testRecord, cloneDeep(mockRecord)] });
  expect(result).to.not.include('Error:');
});
```

---

## 6. Function 測試（普通函式）

**腳本位置：** `tables/<module>/scripts/<tablename>/<funcName>.ts`
**測試位置：** `tests/<module>/functions/<funcName>.test.ts`

**重要：** Function 腳本簽章為 `async (record, param, ctx)`。`ctx` 由 Sandbox 在 arguments 之後注入，因此 `Args` 必須包含 `null` 佔位。

```typescript
import { expect } from 'chai';
import { cloneDeep } from 'lodash';
import { resolve } from 'path';
import { MySandbox } from '@javaCat/MySandbox';
import { MyStatus } from '@norwegianForestTables/enum';
import { MyBody, MyLines } from '@norwegianForestTables/module/_type';
import { SafeRecord2 } from '@norwegianForestTypes/index';
import { generateExecuteFunc, writeRecord } from '../../utils';
import { mockRecord, mockRelated } from '../mocks';

describe('MyTable funcName 函式測試', () => {
  let testRecord = cloneDeep(mockRecord);
  const originQueryProcessor = MySandbox.queryProcessor;

  // Args 第二個型別必須是 null
  const executeFunc = generateExecuteFunc<[SafeRecord2<MyBody, MyLines>, null]>({
    scriptPath: resolve(__dirname, '../../../tables/module/scripts/mytable/funcName.ts'),
    libs: [
      { name: 'dayjs', path: resolve(__dirname, '../../../tables/common/dayjs.ts') },
      { name: 'Utils', path: resolve(__dirname, '../../../tables/common/utils.ts') },
    ],
  });

  before(() => {
    MySandbox.queryProcessor = async (query): Promise<unknown> => {
      if (query.method === 'findV2') {
        if (query.table === 'related') return [mockRelated];
      } else if (query.method === 'updateV2') {
        if (query.table === 'mytable') {
          writeRecord(testRecord, query);
          return [1];
        }
      } else if (query.method === 'echo') {
        return;
      }
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
  });

  beforeEach(() => {
    testRecord = cloneDeep(mockRecord);
  });

  after(() => {
    MySandbox.queryProcessor = originQueryProcessor;
  });

  it('成功執行並更新狀態', async () => {
    const result = await executeFunc({
      args: [testRecord, null],   // 必須傳 null 作為 param 佔位
      user: { name: 'testUser' },
    });
    expect(result).to.include('成功');
    expect(testRecord.body.status).to.equal(MyStatus.DONE);
  });

  it('找不到關聯資料時回傳錯誤', async () => {
    MySandbox.queryProcessor = async (query) => {
      if (query.method === 'findV2' && query.table === 'related') return [];
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
    const result = await executeFunc({ args: [testRecord, null] });
    expect(typeof result === 'string' && result.startsWith('Error:')).to.be.true;
  });
});
```

---

## 7. Function 測試（TodoJob 多階段）

**特點：** 腳本使用 `ctx.todoJob` 管理階段，每次執行回傳 `{ status: 'WORKING' | 'DONE' | 'ERROR', buffer? }` 物件。使用 `executeFuncUntilDoneOrError` 驅動。

```typescript
import { expect } from 'chai';
import { cloneDeep } from 'lodash';
import { resolve } from 'path';
import { MySandbox } from '@javaCat/MySandbox';
import { TodoJobRecord } from '@javaCat/@type/tables/todoJob';
import { MyStatus } from '@norwegianForestTables/enum';
import { MyBody, MyLines } from '@norwegianForestTables/module/_type';
import { SafeRecord2 } from '@norwegianForestTypes/index';
import { generateExecuteFunc, executeFuncUntilDoneOrError, writeRecord } from '../../utils';
import { mockRecord, mockRelated } from '../mocks';

describe('MyTable todoFuncName 函式測試', () => {
  let testRecord = cloneDeep(mockRecord);
  const originQueryProcessor = MySandbox.queryProcessor;

  const executeFunc = generateExecuteFunc<[SafeRecord2<MyBody, MyLines>, null]>({
    scriptPath: resolve(__dirname, '../../../tables/module/scripts/mytable/todoFuncName.ts'),
    libs: [
      { name: 'dayjs', path: resolve(__dirname, '../../../tables/common/dayjs.ts') },
      { name: 'Utils', path: resolve(__dirname, '../../../tables/common/utils.ts') },
    ],
  });

  // 模擬 TodoJob 記錄（status 必須是 WORKING）
  const mockTodoJob: TodoJobRecord = {
    body: {
      name: 'JOB001',
      tableName: 'mytable',
      functionName: 'todoFuncName',
      status: 'WORKING',
      buffer: undefined,
      queueNo: 1,
      source: '測試',
      execCount: 0,
      errorCount: 0,
    },
    lines: { items: [] },
  };

  before(() => {
    MySandbox.queryProcessor = async (query): Promise<unknown> => {
      if (query.method === 'findV2') {
        if (query.table === 'related') return [mockRelated];
      } else if (query.method === 'updateV2') {
        if (query.table === 'mytable') {
          writeRecord(testRecord, query);
          return [1];
        }
      } else if (query.method === 'batchInsertV2') {
        return ['ID001', 'ID002'];
      } else if (query.method === 'echo') {
        return;
      }
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
  });

  beforeEach(() => {
    testRecord = cloneDeep(mockRecord);
  });

  after(() => {
    MySandbox.queryProcessor = originQueryProcessor;
  });

  it('正常完成（status = DONE）', async () => {
    const result = await executeFuncUntilDoneOrError({
      executeFunc,
      args: [testRecord, null],
      todoJob: cloneDeep(mockTodoJob), // cloneDeep：函式內部會修改 todoJob
    });
    expect(result.status).to.equal('DONE');
    expect(testRecord.body.status).to.equal(MyStatus.DONE);
  });

  it('關聯資料不存在時停在 ERROR', async () => {
    MySandbox.queryProcessor = async (query) => {
      if (query.method === 'findV2' && query.table === 'related') return [];
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
    const result = await executeFuncUntilDoneOrError({
      executeFunc,
      args: [testRecord, null],
      todoJob: cloneDeep(mockTodoJob),
    });
    expect(result.status).to.equal('ERROR');
  });
});
```

---

## 8. 純單元測試

**測試對象：** 腳本中匯出的純函式（無 DB 操作、無 Sandbox 依賴）。
**特點：** 直接 import 函式，不需要 `generateExecuteFunc`，速度最快。

```typescript
import { expect } from 'chai';
// 直接 import 被測函式（注意：不透過 generateExecuteFunc）
import { calcAmount, findMinDate } from '../../../tables/module/scripts/mytable/utils';

describe('calcAmount 單元測試', () => {
  it('undefined 輸入回傳 0', () => {
    expect(calcAmount(undefined)).to.equal(0);
  });

  it('負數輸入回傳 0', () => {
    expect(calcAmount(-5)).to.equal(0);
  });

  it('百分比計算', () => {
    expect(calcAmount({ type: 'PERCENT', value: 10 }, 1000)).to.equal(100);
  });
});

describe('findMinDate 單元測試', () => {
  it('空陣列回傳 null', () => {
    expect(findMinDate([])).to.be.null;
  });

  it('單一日期', () => {
    const date = new Date('2024-01-15');
    expect(findMinDate([date])).to.deep.equal(date);
  });

  it('多個日期取最小', () => {
    const dates = [new Date('2024-03-01'), new Date('2024-01-01'), new Date('2024-02-01')];
    expect(findMinDate(dates)).to.deep.equal(new Date('2024-01-01'));
  });
});
```

---

## 通用斷言模式

```typescript
// 基本型別
expect(result).to.equal('expected string');
expect(result).to.equal(42);
expect(result).to.be.true;
expect(result).to.be.false;
expect(result).to.be.undefined;
expect(result).to.be.null;

// 字串包含
expect(result).to.include('Error: 訊息');

// 錯誤字串（Policy / Hook 失敗時）
expect(typeof result === 'string' && result.startsWith('Error:')).to.be.true;

// 陣列
expect(result).to.have.length(3);
expect(result).to.deep.include({ name: 'NAME001' });

// 物件屬性
expect(testRecord.body.status).to.equal(MyStatus.DONE);
expect(testRecord.body.total).to.equal(1500);

// 日期
import { isDate } from 'lodash';
expect(isDate(result)).to.be.true;

// TodoJob 結果
expect(result.status).to.equal('DONE');
expect(result.status).to.be.oneOf(['DONE', 'CANCELLED']);
```

## 腳本執行路徑規則

| 測試檔位置 | scriptPath resolve 前綴 |
|-----------|------------------------|
| `tests/<module>/policy.test.ts` | `../../tables/...` |
| `tests/<module>/approval.test.ts` | `../../tables/...` |
| `tests/<module>/beforeInsert.test.ts` | `../../tables/...` |
| `tests/<module>/functions/<func>.test.ts` | `../../../tables/...` |
