# 憑證與 Session Cookie（Certificate）

## `certificate` 屬性

```typescript
// server-side only
const { jwt, cookie } = client.certificate;
```

**重要限制：**
- 只能在 **server-side**（Node.js / Electron main process）呼叫
- 在 client-side（瀏覽器）呼叫會直接 **throw**：
  ```
  Error: 因安全性問題，只能在伺服器端環境中存取此屬性=certificate
  ```

---

## Cookie 格式

`certificate.cookie` 的值由 `setCookieParser` 解析 GraphQL response 的 `set-cookie` header 後組成：

```
"connect.sid=s%3AxyzABC123; session_token=def456;"
```

格式規則：
- 每個 cookie 以 `name=value;` 表示
- 多個 cookie 以空格串接：`"a=1; b=2; c=3;"`
- **只包含 name 與 value**，不含 path / domain / expires 等屬性

---

## 何時 `cookie` 為 `null`

1. 尚未登入（從未呼叫過 `signin` / `signinByToken`）
2. `graphql-auth.json` 不存在或被刪除
3. 登入後尚未發出任何 GraphQL 請求（session 尚未被 server 設定）

---

## 在 Electron 中將 Cookie 注入給第三方網頁

場景：Electron main process 完成登入後，需要讓 iframe 或 BrowserWindow 開啟的頁面也被視為已登入。

```typescript
import { session } from 'electron';
import { cGQLClient, cPOSWebsiteURL } from '../consts';

async function syncAuthCookiesToLegacyPOS(): Promise<void> {
  const { cookie } = cGQLClient.certificate;
  if (!cookie) return;

  const targetUrl = cPOSWebsiteURL;
  const isSecure = targetUrl.startsWith('https://');
  const domain = new URL(targetUrl).hostname;

  // 解析 "name1=value1; name2=value2;" 格式
  const pairs = cookie.split(';').map((s) => s.trim()).filter(Boolean);
  for (const pair of pairs) {
    const eqIdx = pair.indexOf('=');
    if (eqIdx === -1) continue;
    const name = pair.substring(0, eqIdx).trim();
    const value = pair.substring(eqIdx + 1).trim();
    await session.defaultSession.cookies.set({
      url: targetUrl,
      name,
      value,
      domain,
      path: '/',
      secure: isSecure,
      httpOnly: false,
      sameSite: 'no_restriction', // 允許跨域帶上
    });
  }
  await session.defaultSession.cookies.flushStore();
}
```

**原理：** `session.defaultSession` 是 Electron process 層級共用的 cookie jar，寫入後所有 BrowserWindow 與 iframe 的 HTTP request 都會自動帶上對應 domain 的 cookie，不需要額外 IPC。

---

## Cookie 更新時機

`_cookie` 在每次成功的 GraphQL request 完成後，若 response header 有 `set-cookie`，會自動更新（由 `cookieSaverLink` Apollo Link 處理）。因此 `certificate.cookie` 反映的是**最後一次成功請求**時 server 設定的 cookie 值。

---

## `isSignedIn` 與 cookie 的關係

```typescript
// server-side 的 isSignedIn 實作：
get isSignedIn(): boolean {
  const hasCredentials = isClientSide() ? !!this._jwt : !!this._jwt && !!this._cookie;
  // 加上 JWT 到期時間檢查...
}
```

server-side 必須同時有 `_jwt` 與 `_cookie` 才為 `true`。若 `_cookie` 為 null，即使 JWT 有效也會回傳 `false`。
