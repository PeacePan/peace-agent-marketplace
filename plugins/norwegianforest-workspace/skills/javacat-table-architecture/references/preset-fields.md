# 欄位預設模板 (Preset Fields)

預設模板是預先定義好的欄位屬性組合，用於簡化欄位定義的撰寫。使用展開運算符（spread operator）將模板屬性套用到欄位定義中。

## 命名規範

模板命名格式：`[權限]_[空值標識]_[資料類型]`

- **權限**：`INSERT`、`UPDATE`、`READ`
- **空值標識**：`NULLABLE`（可選，有則代表 `allowNull: true`）
- **資料類型**：`STRING`、`INT`、`FLOAT`、`FLOAT_INT`、`BOOLEAN`、`DATE`、`ENUM`、`KEY_FIELD`、`REF_KEY_FIELD`、`FILE2`、`ID`

## 完整模板清單

### 主鍵欄位

| 模板名稱 | fieldType | valueType | readWrite | 說明 |
|---------|-----------|-----------|-----------|------|
| `KEY_FIELD` | KEY | STRING | INSERT | 使用者輸入主鍵 |
| `READ_KEY_FIELD` | KEY | STRING | READ | 自動編碼主鍵 |

### 參考欄位 (REF_KEY)

| 模板名稱 | fieldType | valueType | readWrite | allowNull | 說明 |
|---------|-----------|-----------|-----------|-----------|------|
| `INSERT_REF_KEY_FIELD` | REF_KEY | STRING | INSERT | - | 建立時選擇關聯 |
| `INSERT_NULLABLE_REF_KEY_FIELD` | REF_KEY | STRING | INSERT | true | 建立時可選關聯 |
| `UPDATE_REF_KEY_FIELD` | REF_KEY | STRING | UPDATE | - | 可修改關聯 |
| `UPDATE_NULLABLE_REF_KEY_FIELD` | REF_KEY | STRING | UPDATE | true | 可修改可空關聯 |
| `READ_REF_KEY_FIELD` | REF_KEY | STRING | READ | - | 唯讀關聯 |
| `READ_NULLABLE_REF_KEY_FIELD` | REF_KEY | STRING | READ | true | 唯讀可空關聯 |

### 字串欄位 (STRING)

| 模板名稱 | fieldType | valueType | readWrite | allowNull |
|---------|-----------|-----------|-----------|-----------|
| `INSERT_STRING` | DATA | STRING | INSERT | - |
| `INSERT_NULLABLE_STRING` | DATA | STRING | INSERT | true |
| `UPDATE_STRING` | DATA | STRING | UPDATE | - |
| `UPDATE_NULLABLE_STRING` | DATA | STRING | UPDATE | true |
| `READ_STRING` | DATA | STRING | READ | - |
| `READ_NULLABLE_STRING` | DATA | STRING | READ | true |

### 整數欄位 (INT)

| 模板名稱 | fieldType | valueType | readWrite | allowNull |
|---------|-----------|-----------|-----------|-----------|
| `INSERT_INT` | DATA | INT | INSERT | - |
| `INSERT_NULLABLE_INT` | DATA | INT | INSERT | true |
| `UPDATE_INT` | DATA | INT | UPDATE | - |
| `UPDATE_NULLABLE_INT` | DATA | INT | UPDATE | true |
| `READ_INT` | DATA | INT | READ | - |
| `READ_NULLABLE_INT` | DATA | INT | READ | true |

### 浮點數欄位 (FLOAT)

| 模板名稱 | fieldType | valueType | readWrite | allowNull |
|---------|-----------|-----------|-----------|-----------|
| `INSERT_FLOAT` | DATA | FLOAT | INSERT | - |
| `INSERT_NULLABLE_FLOAT` | DATA | FLOAT | INSERT | true |
| `UPDATE_FLOAT` | DATA | FLOAT | UPDATE | - |
| `UPDATE_NULLABLE_FLOAT` | DATA | FLOAT | UPDATE | true |
| `READ_FLOAT` | DATA | FLOAT | READ | - |
| `READ_NULLABLE_FLOAT` | DATA | FLOAT | READ | true |

### 浮點數整數欄位 (FLOAT_INT)

| 模板名稱 | fieldType | valueType | readWrite | allowNull |
|---------|-----------|-----------|-----------|-----------|
| `INSERT_FLOAT_INT` | DATA | FLOAT_INT | INSERT | - |
| `INSERT_NULLABLE_FLOAT_INT` | DATA | FLOAT_INT | INSERT | true |
| `UPDATE_FLOAT_INT` | DATA | FLOAT_INT | UPDATE | - |
| `UPDATE_NULLABLE_FLOAT_INT` | DATA | FLOAT_INT | UPDATE | true |
| `READ_FLOAT_INT` | DATA | FLOAT_INT | READ | - |
| `READ_NULLABLE_FLOAT_INT` | DATA | FLOAT_INT | READ | true |

### 布林欄位 (BOOLEAN)

| 模板名稱 | fieldType | valueType | readWrite | allowNull |
|---------|-----------|-----------|-----------|-----------|
| `INSERT_BOOLEAN` | DATA | BOOLEAN | INSERT | - |
| `INSERT_NULLABLE_BOOLEAN` | DATA | BOOLEAN | INSERT | true |
| `UPDATE_BOOLEAN` | DATA | BOOLEAN | UPDATE | - |
| `UPDATE_NULLABLE_BOOLEAN` | DATA | BOOLEAN | UPDATE | true |
| `READ_BOOLEAN` | DATA | BOOLEAN | READ | - |
| `READ_NULLABLE_BOOLEAN` | DATA | BOOLEAN | READ | true |

### 日期欄位 (DATE)

| 模板名稱 | fieldType | valueType | readWrite | allowNull |
|---------|-----------|-----------|-----------|-----------|
| `INSERT_DATE` | DATA | DATE | INSERT | - |
| `INSERT_NULLABLE_DATE` | DATA | DATE | INSERT | true |
| `UPDATE_DATE` | DATA | DATE | UPDATE | - |
| `UPDATE_NULLABLE_DATE` | DATA | DATE | UPDATE | true |
| `READ_DATE` | DATA | DATE | READ | - |
| `READ_NULLABLE_DATE` | DATA | DATE | READ | true |

### 列舉欄位 (ENUM)

| 模板名稱 | fieldType | valueType | readWrite | allowNull |
|---------|-----------|-----------|-----------|-----------|
| `INSERT_ENUM` | DATA | ENUM | INSERT | - |
| `INSERT_NULLABLE_ENUM` | DATA | ENUM | INSERT | true |
| `UPDATE_ENUM` | DATA | ENUM | UPDATE | - |
| `UPDATE_NULLABLE_ENUM` | DATA | ENUM | UPDATE | true |
| `READ_ENUM` | DATA | ENUM | READ | - |
| `READ_NULLABLE_ENUM` | DATA | ENUM | READ | true |

### 檔案欄位 (FILE2)

| 模板名稱 | fieldType | valueType | readWrite | allowNull | 說明 |
|---------|-----------|-----------|-----------|-----------|------|
| `INSERT_FILE2` | REF_KEY | STRING | INSERT | - | 建立時上傳檔案 |
| `INSERT_NULLABLE_FILE2` | REF_KEY | STRING | INSERT | true | 建立時可選上傳 |
| `UPDATE_FILE2_FIELD` | REF_KEY | STRING | UPDATE | - | 可更新檔案 |
| `UPDATE_NULLABLE_FILE2_FIELD` | REF_KEY | STRING | UPDATE | true | 可更新可空檔案 |

檔案欄位本質上是 `REF_KEY` 關聯到系統表格 `__file2__` 的 `name` 欄位。

### ID 欄位

| 模板名稱 | fieldType | valueType | readWrite | allowNull |
|---------|-----------|-----------|-----------|-----------|
| `INSERT_ID` | DATA | ID | INSERT | - |
| `READ_NULLABLE_ID` | DATA | ID | READ | true |

## 使用方式

```typescript
{
  ...UPDATE_STRING,            // 展開預設模板
  name: 'memo',                // 欄位名稱
  displayName: '備註',          // 顯示名稱
  isMultipleLine: true,        // 額外的特殊屬性
  allowNull: true,             // 覆蓋模板的預設值
}
```

模板的屬性可以被後面的屬性覆蓋，所以如果模板中 `allowNull` 未設定，但你需要允許空值，可以在展開後直接設定。

## 選擇模板的思考流程

1. **決定權限**：使用者需要寫入嗎？建立後可以修改嗎？
   - 建立後不可改 → `INSERT`
   - 可隨時修改 → `UPDATE`
   - 不可操作 → `READ`

2. **決定是否可空**：這個欄位是必填還是選填？
   - 必填 → 不加 `NULLABLE`
   - 選填 → 加 `NULLABLE`

3. **決定資料類型**：這個欄位存什麼類型的資料？
   - 文字 → `STRING`
   - 整數 → `INT`
   - 小數 → `FLOAT`
   - 是否 → `BOOLEAN`
   - 選項 → `ENUM`
   - 日期 → `DATE`
   - 關聯 → `REF_KEY_FIELD`
   - 檔案 → `FILE2`
   - 主鍵 → `KEY_FIELD`
