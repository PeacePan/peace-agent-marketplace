# FieldSchema 欄位定義

FieldSchema 是表格系統中最核心的型別，定義了表頭（Body）中每一個欄位的結構與行為。

## 必要屬性

| 屬性 | 型別 | 可否修改 | 說明 |
|------|------|---------|------|
| `name` | `string` | 不可修改 | 欄位名稱，camelCase 格式，符合 `/^[_a-zA-Z][_a-zA-Z0-9]{0,59}$/` |
| `displayName` | `string` | 可修改 | 中文顯示名稱 |
| `fieldType` | `FieldType` | 不可修改 | 欄位類型 |
| `valueType` | `FieldValueType` | 不可修改 | 資料型別 |
| `readWrite` | `FieldReadWrite` | 可修改 | 使用者讀寫權限 |

## FieldType 欄位類型

| 值 | 說明 | 限制 |
|----|------|------|
| `KEY` | 主鍵欄位 | 只能用在表頭；`allowNull` 必須為 `false`（除非有自動編碼）；`readWrite` 必須為 `INSERT` |
| `DATA` | 資料欄位 | 一般資料儲存，最常用 |
| `REF_KEY` | 參考欄位 | 參考（關聯）到另一個表格的紀錄，必須設定 `refTableName` 和 `refFieldName` |
| `REF_DATA` | 參考資料欄位 | 開發者不使用，系統自動產生給前端讀取 |
| `DERIVE` | 推導欄位 | 資料庫不存在此欄位，由程式計算產生；`readWrite` 必須為 `READ` |
| `FUNCTION` | 函數欄位 | 用於觸發函數操作 |

## FieldValueType 資料型別

| 值 | 說明 | 適用場景 |
|----|------|---------|
| `ID` | ID/UUID 字串 | 系統識別碼 |
| `STRING` | 字串 | 文字、名稱、地址、備註 |
| `INT` | 整數 | 數量、個數、不含小數的金額 |
| `FLOAT_INT` | 浮點數整數 | 以浮點數儲存但概念上為整數的值 |
| `FLOAT` | 浮點數 | 重量、長度、比率、含小數的金額 |
| `BOOLEAN` | 布林值 | 是/否的二元狀態 |
| `ENUM` | 列舉 | 有固定選項的狀態、類型 |
| `DATE` | 日期時間 | 時間點 |

## FieldReadWrite 讀寫權限

控制**使用者**（前端）對欄位的操作權限：

| 值 | 說明 | 使用時機 |
|----|------|---------|
| `INSERT` | 建立時可寫入，之後不可更新 | 主鍵、建立後不應修改的欄位 |
| `UPDATE` | 建立和更新時都可寫入 | 一般可編輯欄位 |
| `READ` | 僅供讀取，不可寫入 | 系統自動產生的欄位、計算欄位 |

## scriptReadWrite 腳本讀寫權限

控制**腳本**（後端程式）對欄位的操作權限，與 `readWrite` 獨立運作：

- 未設定時：腳本遵循 `readWrite` 的權限
- `INSERT`：腳本只能在建立時寫入
- `UPDATE`：腳本在建立和更新時都可寫入
- `READ`：腳本不可寫入

常見搭配：
- `readWrite: READ` + `scriptReadWrite: INSERT`：使用者不可操作，系統在建立時自動填入（如建立時間）
- `readWrite: READ` + `scriptReadWrite: UPDATE`：使用者不可操作，系統可隨時更新（如計算欄位）
- `readWrite: UPDATE` + `scriptReadWrite: UPDATE`：使用者和系統都可操作

## 參考欄位屬性

當 `fieldType` 為 `REF_KEY` 時，需要設定以下屬性來建立表格間的關聯：

| 屬性 | 型別 | 可否修改 | 說明 |
|------|------|---------|------|
| `refTableName` | `string` | 不可修改 | 關聯的目標表格名稱 |
| `refFieldName` | `string` | 不可修改 | 關聯的目標欄位名稱 |
| `refDataFields` | `string` | 可修改 | 要附帶顯示的目標表格欄位（逗號分隔） |
| `refByTx` | `boolean` | 可修改 | 是否使用資料庫交易來檢查參考完整性（會降低效能） |
| `refLimitField` | `string` | 可修改 | 參考限制欄位 |
| `bypassRefData` | `boolean` | 可修改 | 跳過此參考欄位的參考資料 |
| `disableRefData` | `boolean` | 可修改 | 禁止其他表格參考本欄位產生 REF_DATA |

## 列舉欄位屬性

當 `valueType` 為 `ENUM` 時：

| 屬性 | 型別 | 可否修改 | 說明 |
|------|------|---------|------|
| `enumName` | `string` | 不可修改 | 對應的列舉名稱，必須在 `enums` 陣列中定義 |

## 欄位修飾

| 屬性 | 型別 | 說明 |
|------|------|------|
| `allowNull` | `boolean` | 寫入時允許空值。核心欄位通常為 `false`，補充資訊可設為 `true` |
| `unique` | `boolean` | 唯一約束（僅限表頭欄位，不可修改） |
| `groupName` | `string` | 欄位群組名稱，用於 UI 分組顯示 |
| `isHidden` | `boolean` | 是否隱藏（不在前端 UI 顯示） |
| `defaultField` | `boolean` | 是否為清單頁預設顯示欄位 |
| `defaultRefField` | `string` | 預設顯示的關聯欄位 |
| `exampleValue` | `string` | 範例值，供文件使用 |
| `defaultValue` | `string` | 預設值（僅接受字串格式，布林數字等也用字串表示） |
| `ordering` | `number` | 顯示排序 |
| `enableInlineEditing` | `boolean` | 是否允許清單頁行內編輯 |
| `description` | `string` | 欄位描述，滑鼠懸停時顯示 |
| `mapsTo` | `string` | 欄位名稱映射，用於 Athena 等外部資料來源 |
| `fieldLevel` | `FieldLevel` | 欄位層級（`SYSTEM` 或 `CUSTOM`） |
| `placeholder` | `string` | 輸入框提示文字 |

## 資料驗證

### 數值驗證

| 屬性 | 型別 | 說明 |
|------|------|------|
| `numberMin` | `number` | 最小值（如金額不可為負數，設為 `0`） |
| `numberMax` | `number` | 最大值 |

### 日期驗證

| 屬性 | 型別 | 說明 |
|------|------|------|
| `dateMin` | `number` | 最小日期 |
| `dateMax` | `number` | 最大日期 |

### 字串驗證

| 屬性 | 型別 | 說明 |
|------|------|------|
| `minLength` | `number` | 最小長度 |
| `maxLength` | `number` | 最大長度 |
| `regExp` | `string` | 正規表示式驗證 |
| `isEmail` | `boolean` | 電子郵件格式驗證 |
| `maxEmailCount` | `number` | 最大信箱數量 |
| `mobileLocale` | `string` | 手機號碼驗證（地區，逗號分隔） |
| `noWhiteSpace` | `NoWhiteSpace` | 空白字元限制 |
| `charWidth` | `CharWidth` | 字元寬度限制 |
| `allowChar` | `string` | 允許的字元 |
| `disallowChar` | `string` | 不允許的字元 |
| `namingConvention` | `NamingConvention` | 命名慣例驗證 |
| `fileSizeLimitByte` | `number` | 檔案大小限制（Byte） |

### NoWhiteSpace 空白字元檢查

| 值 | 說明 |
|----|------|
| `ALL` | 不允許任何空白字元 |
| `ALLOW_INNER_SINGLE_SPACE` | 允許字串中單一空格字元 |
| `EXCEPT_SPACE` | 除了空格都禁用 |
| `NO_LEADING_SPACE_AND_TRAILING_SPACE` | 不允許前後空白，中間不能連續兩個空白 |

### CharWidth 字元寬度檢查

| 值 | 說明 |
|----|------|
| `ALL_HALF_WIDTH` | 全為半形 |
| `ALL_FULL_WIDTH` | 全為全形 |
| `NO_HALF_WIDTH` | 禁止半形 |
| `NO_FULL_WIDTH` | 禁止全形 |

### NamingConvention 命名慣例

| 值 | 說明 |
|----|------|
| `SCREAMING_SNAKE_CASE` | 如 `MY_CONSTANT` |
| `CAMEL_CASE` | 如 `myVariable` |
| `PASCAL_CASE` | 如 `MyClass` |
| `SNAKE_CASE` | 如 `my_variable` |

## 時間顯示

| 屬性 | 型別 | 說明 |
|------|------|------|
| `timeGranularity` | `TimeGranularity` | 顯示精度：`SECOND`、`MILLISECOND`、`MINUTE`、`HOUR`、`DAY` |
| `timezoneOffset` | `number` | 時區偏移（-12 到 +14 小時） |

## 多行與多值

| 屬性 | 型別 | 說明 |
|------|------|------|
| `isMultipleLine` | `boolean` | 前端顯示為多行文字輸入框 |
| `useHTML` | `boolean` | 前端顯示為 HTML 編輯器 |
| `multiple` | `number` | 多值欄位（前端用） |

## 表格選擇器

| 屬性 | 型別 | 說明 |
|------|------|------|
| `tableSelector` | `TableSelector` | 選擇器類型：`TableName`、`BodyField`、`Line`、`LineField` |
| `tableSourceField` | `string` | 表格名稱來源欄位 |
| `tableLineSourceField` | `string` | 表身名稱來源欄位 |

## 函數欄位

| 屬性 | 型別 | 說明 |
|------|------|------|
| `functionName` | `string` | 關聯的函數名稱 |
| `functionEffectFields` | `string` | 函數影響的欄位（逗號分隔） |

## 其他

| 屬性 | 型別 | 說明 |
|------|------|------|
| `draftable` | `boolean` | 是否允許草稿狀態 |
| `publishOn` | `string` | 發布控制 |
| `refEnumDisplayNameField` | `string` | 參考列舉顯示名稱欄位（前端用） |
| `refEnumSearchArguments` | `string` | 參考列舉搜尋參數（前端用） |
