# 自動編碼 (Auto Key)

自動編碼系統用於在 `KEY` 類型欄位上自動產生唯一的紀錄編號。當主鍵欄位設定了自動編碼，使用者不需手動輸入主鍵值，系統會自動依據設定規則產生。

## 編碼結構

一個自動編碼的完整結構如下：

```
[前綴部分][分隔符][序號/隨機碼][分隔符][後綴部分]
```

## 前綴屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `autoKeyPrefix` | `string` | 固定前綴字串 |
| `autoKeyPrefixByField` | `string` | 動態前綴，取自其他欄位的值（逗號分隔多個欄位） |
| `autoKeyPrefixByDayjs` | `string` | 時間前綴，使用 Dayjs 格式（如 `YYYYMMDD`） |

## 後綴屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `autoKeySuffix` | `string` | 固定後綴字串 |
| `autoKeySuffixByField` | `string` | 動態後綴，取自其他欄位的值（逗號分隔多個欄位） |
| `autoKeySuffixByDayjs` | `string` | 時間後綴，使用 Dayjs 格式 |

## 序號屬性

| 屬性 | 型別 | 說明 |
|------|------|------|
| `autoKeyMinDigits` | `number` | 序號最小位數（不足時前面補零，如 `3` → `001`） |
| `autoKeyInitialNumber` | `number` | 起始號碼 |

## 編碼類型

| 屬性 | 型別 | 說明 |
|------|------|------|
| `autoKeyNonSerialId` | `boolean` | 使用隨機產生編碼（不可排序） |
| `autoKeySerialId` | `boolean` | 使用隨機產生編碼（可排序） |
| `autoKeyTimestampId` | `boolean` | 使用時間序編碼（可排序） |
| `autoKeyFixedString` | `string` | 使用固定字串編碼（需搭配動態前後綴避免衝突） |

## 分隔符

| 屬性 | 型別 | 說明 |
|------|------|------|
| `autoKeySep` | `string` | 分隔符號（如 `-`） |

## 搭配設定

使用自動編碼的主鍵欄位通常使用 `READ_KEY_FIELD` preset，因為使用者不需要也不應該手動輸入主鍵值。

```typescript
{
  ...READ_KEY_FIELD,
  name: 'name',
  displayName: '採購單號',
  autoKeyPrefix: 'PO',
  autoKeyPrefixByDayjs: 'YYYYMMDD',
  autoKeySep: '-',
  autoKeyMinDigits: 4,
  autoKeyInitialNumber: 1,
}
// 產生編號如: PO20260325-0001, PO20260325-0002
```

## 常見組合範例

### 日期序號型
```typescript
autoKeyPrefix: 'SO',
autoKeyPrefixByDayjs: 'YYYYMMDD',
autoKeySep: '-',
autoKeyMinDigits: 4,
// SO20260325-0001
```

### 動態前綴型
```typescript
autoKeyPrefixByField: 'storeCode',
autoKeySep: '-',
autoKeyMinDigits: 6,
// A001-000001
```

### 純隨機型
```typescript
autoKeyTimestampId: true,
// 產生時間序可排序的隨機 ID
```
