# 檔案上傳（File Upload）

## `uploadFile()`

```typescript
const fileRecord = await client.uploadFile(file, {
  category: 'product_image',   // 必填：檔案分類名稱（對應 FileCategory 表）
  contentType: 'image/jpeg',   // 必填：MIME type
  fileName: 'photo.jpg',       // 可選：指定檔名（省略則自動產生）
  memo: '商品主圖',             // 可選：備註
});
// fileRecord?.body.url → 公開 URL（僅當 FileCategory.public = true 時才有值）
```

---

## 上傳流程（五步驟）

```
1. 查詢 FileCategory 取得限制規則（大小、MIME、尺寸）
2. 驗證檔案符合規則
3. 呼叫 GraphQL mutation 新增 File2 record，取得 S3 presigned POST URL
4. 直接以 FormData POST 至 S3（不經過 JavaCat server）
5. 更新 File2 record 的 fileSize 欄位，標記上傳完成
```

步驟 3-4-5 有**自動重試機制**（最多 3 次）。

---

## 驗證規則（由 FileCategory 定義）

| 欄位 | 說明 |
|------|------|
| `limitedContentType` | 允許的 MIME type 列表（逗號分隔） |
| `limitedFileSize` | 最大檔案 bytes 數 |
| `limitedWidthMin/Max` | 圖片寬度限制（僅圖片類型） |
| `limitedHeightMin/Max` | 圖片高度限制（僅圖片類型） |
| `disableReupload` | 是否禁止重複上傳同名檔案 |

---

## 公開 URL 格式

當 `FileCategory.public = true` 時，`fileRecord.body.url` 會被自動填入：

```
https://data-api-{env}.wonderpet.asia/file/{category}/{fileName}
```

---

## 注意事項

- **重複上傳**：若同名檔案已存在且 `disableReupload = true`，會 throw
- **圖片尺寸驗證**：client-side 用 `Image` DOM API，server-side 用 `sharp` 套件
- **S3 上傳**：直接以 `fetch` POST 至 S3，`credentials: 'omit'`（不帶 JavaCat cookie）
