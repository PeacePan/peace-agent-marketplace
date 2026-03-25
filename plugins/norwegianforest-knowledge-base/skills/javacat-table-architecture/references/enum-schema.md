# 列舉定義 (EnumSchema)

列舉（Enum）用於定義欄位的固定選項集合。當欄位的 `valueType` 為 `ENUM` 時，必須在表格的 `enums` 陣列中定義對應的列舉成員。

## EnumSchema 結構

| 屬性 | 型別 | 說明 |
|------|------|------|
| `enumName` | `string` | 列舉名稱，對應欄位的 `enumName` 屬性 |
| `name` | `string` | 列舉成員名稱（值） |
| `displayName` | `string` | 列舉成員的中文顯示名稱 |
| `disabled` | `boolean` | 是否停用此選項（停用後仍保留歷史資料，但不可新選） |
| `description` | `string` | 描述 |

## 定義方式

### 方式一：手動定義

直接在 `enums` 陣列中逐一列出每個成員：

```typescript
enums: [
  { enumName: 'OrderStatus', name: 'PENDING', displayName: '待處理' },
  { enumName: 'OrderStatus', name: 'PROCESSING', displayName: '處理中' },
  { enumName: 'OrderStatus', name: 'COMPLETED', displayName: '已完成' },
  { enumName: 'OrderStatus', name: 'CANCELLED', displayName: '已取消' },
],
```

### 方式二：使用 convertTsEnumToMyTableEnum 轉換

當已有 TypeScript 列舉和對應的 DisplayName 物件時，可使用工具函式自動轉換：

```typescript
// 先定義 TypeScript 列舉
export enum OrderStatus {
  PENDING = 'PENDING',
  PROCESSING = 'PROCESSING',
  COMPLETED = 'COMPLETED',
  CANCELLED = 'CANCELLED',
}

// 定義顯示名稱映射
export const OrderStatusDisplayName: Record<OrderStatus, string> = {
  [OrderStatus.PENDING]: '待處理',
  [OrderStatus.PROCESSING]: '處理中',
  [OrderStatus.COMPLETED]: '已完成',
  [OrderStatus.CANCELLED]: '已取消',
};

// 在表格定義中使用轉換函式
enums: [
  ...convertTsEnumToMyTableEnum('OrderStatus', OrderStatus, OrderStatusDisplayName),
],
```

`convertTsEnumToMyTableEnum` 函式位於 `@norwegianForestLibs/util`，接受三個參數：
1. `enumName`：列舉名稱字串
2. `enumObj`：TypeScript 列舉物件
3. `displayNameObj`：顯示名稱映射物件

## 列舉的組織位置

### 全域列舉
放在 `NorwegianForest/tables/enum.ts`，跨模組共用的業務列舉。

### 模組專用列舉
放在 `NorwegianForest/tables/[模組]/_enum.ts`，僅該模組使用的列舉。

## 列舉命名規範

- **列舉名稱**：PascalCase（如 `OrderStatus`）
- **成員名稱**：SCREAMING_SNAKE_CASE（如 `PENDING`）
- **顯示名稱常數**：列舉名稱 + `DisplayName`（如 `OrderStatusDisplayName`）

## 欄位與列舉的關聯

```typescript
// 欄位定義
{
  ...UPDATE_ENUM,
  name: 'status',
  displayName: '訂單狀態',
  enumName: 'OrderStatus',   // 對應 enums 中 enumName 為 'OrderStatus' 的項目
}

// enums 定義
enums: [
  { enumName: 'OrderStatus', name: 'PENDING', displayName: '待處理' },
  { enumName: 'OrderStatus', name: 'PROCESSING', displayName: '處理中' },
  // ...
],
```
