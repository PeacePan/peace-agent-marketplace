# JavaCat 表格系統架構總覽

## 系統定位

JavaCat 是一個運行在 AWS 上的 Serverless 服務，它的核心能力是透過**抽象的表格定義（Table Definition）**動態產生 GraphQL 伺服器。開發者不需要手動撰寫 GraphQL schema 或 resolver，只需定義表格結構，JavaCat 就會自動處理資料庫操作、權限控制、驗證邏輯等。

NorwegianForest 是 JavaCat 的子專案，專門負責定義業務表格。兩者的關係類似「大腦」與「身體器官」——JavaCat 提供運行時核心，NorwegianForest 提供具體的業務表格定義。

## 表格定義的資料流

```
NorwegianForest 定義表格 (TypeScript)
  ↓ npm run print / npm run patch
JavaCat 資料庫存放表格定義 (DocumentDB)
  ↓ 啟動時讀取
JavaCat 動態產生 GraphQL Server
  ↓ 提供 API
前端中台 / 其他服務
```

## 表格的兩層結構

每個表格定義由兩大部分組成：

### 1. 表頭 (Body)
表格的**紀錄級別**資料。每筆紀錄有一組表頭欄位，類似傳統資料庫中的一列。

### 2. 表身 (Lines)
表格的**明細級別**資料。每筆紀錄可以有多個表身區段（Line），每個區段包含多列（Row）。

這類似於 ERP 系統中的「單頭 + 單身」結構。例如一張採購單：
- 表頭：採購單號、供應商、日期
- 表身「明細」：品項、數量、單價（多列）

## MyTableRecord 完整結構

一個完整的表格定義物件 (`SafeMyTable`) 包含：

```typescript
{
  body: {
    // 表格基本資訊 (MyTableBody)
    name: string;           // 表格名稱
    displayName: string;    // 顯示名稱
    type: TableType;        // 表格類型
    group?: string;         // 業務群組
    schemaVer: string;      // 架構版本
    version?: number;       // 表格版本
    // ... 更多表格層級設定
  },
  lines: {
    bodyFields: FieldSchema[];           // 表頭欄位定義
    lineFields?: LineFieldSchema[];      // 表身欄位定義
    lines?: LineSchema[];                // 表身定義
    enums?: EnumSchema[];                // 列舉定義
    policies?: MyTablePolicy[];          // 政策驗證
    hooks?: MyTableHook[];               // 生命週期掛勾
    functions?: MyTableFunction[];       // 業務函數
    arguments?: MyTableFunctionArgument[]; // 函數參數
    crons?: MyTableCron[];               // 排程任務
    events?: MyTableEvent[];             // 事件
    approvalChain?: MyTableApprovalChain[]; // 簽核路徑
    libs?: MyTableLib[];                 // 共用函式庫
    fieldGroups?: MyTableFieldGroup[];   // 欄位群組
    searchSuggestions?: MyTableSearchSuggestions[]; // 查詢提示
  }
}
```

## 原始碼位置

| 項目 | 路徑 |
|------|------|
| 型別定義 (FieldSchema, LineSchema 等) | `JavaCat/src/lib2/@type/const.ts` |
| 列舉定義 (FieldType, FieldValueType 等) | `JavaCat/src/lib2/@type/enum.ts` |
| 表格型別 (MyTableBody, SafeMyTable 等) | `JavaCat/src/lib2/@type/tables/table.ts` |
| 表格驗證 | `JavaCat/src/lib2/MyTable/assert.ts` |
| 表格工具函式 | `JavaCat/src/lib2/MyTable/util.ts` |
| 系統表格定義 | `JavaCat/src/lib2/MyTable/tables/systemTableV2/` |
| NorwegianForest 表格定義 | `NorwegianForest/tables/[模組]/[表格名稱].ts` |
| NorwegianForest 欄位預設模板 | `NorwegianForest/libs/preset.ts` |
