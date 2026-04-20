# 系統內建欄位 (Builtin Fields)

JavaCat 會自動為每個表格的表頭和表身注入系統欄位。這些欄位以底線 `_` 開頭，由系統自動管理，開發者不需要手動定義。

## 表頭系統欄位 (BUILTIN_BODY_FIELD)

### 系統行為欄位

| 欄位名稱 | 顯示名稱 | 型別 | 說明 |
|---------|---------|------|------|
| `_id` | 系統編號 | SystemId | 系統主鍵，ObjectId |
| `_gId` | 全域識別碼 | string | UUID v4，不會因紀錄更新而變動 |
| `_createdAt` | 建立時間 | Date | 紀錄建立時間 |
| `_createdBy` | 建立者 | string | 建立者的使用者 ID |
| `_createdBy_displayName` | 建立者.使用者名稱 | string | 建立者的顯示名稱 |
| `_updateId` | 更新識別碼 | SystemId | ObjectId，每次紀錄更新都會變動 |
| `_updatedAt` | 更新時間 | Date | 最後更新時間 |
| `_updatedBy` | 更新者 | string | 最後更新者的使用者 ID |
| `_updatedBy_displayName` | 更新者.使用者名稱 | string | 更新者的顯示名稱 |
| `_archivedAt` | 封存時間 | Date | 封存時間 |
| `_archivedBy` | 封存者 | string | 封存者的使用者 ID |
| `_archivedBy_displayName` | 封存者.使用者名稱 | string | 封存者的顯示名稱 |

### 簽核欄位

僅在表格啟用簽核 (`enableApproval2: true`) 時有意義：

| 欄位名稱 | 顯示名稱 | 型別 | 說明 |
|---------|---------|------|------|
| `_approvalStatus` | 簽核狀態 | ApprovalStatus | APPROVED / DENIED / PENDING / ERROR |
| `_approvalName2` | 簽核單編號 | string | 簽核單的唯一編號 |
| `_approvalSequence2` | 簽核序數 | string | 同批新增的紀錄共用同一序數 |
| `_approvalRetry` | 簽核重試次數 | number | 簽核單產生失敗的重試次數 |
| `_approvalResult` | 簽核失敗原因 | string | 簽核單產生失敗的原因 |
| `_approvalApprovedBy2` | 簽核同意者 | string | 同意者的使用者 ID |
| `_approvalApprovedAt2` | 簽核同意時間 | Date | 簽核同意的時間 |
| `_approvalDeniedBy2` | 簽核拒絕者 | string | 拒絕者的使用者 ID |
| `_approvalDeniedAt2` | 簽核拒絕時間 | Date | 簽核拒絕的時間 |

## 表身系統欄位 (BUILTIN_LINE_FIELD)

| 欄位名稱 | 顯示名稱 | 型別 | 說明 |
|---------|---------|------|------|
| `_id` | 表身列編號 | SystemId | 表身列的系統主鍵 |
| `_createdAt` | 建立時間 | Date | 該列的建立時間 |
| `_createdBy` | 建立者 | string | 建立該列的使用者 ID |
| `_createdBy_displayName` | 建立者.使用者名稱 | string | 建立者的顯示名稱 |
| `_updatedAt` | 更新時間 | Date | 該列的最後更新時間 |
| `_updatedBy` | 更新者 | string | 最後更新該列的使用者 ID |
| `_updatedBy_displayName` | 更新者.使用者名稱 | string | 更新者的顯示名稱 |

## 欄位名稱保留字

以下名稱為系統保留字，開發者不可使用：

```
_id, _gId, _createdAt, _updateId, _updatedAt, _archivedAt,
_createdBy, _updatedBy, _archivedBy,
_approvalStage, _approvalStatus, _approvalRule, _approvalRole,
_approvalUser, _approvalAction, _approvalMessage, _approvalActedAt,
_approvalName
```

## 值型別約束

所有欄位值必須是純量（Scalar），不可使用複合型別：

允許的型別：
- `null`
- `boolean`
- `number`
- `Date`
- `string`
- `SystemId`（ObjectId）

不允許的型別：
- `object`
- `array`
- 巢狀結構
