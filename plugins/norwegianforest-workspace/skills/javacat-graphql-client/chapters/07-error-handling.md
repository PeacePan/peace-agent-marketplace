# 錯誤處理（Error Handling）

## 錯誤格式

所有 Query / Mutation 的錯誤都被 `extractMessageFromServerError` 統一格式化，最終 throw 出的 `Error.message` 是**換行符號串接的多行字串**：

```
http status: 403\n登入時效權限過期，請重新登入
```

可用 `.split('\n')` 取得各別錯誤訊息。

---

## 常見錯誤與原因

| 錯誤訊息 | 原因 | 解法 |
|---------|------|------|
| `登入時效權限過期，請重新登入` | JWT 過期或 HTTP 403 | 重新呼叫 `signin` / `signinByToken` |
| `當前使用者無權限` | 欄位或表格無存取權 | 確認角色與 permissions2 設定 |
| `jwtRenew 只能在 DEV 環境下使用` | 在非 dev 環境呼叫 `jwtRenew` | 改用 `signinByToken` 刷新 |
| `因安全性問題，只能在伺服器端環境中存取此屬性=certificate` | 在 client-side 呼叫 `certificate` | 只在 server-side / main process 呼叫 |
| `JavaCatGraphQLClient: authFilePath is required in server side` | server-side 未提供 `authEnvPath` | 建構子補上 `authEnvPath` |
| `JavaCatGraphQLClient: jwtStorageKey is required in client side` | client-side 未提供 `jwtStorageKey` | 建構子補上 `jwtStorageKey` |
| `上傳檔案發生錯誤: ...` | uploadFile 任何步驟失敗 | 查看錯誤子訊息 |

---

## Apollo 錯誤類型

`extractMessageFromServerError` 處理三種錯誤類型：

| 類型 | 識別方式 | 說明 |
|------|---------|------|
| `ServerParseError` | `'bodyText' in networkError` | Server 回傳純文字（非 JSON） |
| `ServerError` | `'response' in networkError` | Server 回傳 GraphQL error 結構 |
| `GraphQLError` | `instanceof GraphQLError` | Client-side GQL 錯誤 |

---

## 錯誤處理範例

```typescript
try {
  const records = await client.query.find({ table: 'member' });
} catch (error) {
  const messages = (error as Error).message.split('\n');

  // 偵測 JWT 過期
  if (messages.some(m => m.includes('登入時效權限過期'))) {
    // 重新登入
    await client.auth.signinByToken({ accessKeyId, secretAccessKey });
  }

  // 偵測 HTTP 狀態碼
  const httpLine = messages.find(m => m.startsWith('http status:'));
  const statusCode = httpLine ? parseInt(httpLine.split(': ')[1]) : null;
}
```

---

## `###N###` 錯誤格式

當 server 回傳多筆 mutation 錯誤時，`extractMessageFromServerError` 會將 `###1###` 格式的標記轉換為「第 1 筆」的可讀形式：

```
原始：第 ###2### 筆資料驗證失敗
轉換：第 2 筆資料驗證失敗
```
