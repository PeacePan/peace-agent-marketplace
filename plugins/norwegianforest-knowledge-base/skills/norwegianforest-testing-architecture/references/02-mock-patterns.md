# Mock 策略

NorwegianForest 的測試透過攔截 `MySandbox.queryProcessor` 模擬所有 DB 操作。測試中不連接真實資料庫。

## MySandbox 基本概念

- `MySandbox.queryProcessor` 是 Sandbox VM 執行所有 DB 查詢的唯一入口
- 腳本內的所有 `findV2`、`updateV2`、`call` 等操作，都會呼叫此函式
- 測試時替換此函式，即可攔截並模擬所有 DB 操作
- **務必在 `after()` 中恢復**原始 queryProcessor，避免污染其他測試

## 標準 QueryProcessor Mock 模板

```typescript
import { expect } from 'chai';
import { cloneDeep } from 'lodash';
import { resolve } from 'path';
import { MySandbox } from '@javaCat/MySandbox';
import { generateExecuteFunc, writeRecord } from '../utils';
import { mockRecord, mockRelated } from './mocks';

describe('MyTable 測試', () => {
  let testRecord = cloneDeep(mockRecord);
  const originQueryProcessor = MySandbox.queryProcessor;

  before(() => {
    MySandbox.queryProcessor = async (query): Promise<unknown> => {
      if (query.method === 'findV2') {
        if (query.table === 'relatedtable') return [mockRelated];
        if (query.table === 'othertable') return [];
      } else if (query.method === 'updateV2') {
        if (query.table === 'mytable') {
          writeRecord(testRecord, query);
          return [1];
        }
      } else if (query.method === 'insertV2') {
        if (query.table === 'logtable') return 'LOG001';
      } else if (query.method === 'batchUpdateV2') {
        if (query.table === 'detailtable') {
          return mockDetails.map(r => r._id);
        }
      } else if (query.method === 'call') {
        if (query.table === 'othertable' && query.name === '函式名稱') {
          return JSON.stringify({ success: true });
        }
      } else if (query.method === 'echo') {
        return; // echo 直接略過
      }
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
  });

  beforeEach(() => {
    testRecord = cloneDeep(mockRecord); // 每個 it 都重置
  });

  after(() => {
    MySandbox.queryProcessor = originQueryProcessor; // 務必恢復
  });

  it('...', async () => { /* 測試邏輯 */ });
});
```

## QueryEventEmitter 追蹤模式

用於驗證腳本有沒有對特定表格發出特定查詢（例如確認有執行 `updateV2`）。

```typescript
import { QueryEventEmitter, generateExecuteFunc, writeRecord } from '../utils';

describe('測試', () => {
  const eventEmitter = new QueryEventEmitter();
  const originQueryProcessor = MySandbox.queryProcessor;

  before(() => {
    MySandbox.queryProcessor = async (query): Promise<unknown> => {
      eventEmitter.emit(query.method, query); // 先 emit 事件
      // 再正常處理查詢
      if (query.method === 'updateV2') {
        writeRecord(testRecord, query);
        return [1];
      }
      throw new Error('未處理的查詢: ' + JSON.stringify(query));
    };
  });

  it('應該對 targettable 執行 updateV2', async () => {
    let hasUpdate = false;
    // 在 it 內部添加監聽器（每個 it 獨立）
    eventEmitter.addListener('updateV2', (query) => {
      hasUpdate ||= query.table === 'targettable' && query.body?.status === 'DONE';
    });

    await executeFunc({ args: [testRecord] });

    eventEmitter.removeAllListeners('updateV2'); // 清除監聽器
    expect(hasUpdate).to.be.true;
  });

  after(() => {
    MySandbox.queryProcessor = originQueryProcessor;
  });
});
```

**注意：**
- `QueryEventEmitter` 預設最多 20 個監聽器
- 每個 `it` 結束後應呼叫 `removeAllListeners` 防止跨測試污染
- 可用 `once` 取代 `addListener` + `removeAllListeners`

## 條件式 Mock 工廠函式

當多個測試需要不同的 Mock 配置時，用工廠函式產生不同的 queryProcessor。

```typescript
const buildQueryProcessor = (options: {
  relatedRecord?: SafeRecord2<RelatedBody> | null;
  shouldFail?: boolean;
}): typeof MySandbox.queryProcessor => {
  return async (query): Promise<unknown> => {
    if (query.method === 'findV2') {
      if (query.table === 'relatedtable') {
        if (options.relatedRecord === undefined) return [mockRelated]; // 預設
        if (options.relatedRecord === null) return [];                 // 模擬找不到
        return [options.relatedRecord];
      }
    } else if (query.method === 'updateV2') {
      if (options.shouldFail) throw new Error('模擬 DB 錯誤');
      writeRecord(testRecord, query);
      return [1];
    }
    throw new Error('未處理的查詢: ' + JSON.stringify(query));
  };
};

it('找不到關聯資料時回傳錯誤', async () => {
  MySandbox.queryProcessor = buildQueryProcessor({ relatedRecord: null });
  const result = await executeFunc({ args: [testRecord, null] });
  expect(result).to.include('Error:');
});

it('正常情況', async () => {
  MySandbox.queryProcessor = buildQueryProcessor({});
  const result = await executeFunc({ args: [testRecord, null] });
  expect(result).to.be.undefined;
});
```

## Mock 數據格式（SafeRecord2）

```typescript
// tests/<module>/mocks.ts
import { SafeRecord2 } from '@norwegianForestTypes/index';
import { MyBody, MyLines } from '@norwegianForestTables/module/_type';
import { MyStatus } from '@norwegianForestTables/enum';

export const mockRecord: SafeRecord2<MyBody, MyLines> = {
  _id: 'MOCK001',
  body: {
    name: 'NAME001',
    status: MyStatus.PENDING,
    storeName: 'STORE001',
    total: 1000,
    _createdAt: new Date('2024-01-01T00:00:00Z'),
    _updatedAt: new Date('2024-01-01T00:00:00Z'),
  },
  lines: {
    items: [
      {
        _id: '1',
        itemName: 'ITEM001',
        quantity: 5,
        price: 200,
      },
    ],
  },
};
```

**注意：**
- `_id` 使用簡單字串即可（不需要真實 ObjectId）
- 日期欄位用固定的 `new Date('ISO string')` 避免時間差異
- `lines` 中的每個表身項目需要 `_id` 欄位（`writeRecord` 的 `$set`/`$pull` 依此比對）

## cloneDeep 防污染模式

```typescript
// 頂層宣告（let，不是 const）
let testRecord = cloneDeep(mockRecord);

// 每個 it 前重置
beforeEach(() => {
  testRecord = cloneDeep(mockRecord);
});
```

**必要原因：** Mock 數據（如 `mockRecord`）是 module-level 常數。若直接修改，會影響後續測試。`cloneDeep` 確保每個 `it` 都有獨立的副本。

## before / beforeEach / after 生命週期管理

```typescript
describe('模組測試', () => {
  const originQueryProcessor = MySandbox.queryProcessor; // 保存原始
  let testRecord = cloneDeep(mockRecord);

  // 每個 describe 只設定一次 queryProcessor
  before(() => {
    MySandbox.queryProcessor = async (query) => { /* mock 邏輯 */ };
  });

  // 每個 it 前重置 record（但不重置 queryProcessor）
  beforeEach(() => {
    testRecord = cloneDeep(mockRecord);
  });

  // describe 結束後恢復 queryProcessor
  after(() => {
    MySandbox.queryProcessor = originQueryProcessor;
  });
});
```

## query.method 完整列表

| method | 返回值 | 用途 |
|--------|--------|------|
| `findV2` | `Record[]`（陣列，可為空） | 查詢多筆 |
| `updateV2` | `[1]` | 更新單筆 |
| `insertV2` | `string`（新建記錄的 _id） | 新增單筆 |
| `batchInsertV2` | `string[]` | 批次新增 |
| `batchUpdateV2` | `string[]` | 批次更新 |
| `dangerBatchUpdateV2` | `string[]` | 無條件批次更新 |
| `call` | `JSON.stringify(result)` | 呼叫其他表格 function |
| `find` | `Record[]` | 舊版查詢（部分舊腳本使用） |
| `update` | `[1]` | 舊版更新 |
| `echo` | `undefined` | 日誌（直接 return 略過） |
| `setTodoJob` | `undefined` | TodoJob 狀態更新 |
| `todoJobsV2` | `TodoJobRecord[]` | 查詢 TodoJob |
| `http.json` | 依需求 | HTTP 請求（通常 mock 返回 JSON） |

**原則：** Mock 中遇到未預期的 `query` 應 `throw new Error('未處理的查詢: ' + JSON.stringify(query))`，這樣可以立即發現腳本呼叫了未 mock 的查詢。
