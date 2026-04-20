---
name: javacat-table-architecture
description: >
  JavaCat 表格定義系統完整架構知識。涵蓋 FieldSchema、LineSchema、EnumSchema、
  MyTableBody、預設模板（Preset）、自動編碼（Auto Key）、系統內建欄位、腳本掛勾、
  以及 NorwegianForest 專案的檔案結構與命名規範。當需要撰寫、修改、或理解任何
  JavaCat/NorwegianForest 表格定義時，務必先讀此 skill。適用場景包括：建立新表格、
  修改既有表格欄位、理解欄位屬性含義、推論欄位的 fieldType/valueType/readWrite、
  設定自動編碼、定義列舉、建立表身、撰寫政策或掛勾腳本。
---

# JavaCat 表格定義架構

JavaCat 是運行在 AWS 上的 Serverless 服務，透過抽象的表格定義動態產生 GraphQL 伺服器。NorwegianForest 是負責定義業務表格的子專案。

## 參考文件目錄

| 章節 | 內容摘要 | 何時閱讀 |
|------|---------|---------|
| [architecture-overview.md](references/architecture-overview.md) | 系統定位、資料流、MyTableRecord 完整結構、原始碼位置 | 第一次了解表格系統架構 |
| [table-body.md](references/table-body.md) | MyTableBody 表格表頭：TableType、IdType、簽核、資料庫設定 | 建立新表格或修改表格元資料 |
| [field-schema.md](references/field-schema.md) | FieldSchema 完整屬性：FieldType、FieldValueType、FieldReadWrite、參考欄位、驗證規則 | 定義或修改欄位屬性（最重要的參考） |
| [auto-key.md](references/auto-key.md) | 自動編碼系統：前綴、後綴、序號、編碼類型 | 設定主鍵自動編碼 |
| [line-schema.md](references/line-schema.md) | LineSchema 表身定義、LineFieldSchema、LineReadWrite 權限矩陣 | 定義或修改表身結構 |
| [enum-schema.md](references/enum-schema.md) | EnumSchema 列舉定義、convertTsEnumToMyTableEnum 工具函式 | 定義或修改列舉選項 |
| [preset-fields.md](references/preset-fields.md) | 全部預設模板清單、選擇模板思考流程 | 撰寫欄位定義時選用正確的 preset |
| [builtin-fields.md](references/builtin-fields.md) | 系統內建欄位（表頭/表身）、保留字、值型別約束 | 了解系統自動管理的欄位 |
| [scripts-and-hooks.md](references/scripts-and-hooks.md) | Policy、Hook、Function、Cron、ApprovalChain、Lib | 撰寫腳本或設定進階功能 |
| [norwegianforest-file-structure.md](references/norwegianforest-file-structure.md) | NorwegianForest 目錄結構、常數定義、型別定義、部署流程、命名規範 | 在 NorwegianForest 中建立或修改表格檔案 |

## 快速定位

- **建立新表格** → 先讀 [norwegianforest-file-structure.md](references/norwegianforest-file-structure.md)，再讀 [table-body.md](references/table-body.md)
- **定義欄位** → [field-schema.md](references/field-schema.md) + [preset-fields.md](references/preset-fields.md)
- **設定自動編碼** → [auto-key.md](references/auto-key.md)
- **建立表身** → [line-schema.md](references/line-schema.md)
- **定義列舉** → [enum-schema.md](references/enum-schema.md)
- **撰寫腳本** → [scripts-and-hooks.md](references/scripts-and-hooks.md)
- **了解系統欄位** → [builtin-fields.md](references/builtin-fields.md)
- **了解整體架構** → [architecture-overview.md](references/architecture-overview.md)

## 核心概念速覽

### 表格結構

```
MyTableRecord
├── body (表頭元資料)
│   ├── name, displayName, type, group, schemaVer ...
└── lines
    ├── bodyFields[]      → FieldSchema (表頭欄位)
    ├── lineFields[]      → LineFieldSchema (表身欄位)
    ├── lines[]           → LineSchema (表身定義)
    ├── enums[]           → EnumSchema (列舉)
    ├── policies[]        → 政策驗證
    ├── hooks[]           → 生命週期掛勾
    ├── functions[]       → 業務函數
    └── crons[]           → 排程任務
```

### 欄位定義三要素

每個欄位的核心由三個屬性決定：

1. **fieldType**（角色）：`KEY` | `DATA` | `REF_KEY` | `DERIVE` | `FUNCTION`
2. **valueType**（資料型別）：`STRING` | `INT` | `FLOAT` | `BOOLEAN` | `ENUM` | `DATE` | `ID`
3. **readWrite**（使用者權限）：`INSERT` | `UPDATE` | `READ`

### Preset 命名公式

```
[權限]_[NULLABLE]_[資料類型]
```

例如 `UPDATE_NULLABLE_STRING` = 可更新、可空值、字串欄位。
