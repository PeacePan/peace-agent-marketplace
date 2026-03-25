# IPC 三層架構與資料流

## 三層對應關係

Ragdoll 的 IPC 通訊採用 Electron 推薦的 `contextBridge` + `ipcRenderer.invoke` 模式，分為三層：

```
Layer 1: Preload (ipc-renderer-preload.ts)
  ↕ contextBridge.exposeInMainWorld('ragdollAPI', ...)
Layer 2: IPC Channel (字串常數)
  ↕ ipcMain.handle('channel', handler)
Layer 3: Main Handler (ipc-main-setup.ts → 實際實作)
```

### Layer 1: Preload 腳本

**檔案**：`electron/main/settings/ipc-renderer-preload.ts`

- 定義 `ElectronAPI` class，實作 `ElectronAPIMethods` 介面
- 每個方法內部呼叫 `ipcRenderer.invoke('channel-name', ...args)` 傳送到主進程
- 最終透過 `contextBridge.exposeInMainWorld('ragdollAPI', new ElectronAPI())` 曝露

```typescript
// 範例：store 操作
store = {
  get: (key: string) => ipcRenderer.invoke('store-get', key),
  set: <T>(key: string, value: T) => ipcRenderer.invoke('store-set', key, value),
  delete: (key: string) => ipcRenderer.invoke('store-delete', key),
};
```

### Layer 2: IPC Channel

**Channel 命名規範**：
- 資料庫操作：`db-{operation}`（如 `db-list`、`db-findOne`、`db-insert`）
- 儲存操作：`store-{operation}`（如 `store-get`、`store-set`）
- GraphQL 操作：`gql-{category}-{method}`（如 `gql-auth-signin`、`gql-query-find`）
- 裝置操作：`devices:{device}:{method}`（如 `devices:invoice:open`、`devices:creditCard:sale`）
- 系統操作：`{action}`（如 `sync-data`、`restart-app`）

### Layer 3: Main Handler

**檔案**：`electron/main/settings/ipc-main-setup.ts`

- 使用 `ipcMain.handle('channel', handler)` 註冊處理函式
- Handler 接收 `(event, ...args)` 參數，回傳 Promise

```typescript
// 範例：store-get handler
ipcMain.handle('store-get', (_, key: keyof RagdollStore) => getStore().get(key));
```

---

## invoke vs send

| 方法 | 回傳值 | 用途 | 主進程對應 |
|------|--------|------|-----------|
| `ipcRenderer.invoke` | `Promise<T>` | 需要回傳結果的操作（查詢、寫入確認、裝置操作） | `ipcMain.handle` |
| `ipcRenderer.send` | `void` | 不需回傳結果的單向通知（觸發背景任務） | `ipcMain.on` |

**Ragdoll 中使用 `send` 的場景**：
- `triggerUploadOfflineSales()` — 觸發離線銷售單上傳（背景任務，不等結果）
- `renderer-error` — 渲染進程錯誤回報

其餘所有操作皆使用 `invoke`（包含 store、db、graphql、devices）。

---

## Sandbox 模式與 IPC_CHANNELS 雙重定義

Electron sandbox 模式下，preload 腳本**無法** `require` 或 `import` 外部模組（只有 `electron`、`node:` 內建模組可用）。因此：

- `IPC_CHANNELS` 常數在 `ipc-devices.ts` 定義一份（供 main handler 使用）
- `ipc-renderer-preload.ts` 內部**重新定義一份相同的常數**（供 preload 使用）

> **重要**：修改任何 IPC Channel 名稱時，**必須同步修改兩處**，否則通訊會斷開。

```
electron/main/types/ipc-devices.ts    → IPC_CHANNELS（主進程用）
electron/main/settings/ipc-renderer-preload.ts → IPC_CHANNELS（preload 用）
```

---

## 新增 IPC Channel 標準步驟

### Checklist

以下以「新增 `devices:foo:bar` Channel」為例：

- [ ] **Step 1 — 定義型別**
  - 在 `electron/main/types/ipc-devices.ts`（或適當的 types 檔案）新增 Request / Response 型別
  - 在 `IPC_CHANNELS` 常數中新增 channel 名稱

- [ ] **Step 2 — 更新 Preload**
  - 在 `electron/main/settings/ipc-renderer-preload.ts` 的 `IPC_CHANNELS` 新增**相同**的 channel 名稱
  - 在 `ElectronAPI` class 中新增對應方法，內部呼叫 `ipcRenderer.invoke`

- [ ] **Step 3 — 更新型別合約**
  - 在 `electron/main/types/api.ts` 的 `ElectronAPIMethods` 介面新增方法簽名
  - 確認 `next/types/global.d.ts` 不需修改（它直接引用 `ElectronAPIMethods`）

- [ ] **Step 4 — 註冊 Main Handler**
  - 在 `electron/main/settings/ipc-main-setup.ts` 的 `ipcMainSetup()` 中新增 `ipcMain.handle(...)`
  - 實作實際邏輯（或委派到 `devices/`、`lib/` 下的模組）

- [ ] **Step 5 — 渲染端使用**
  - 在 Next.js 元件中直接呼叫 `ragdollAPI.xxx.yyy()`
  - 所有 IPC 呼叫皆為 `async`，需 `await` 或處理 Promise

### 不需修改的檔案

- `next/types/global.d.ts`：自動繼承 `ElectronAPIMethods`，無需手動同步
- 任何 Next.js 的 store / hook：直接呼叫 `ragdollAPI` 即可，不需額外封裝
