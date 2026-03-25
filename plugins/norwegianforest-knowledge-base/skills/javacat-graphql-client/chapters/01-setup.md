# 初始化與環境差異

## 建構子選項

```typescript
type JavaCatGraphQLClientBaseOptions = {
  env: 'production' | 'staging' | 'dev';
  jwtStorageKey?: string;  // client-side 必填
  authEnvPath?: string;    // server-side 必填
};
```

## Client-side（瀏覽器）

- `jwtStorageKey` **必填**，`authEnvPath` 不需要
- JWT 儲存於 `localStorage`
- Cookie 由瀏覽器自動管理，不需手動處理
- `isSignedIn` 只檢查 `_jwt` 是否有效（不檢查 cookie）
- `certificate` 屬性呼叫會直接 **throw**（安全設計）

```typescript
const client = new JavaCatGraphQLClient({
  env: 'production',
  jwtStorageKey: 'javacat_jwt',
});
```

## Server-side（Node.js / Electron main process）

- `authEnvPath` **必填**，指向 `graphql-auth.json` 檔案路徑
- JWT 與 cookie 均儲存於 `graphql-auth.json`
- `isSignedIn` 同時檢查 `_jwt` 與 `_cookie` 兩者皆有效
- `certificate` 屬性可正常存取

```typescript
const client = new JavaCatGraphQLClient({
  env: 'production',
  authEnvPath: '/path/to/data/graphql-auth.json',
});
```

## `graphql-auth.json` 結構

server-side 的憑證由 `_saveCredential` 寫入，key 為 GraphQL domain：

```json
{
  "data-api-production.wonderpet.asia": {
    "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
    "cookies": "connect.sid=s%3Axyz; session_token=abc;"
  }
}
```

## 啟動時自動載入憑證

建構子會在 server-side 環境自動讀取 `authEnvPath` 的 JSON 並設定 `_jwt` 與 `_cookie`，因此下次啟動時 `isSignedIn` 可能已為 `true`（前提：JWT 未過期）。

## 環境對照表

| 行為 | Client-side | Server-side |
|------|-------------|-------------|
| JWT 儲存位置 | `localStorage` | `graphql-auth.json` |
| Cookie 管理 | 瀏覽器自動處理 | 手動從 response header 解析 |
| `isSignedIn` 條件 | JWT 有效 | JWT + cookie 皆有效 |
| `certificate` 屬性 | throw Error | `{ jwt, cookie }` |
| 啟動時自動載入 | 從 localStorage | 從 JSON 檔案 |
