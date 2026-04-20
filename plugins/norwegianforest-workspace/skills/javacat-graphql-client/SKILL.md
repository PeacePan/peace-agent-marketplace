---
name: javacat-graphql-client
description: 在 NorwegianForest / Ragdoll / WonderPet 專案中使用 javacat-graphql-client 時使用，涵蓋初始化、認證、查詢、變更、檔案上傳與 session cookie 管理。遭遇 isSignedIn、certificate、signinByToken、find、execute、call、insert、update 相關錯誤，或需要了解 client-side 與 server-side 差異時亦適用。
---

# javacat-graphql-client

## 概覽

`javacat-graphql-client` 是 WonderPet 內部封裝的 GraphQL 客戶端，基於 Apollo Client 建構，用於與 JavaCat GraphQL API 互動。支援 **client-side（瀏覽器）** 與 **server-side（Node.js / Electron main process）** 兩種環境，行為有顯著差異。

## GraphQL API 端點

| 環境 | URL |
|------|-----|
| `dev` | `https://data-api-development.wonderpet.asia/graphql` |
| `staging` | `https://data-api-staging.wonderpet.asia/graphql` |
| `production` | `https://data-api-production.wonderpet.asia/graphql` |

## 架構

```
JavaCatGraphQLClient
├── .auth        → JavaCatGraphQLClientAuthHandler
├── .query       → JavaCatGraphQLClientQueryHandler
├── .mutation    → JavaCatGraphQLClientMutationHandler
├── .isSignedIn  → boolean（JWT 有效且未過期）
└── .certificate → { jwt, cookie }（僅限 server-side）
```

## 章節索引

| 章節 | 檔案 | 說明 |
|------|------|------|
| 初始化與環境差異 | [01-setup.md](./chapters/01-setup.md) | 建構子選項、client vs server 差異 |
| 認證 | [02-auth.md](./chapters/02-auth.md) | signin、signinByToken、OTP、authenticate |
| 查詢 | [03-query.md](./chapters/03-query.md) | find、get、count、permissions |
| 變更 | [04-mutation.md](./chapters/04-mutation.md) | insert、update、patch、archive、execute、call、approve/deny |
| 憑證與 Cookie | [05-certificate.md](./chapters/05-certificate.md) | certificate 屬性、session cookie 格式與用途 |
| 檔案上傳 | [06-file-upload.md](./chapters/06-file-upload.md) | uploadFile 流程與限制 |
| 錯誤處理 | [07-error-handling.md](./chapters/07-error-handling.md) | Apollo 錯誤格式、常見錯誤訊息 |

## 快速參考

```typescript
import { JavaCatGraphQLClient } from 'javacat-graphql-client';

// 伺服器端（Electron main process / Node.js）
const client = new JavaCatGraphQLClient({
  env: 'production',
  authEnvPath: '/path/to/graphql-auth.json',
});

// 客戶端（瀏覽器）
const client = new JavaCatGraphQLClient({
  env: 'production',
  jwtStorageKey: 'my_jwt_key',
});
```

## 環境判斷規則

```typescript
// isClientSide(): typeof window !== 'undefined' && typeof localStorage !== 'undefined'
// isServerSide(): 相反
```

**Electron main process 屬於 server-side**，因為 `window` 與 `localStorage` 在 main process 中不存在。
