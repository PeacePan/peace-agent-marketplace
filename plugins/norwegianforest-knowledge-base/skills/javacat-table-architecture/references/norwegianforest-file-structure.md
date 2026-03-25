# NorwegianForest 表格定義檔案結構

NorwegianForest 是 JavaCat 的子專案，專門管理業務表格定義。本章說明如何在 NorwegianForest 中建立和管理表格。

## 目錄結構

```
NorwegianForest/
├── tables/
│   ├── const.ts                     # 表格常數（TABLE_NAME, TABLE_DISPLAY_NAME, TABLE_GROUP）
│   ├── enum.ts                      # 全域列舉定義
│   ├── _type.ts                     # 全域型別定義
│   ├── index.ts                     # 表格匯出與部署入口
│   ├── [模組]/
│   │   ├── [tableName].ts          # 表格定義主檔
│   │   ├── _type.ts                # 模組型別定義
│   │   ├── _enum.ts                # 模組列舉定義
│   │   └── scripts/[tableName]/
│   │       ├── policy.ts           # 政策驗證腳本
│   │       ├── beforeInsert.ts     # 新增前掛勾
│   │       ├── beforeUpdate.ts     # 更新前掛勾
│   │       ├── [function].ts       # 業務函數腳本
│   │       └── [function].cron.ts  # 排程腳本
│   └── libs/
│       └── preset.ts               # 欄位預設模板
```

## 常數檔案 (tables/const.ts)

### TABLE_NAME

定義表格的程式識別名稱，使用 `Object.freeze()` 建立不可變物件：

```typescript
export const TABLE_NAME = Object.freeze({
  // 按業務模組分組
  // POS
  POS_SALE: 'possale',
  POS_PAYMENT: 'pospayment',
  // 採購
  PURCHASE_ORDER: 'purchaseorder',
});
```

命名規範：
- 常數名稱：SCREAMING_SNAKE_CASE（如 `PURCHASE_ORDER`）
- 字串值：全小寫英文（如 `'purchaseorder'`），符合 `/^[a-z0-9_]{2,100}$/`

### TABLE_DISPLAY_NAME

定義表格的中文顯示名稱：

```typescript
export enum TABLE_DISPLAY_NAME {
  POS_SALE = 'POS銷售',
  POS_PAYMENT = 'POS收款',
  PURCHASE_ORDER = '採購單',
}
```

### TABLE_GROUP

定義表格所屬的業務群組：

```typescript
export enum TABLE_GROUP {
  POS = 'POS',
  PROCUREMENT = '採購',
  INVENTORY = '庫存',
}
```

## 型別定義 (tables/[模組]/_type.ts)

每個模組需要定義對應的 TypeScript 型別：

```typescript
import { SafeMyTable } from '@JavaCat/src/lib2/@type/tables/table';

// 表頭型別
export type PurchaseOrderBody = {
  name: string;
  supplierName: string;
  orderDate: Date;
  // ...
};

// 表身型別
export type PurchaseOrderLines = {
  detail: {
    productId: string;
    quantity: number;
    unitPrice: number;
  };
};

// 完整表格記錄型別
export type PurchaseOrderTableRecord = SafeMyTable<
  keyof PurchaseOrderBody,
  keyof PurchaseOrderLines,
  // ... 更多泛型參數
>;
```

命名規範：
- 表頭型別：`[表格名稱PascalCase]Body`
- 表身型別：`[表格名稱PascalCase]Lines`
- 記錄型別：`[表格名稱PascalCase]TableRecord`

## 表格定義主檔 (tables/[模組]/[tableName].ts)

完整的表格定義範例：

```typescript
import * as path from 'path';
import { readCompiledScript } from '@norwegianForestLibs/compile';
import { TableType } from '@norwegianForestLibs/enum';
import {
  KEY_FIELD, READ_KEY_FIELD,
  UPDATE_STRING, UPDATE_NULLABLE_STRING,
  UPDATE_INT, INSERT_REF_KEY_FIELD,
  UPDATE_ENUM,
} from '@norwegianForestLibs/preset';
import { convertTsEnumToMyTableEnum } from '@norwegianForestLibs/util';
import { TABLE_NAME, TABLE_DISPLAY_NAME, TABLE_GROUP } from '../const';
import { OrderStatus, OrderStatusDisplayName } from './_enum';
import { PurchaseOrderTableRecord } from './_type';
import { LineReadWrite } from '@norwegianForestLibs/enum';

const scriptDir = path.resolve(__dirname, './scripts/purchaseorder');

export const purchaseorderTableRecord: PurchaseOrderTableRecord = {
  body: {
    name: TABLE_NAME.PURCHASE_ORDER,
    displayName: TABLE_DISPLAY_NAME.PURCHASE_ORDER,
    type: TableType.DATA,
    group: TABLE_GROUP.PROCUREMENT,
    schemaVer: '2',
    version: null,
    nameField: 'name',
    displayNameField: 'name',
  },
  lines: {
    bodyFields: [
      {
        ...KEY_FIELD,
        name: 'name',
        displayName: '採購單號',
      },
      {
        ...INSERT_REF_KEY_FIELD,
        name: 'supplierName',
        displayName: '供應商',
        refTableName: 'supplier',
        refFieldName: 'name',
        refDataFields: 'displayName',
      },
      {
        ...UPDATE_ENUM,
        name: 'status',
        displayName: '狀態',
        enumName: 'OrderStatus',
      },
    ],
    lineFields: [
      {
        ...INSERT_REF_KEY_FIELD,
        lineName: 'detail',
        name: 'productId',
        displayName: '商品',
        refTableName: 'product',
        refFieldName: 'name',
      },
      {
        ...UPDATE_INT,
        lineName: 'detail',
        name: 'quantity',
        displayName: '數量',
        numberMin: 1,
      },
    ],
    lines: [
      {
        name: 'detail',
        displayName: '採購明細',
        readWrite: LineReadWrite.FULL,
      },
    ],
    enums: [
      ...convertTsEnumToMyTableEnum('OrderStatus', OrderStatus, OrderStatusDisplayName),
    ],
    policies: [
      {
        name: 'validateOrder',
        script: readCompiledScript(path.resolve(scriptDir, 'policy.ts')),
      },
    ],
  },
};
```

## 部署流程

### 新增表格
1. 在 `tables/const.ts` 新增 TABLE_NAME 和 TABLE_DISPLAY_NAME
2. 建立表格定義檔案
3. 在 `tables/index.ts` 中匯出
4. 執行 `npm run print ${表格名稱}` 產生 GraphQL 內容
5. 使用 `npm run insert ${表格名稱}` 新增到資料庫

### 更新表格
1. 修改表格定義
2. 執行 `npm run patch ${表格名稱}` 更新到資料庫

### 命名規範總整理

| 項目 | 格式 | 範例 |
|------|------|------|
| 檔案名稱 | 全小寫，與 TABLE_NAME 值一致 | `purchaseorder.ts` |
| 欄位名稱 | camelCase | `supplierName` |
| 列舉名稱 | PascalCase | `OrderStatus` |
| 列舉成員 | SCREAMING_SNAKE_CASE | `PENDING` |
| 型別名稱 | PascalCase + 後綴 | `PurchaseOrderTableRecord` |
| TABLE_NAME 常數 | SCREAMING_SNAKE_CASE | `PURCHASE_ORDER` |
| TABLE_NAME 字串值 | 全小寫英文 | `'purchaseorder'` |
