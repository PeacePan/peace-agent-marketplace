# ragdollAPI 完整 API 清單

型別合約定義：`electron/main/types/api.ts` → `ElectronAPIMethods`
渲染端全域宣告：`next/types/global.d.ts` → `const ragdollAPI: ElectronAPIMethods`

---

## ragdollAPI.store — 本地儲存

透過 electron-store（`ragdoll-store.json`）進行 key-value 持久化儲存。

| 方法 | 簽名 | IPC Channel | 說明 |
|------|------|-------------|------|
| `get` | `<K extends keyof RagdollStore>(key: K) => Promise<RagdollStore[K] \| undefined>` | `store-get` | 讀取指定 key 的值 |
| `set` | `<K extends keyof RagdollStore>(key: K, value: RagdollStore[K]) => Promise<void>` | `store-set` | 寫入指定 key 的值 |
| `delete` | `(key: keyof RagdollStore) => Promise<void>` | `store-delete` | 刪除指定 key |

> **型別安全**：key 受 `RagdollStore` 型別約束，新增欄位需修改 `electron/main/types/storage.ts`。

### 使用範例

```typescript
// 讀取
const storeName: string | undefined = await ragdollAPI.store.get('POS_STORE_NAME');

// 寫入
await ragdollAPI.store.set('POS_STORE_NAME', 'STORE_001');

// 刪除
await ragdollAPI.store.delete('POS_STORE_NAME');
```

---

## ragdollAPI.db — SQLite 資料庫操作

操作本地 SQLite 資料庫，支援 CRUD 與條件查詢。

| 方法 | 說明 | IPC Channel |
|------|------|-------------|
| `list(tableName, options?)` | 查詢多筆記錄（支援 filters、排序、分頁） | `db-list` |
| `findOne(tableName, filters?)` | 查詢單筆記錄 | `db-findOne` |
| `count(tableName, filters)` | 計算符合條件的記錄數 | `db-count` |
| `insert(tableName, inserts)` | 批量新增記錄 | `db-insert` |
| `update(tableName, updates)` | 批量更新記錄 | `db-update` |
| `remove(tableName, removes)` | 批量刪除記錄 | `db-remove` |

### 查詢範例

```typescript
// 查詢所有商品
const items = await ragdollAPI.db.list('item', {
  filters: [{ body: { status: { eq: 'active' } } }],
  limit: 100,
});

// 查詢單筆
const item = await ragdollAPI.db.findOne('item', [
  { body: { name: { eq: 'ITEM001' } } },
]);
```

---

## ragdollAPI.graphql — GraphQL 遠端操作

透過 `javacat-graphql-client` 與後端 GraphQL API 通訊。

| 方法 | 說明 | IPC Channel |
|------|------|-------------|
| `isSignedIn()` | 檢查登入狀態 | `gql-isSignedIn` |
| `otp(query)` | 發送 OTP | `gql-auth-otp` |
| `signIn(query)` | OTP 登入 | `gql-auth-signin` |
| `signInByToken(query)` | Token 登入 | `gql-auth-signinByToken` |
| `find(query, options)` | 查詢資料 | `gql-query-find` |
| `insert(query)` | 新增資料 | `gql-mutation-insert` |
| `update(query)` | 更新資料 | `gql-mutation-update` |
| `execute(args)` | 執行自訂函式 | `gql-mutation-execute` |

---

## ragdollAPI.devices — 硬體裝置

詳見 [04-device-ipc.md](./04-device-ipc.md)。

| 子物件 | 裝置 | 主要方法 |
|--------|------|---------|
| `devices.invoice` | 發票機 | `ping`, `print`, `open`（開錢櫃） |
| `devices.creditCard` | 刷卡機 | `ping`, `sale`, `void`, `refund`, `isBusy`, `cancel` |
| `devices.taishinPay` | 台新 ONE 碼 | `payment`, `refund`, `query` |
| `devices.edenred` | 宜睿禮券 | `getVoucher`, `authorization` |

---

## 其他工具方法

| 方法 | 說明 | IPC Channel | 通訊模式 |
|------|------|-------------|---------|
| `getTargetEnv()` | 取得運行環境（dev/staging/prod）與 isLocalDev 標記 | `get-target-env` | invoke |
| `openExternal(url)` | 開啟外部瀏覽器連結 | `open-external` | invoke |
| `restartApp()` | 重新啟動應用程式 | `restart-app` | invoke |
| `isOnline()` | 檢查網路連線狀態 | `net-isOnline` | invoke |
| `syncData()` | 觸發完整資料同步（回傳 `SyncResult`） | `sync-data` | invoke |
| `syncInvoiceOffset()` | 同步發票偏移量到遠端 | `sync-invoice-offset` | invoke |
| `commitInvoice(params)` | 原子性發票記錄（更新 offset + 寫入 issue_invoice） | `commit-invoice` | invoke |
| `triggerUploadOfflineSales()` | 觸發離線銷售單上傳（背景、不等回傳） | `trigger-upload-offline-sales` | **send** |
| `calcBestPosPromotion(data)` | 計算最佳促銷組合（Worker 執行緒） | `calc-best-pos-promotion` | invoke |

---

## 事件監聽 (on / off / send)

除了 `invoke` 模式外，`ragdollAPI` 也提供底層事件通訊：

```typescript
// 監聽主進程推送的事件
ragdollAPI.on('channel', (event, ...args) => { ... });

// 取消監聽
ragdollAPI.off('channel', callback);

// 向主進程發送單向訊息（不等回傳）
ragdollAPI.send('channel', ...args);
```

**目前使用場景**：
- `renderer-error`：渲染端發生錯誤時回報主進程（layout.tsx 中的全域 error handler）
- `trigger-upload-offline-sales`：觸發背景上傳
