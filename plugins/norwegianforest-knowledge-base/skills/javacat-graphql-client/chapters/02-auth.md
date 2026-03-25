# 認證（Authentication）

所有認證方法均在 `client.auth` 命名空間下。

## 方法總覽

| 方法 | 說明 | 環境限制 |
|------|------|---------|
| `authenticate()` | 驗證 JWT 並取得使用者身份資訊 | 兩端皆可 |
| `otp()` | 發送一次性驗證碼至 email 或手機 | 兩端皆可 |
| `signin()` | 使用 OTP 登入，取得 JWT | 兩端皆可 |
| `signinByToken()` | 使用 accessKeyId + secretAccessKey 登入 | 兩端皆可 |
| `jwtRenew()` | 刷新 JWT | **DEV only** |
| `changeUser()` | 切換使用者 | **DEV only** |
| `tokenNewReq()` | 裝置登入：請求 OTP | 兩端皆可 |
| `tokenNew()` | 裝置登入：產生 token | 兩端皆可 |
| `tokenRenew()` | 裝置 token 刷新 | 兩端皆可 |

---

## `authenticate()`

驗證當前 JWT 有效性，並取得使用者完整身份資訊。

```typescript
const auth = await client.auth.authenticate();
// auth.user.name        → 使用者名稱
// auth.user.displayName → 顯示名稱
// auth.roles            → 角色列表
// auth.tables           → 可存取的表格
// auth.permissions2     → 新版權限設定
// auth.constraints2     → 新版約束條件
// auth.token            → API 存取令牌資訊 { name, accessKeyId, memo }
```

---

## `otp()` + `signin()`

標準的 OTP 登入流程（兩步驟）：

```typescript
// Step 1: 發送 OTP
const sent = await client.auth.otp({
  name: 'john_doe',
  email: 'john@example.com',
  // 或 mobile: '0912345678'（自動轉換為 +886 格式）
});

// Step 2: 使用 OTP 登入
const jwt = await client.auth.signin({
  name: 'john_doe',
  email: 'john@example.com',
  otp: '123456',
});
// jwt 已自動儲存到 localStorage（client）或 graphql-auth.json（server）
```

手機號碼格式：`09xxxxxxxx` 會自動轉換為 `+886xxxxxxxx`。

---

## `signinByToken()`

使用 accessKey 登入，適合 server-to-server 或機台自動登入：

```typescript
const jwt = await client.auth.signinByToken({
  accessKeyId: 'your_access_key_id',
  secretAccessKey: 'your_secret_access_key',
});
```

登入成功後 JWT 自動儲存，server-side 同時更新 `_cookie`。

---

## `isSignedIn` 屬性

`isSignedIn` 是同步屬性（非 async），內部透過 `jwtDecode` 驗證 JWT 到期時間：

```typescript
if (client.isSignedIn) {
  // JWT 存在且未到期（server-side 還需 _cookie 存在）
}
```

**注意**：server-side 必須 `_jwt` 與 `_cookie` 都存在才為 `true`。

---

## 裝置登入（tokenNewReq / tokenNew / tokenRenew）

```typescript
// Step 1: 請求 OTP
await client.auth.tokenNewReq({
  deviceName: 'POS-001',
  deviceId: 'device-uuid',
  userName: 'pos_user',
});

// Step 2: 產生 token（輸入 OTP）
const deviceToken = await client.auth.tokenNew({
  deviceName: 'POS-001',
  deviceId: 'device-uuid',
  userName: 'pos_user',
  otp: '123456',
});

// 之後可以刷新
const renewed = await client.auth.tokenRenew({
  deviceName: 'POS-001',
  deviceId: 'device-uuid',
});
```

---

## DEV only 方法

```typescript
// jwtRenew: 延長當前 JWT 有效期
const newJwt = await client.auth.jwtRenew(); // throws if env !== 'dev'

// changeUser: 切換使用者（需要 Administrator 身份）
const jwt = await client.auth.changeUser('target_user'); // throws if env !== 'dev'
```
