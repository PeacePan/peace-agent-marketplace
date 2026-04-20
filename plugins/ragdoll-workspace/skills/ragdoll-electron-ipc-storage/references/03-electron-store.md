# Electron Store 本地儲存

## 概述

Ragdoll 使用 `electron-store`（npm 套件）進行 key-value 持久化儲存，實際檔案為 `ragdoll-store.json`，存放於 `data/{env}/` 目錄下。

**主進程實作**：`electron/main/lib/storage.ts`

```typescript
import ElectronStore from 'electron-store';

let _store: Conf<RagdollStore> | null = null;

export function initStore(): Conf<RagdollStore> {
  if (_store) return _store;
  ElectronStore.initRenderer();
  _store = new ElectronStore<RagdollStore>({
    name: 'ragdoll-store',
    cwd: cOfflineDataPath,
  }) as unknown as Conf<RagdollStore>;
  return _store;
}

export function getStore(): Conf<RagdollStore> {
  if (!_store) throw new Error('Store has not been initialized.');
  return _store;
}
```

---

## RagdollStore 型別定義

**檔案**：`electron/main/types/storage.ts`

```typescript
export type RagdollStore = Partial<{
  POS_STORE_NAME: string;              // POS 門市編號
  POS_CONFIG_NAME: string;             // POS 機台配置編號
  POS_THERMAL_PRINTER: string;         // POS 熱感印表機名稱
  LAST_DATA_CHECK_AT: number;          // 最後資料檢查時間 (Unix timestamp)
  LAST_PROMOTION_CALC_AT: number;      // 最後促銷價計算時間 (Unix timestamp)
  LAST_OFFLINE_ITEM_SYNC_AT: number;   // 最後離線料件同步時間 (Unix timestamp)
  CREDIT_CARD_READER_TYPE: CreditCardReaderType;  // 刷卡機類型
  INIT_READONLY_DATABASE_VERSION: number;          // 初始化唯讀資料庫版本
}>;
```

> **注意**：`RagdollStore` 使用 `Partial<{...}>`，所有欄位皆為 optional，`get()` 回傳值可能是 `undefined`。

---

## 渲染端使用方式

所有操作透過 `ragdollAPI.store` 進行，皆為**非同步**（回傳 Promise）。

```typescript
// 讀取（注意回傳可能是 undefined）
const storeName: string | undefined = await ragdollAPI.store.get('POS_STORE_NAME');

// 寫入（型別安全：value 必須符合 RagdollStore[K]）
await ragdollAPI.store.set('LAST_DATA_CHECK_AT', Date.now());

// 刪除
await ragdollAPI.store.delete('POS_THERMAL_PRINTER');
```

### IPC 流程

```
渲染端                        主進程
ragdollAPI.store.get('KEY')
  → ipcRenderer.invoke('store-get', 'KEY')
                              → ipcMain.handle('store-get')
                              → getStore().get('KEY')
                              ← 回傳 value
  ← Promise<value>
```

---

## 擴充 RagdollStore 標準步驟

### Checklist

以新增 `MY_NEW_FIELD: MyType` 為例：

- [ ] **Step 1 — 修改型別**
  - 在 `electron/main/types/storage.ts` 的 `RagdollStore` 新增欄位與 JSDoc 註解
  ```typescript
  export type RagdollStore = Partial<{
    // ... 既有欄位
    /** 我的新欄位說明 */
    MY_NEW_FIELD: MyType;
  }>;
  ```

- [ ] **Step 2 — 確認無需修改 IPC**
  - `store-get/set/delete` 的 IPC handler 是泛用的，**不需修改** `ipc-main-setup.ts` 或 `ipc-renderer-preload.ts`
  - 型別約束由 TypeScript 的 `keyof RagdollStore` 自動生效

- [ ] **Step 3 — 渲染端直接使用**
  - `await ragdollAPI.store.get('MY_NEW_FIELD')` 即可讀取
  - TypeScript 會自動推導回傳型別為 `MyType | undefined`

### 不需修改的檔案

| 檔案 | 原因 |
|------|------|
| `ipc-renderer-preload.ts` | store 操作是泛用的，key 為 string 參數 |
| `ipc-main-setup.ts` | handler 使用 `keyof RagdollStore` 泛型，自動涵蓋新欄位 |
| `next/types/global.d.ts` | 自動繼承 `ElectronAPIMethods` |

> **這是 electron-store 擴充最省力的地方**：只需改一個型別檔案，整條 IPC 鏈路自動生效。

---

## 與 Maltese localStorage 的差異

| 特性 | Maltese (localStorage) | Ragdoll (electron-store) |
|------|----------------------|------------------------|
| 操作模式 | 同步 | **非同步**（IPC 跨進程） |
| 儲存位置 | 瀏覽器 localStorage | 檔案系統 `ragdoll-store.json` |
| 型別安全 | 無（全部 `string`，需手動 parse） | 有（`RagdollStore` 泛型約束） |
| 持久性 | 依賴瀏覽器，可能被清除 | 獨立檔案，應用重裝仍保留 |
| 資料格式 | `JSON.stringify` 手動管理 | electron-store 自動序列化 |
| 過期機制 | Maltese `stashArrayFactory` 手動過濾 24h | 需自行在讀取時實作過濾邏輯 |

### 遷移 Maltese localStorage 到 Ragdoll electron-store 的要點

1. **所有操作加 `await`**：localStorage 是同步的，electron-store 透過 IPC 是非同步的
2. **不需 JSON 手動序列化**：electron-store 自動處理 JSON 讀寫
3. **型別定義集中管理**：在 `RagdollStore` 中定義欄位型別，而非散落在各檔案
4. **過期過濾邏輯獨立實作**：electron-store 不內建過期機制，需在工具函式中手動過濾

```typescript
// Maltese 風格（同步、手動 JSON）
const data = JSON.parse(localStorage.getItem('key') ?? '[]');
localStorage.setItem('key', JSON.stringify(newData));

// Ragdoll 風格（非同步、自動序列化）
const data = (await ragdollAPI.store.get('KEY')) ?? [];
await ragdollAPI.store.set('KEY', newData);
```
