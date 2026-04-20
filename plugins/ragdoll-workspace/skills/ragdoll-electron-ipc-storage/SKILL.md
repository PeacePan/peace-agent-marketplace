---
name: ragdoll-electron-ipc-storage
description: >
  Ragdoll Electron IPC 與 Local Storage 整合指南。涵蓋 Electron 主進程與 Next.js 渲染進程之間的
  IPC 通訊架構、ragdollAPI 完整 API 清單、electron-store 本地儲存機制、硬體裝置 IPC 介面，
  以及新增 IPC Channel 或擴充 Local Storage 的標準步驟。

  以下情況必須參考此文件再動手：
  - 新增或修改 Electron IPC 通訊介面
  - 擴充 electron-store 本地儲存欄位（RagdollStore 型別異動）
  - 使用 ragdollAPI 呼叫硬體裝置（發票機、刷卡機、台新 ONE 碼、宜睿禮券）
  - 使用 ragdollAPI.store / ragdollAPI.db / ragdollAPI.graphql 操作資料
  - 從渲染端呼叫主進程的任何功能
  - 理解 Preload → IPC Channel → Main Handler 三層架構
---

# Ragdoll Electron IPC & Local Storage 整合指南

Ragdoll 採用 Electron 的 `contextBridge` + `ipcRenderer.invoke` 模式，所有渲染進程對主進程的呼叫都透過 `window.ragdollAPI`（全域常數 `ragdollAPI`）進行。

## 架構總覽

```
┌──────────────────────────────────────────────────────────────┐
│  Next.js 渲染進程 (Renderer)                                  │
│                                                              │
│  ragdollAPI.store.get('KEY')                                 │
│  ragdollAPI.devices.invoice.open()                           │
│  ragdollAPI.db.list('tableName')                             │
│       │                                                      │
│       ▼                                                      │
│  ipc-renderer-preload.ts                                     │
│  (contextBridge.exposeInMainWorld)                            │
│  ipcRenderer.invoke('channel', ...args)                      │
└────────────────────────┬─────────────────────────────────────┘
                         │ IPC Channel
┌────────────────────────▼─────────────────────────────────────┐
│  Electron 主進程 (Main)                                       │
│                                                              │
│  ipc-main-setup.ts                                           │
│  ipcMain.handle('channel', handler)                          │
│       │                                                      │
│       ▼                                                      │
│  實際實作：storage.ts / database/ / devices/ / jobs/           │
└──────────────────────────────────────────────────────────────┘
```

## 關鍵檔案索引

| 檔案 | 職責 |
|------|------|
| `electron/main/settings/ipc-renderer-preload.ts` | Preload 腳本，定義 `ElectronAPI` class 並透過 `contextBridge` 曝露為 `ragdollAPI` |
| `electron/main/settings/ipc-main-setup.ts` | 主進程 IPC handler 註冊中心 |
| `electron/main/types/api.ts` | `ElectronAPIMethods` 介面（ragdollAPI 的完整型別合約） |
| `electron/main/types/ipc-devices.ts` | 所有硬體裝置 IPC 介面、Channel 常數 |
| `electron/main/types/storage.ts` | `RagdollStore` 型別（electron-store 可用 key） |
| `electron/main/lib/storage.ts` | electron-store 實例初始化與存取 |
| `next/types/global.d.ts` | 渲染端 `ragdollAPI` 全域型別宣告 |

---

## 各章節參考文件

### IPC 三層架構與資料流
參見 [references/01-ipc-architecture.md](./references/01-ipc-architecture.md)：
- Preload → Channel → Main Handler 三層對應關係
- `ipcRenderer.invoke` vs `ipcRenderer.send` 的使用時機
- Sandbox 模式限制與 IPC_CHANNELS 雙重定義原因
- 新增 IPC Channel 的標準步驟（含 checklist）

### ragdollAPI 完整 API 清單
參見 [references/02-ragdoll-api-reference.md](./references/02-ragdoll-api-reference.md)：
- `ragdollAPI.store` — 本地儲存 CRUD
- `ragdollAPI.db` — SQLite 資料庫操作
- `ragdollAPI.graphql` — GraphQL 遠端操作
- `ragdollAPI.devices` — 硬體裝置操作
- 其他工具方法（`syncData`、`commitInvoice`、`calcBestPosPromotion` 等）

### Electron Store 本地儲存
參見 [references/03-electron-store.md](./references/03-electron-store.md)：
- `RagdollStore` 型別定義與現有欄位
- `ragdollAPI.store.get/set/delete` 使用方式
- 擴充 RagdollStore 的標準步驟（含 checklist）
- 與 Maltese localStorage 的差異比較

### 硬體裝置 IPC 介面
參見 [references/04-device-ipc.md](./references/04-device-ipc.md)：
- 發票機（InvoiceDeviceIPC）：ping / print / open
- 刷卡機（CreditCardDeviceIPC）：ping / sale / void / refund / isBusy / cancel
- 台新 ONE 碼（TaishinPayDeviceIPC）：payment / refund / query
- 宜睿禮券（EdenredDeviceIPC）：getVoucher / authorization
- IPC_CHANNELS 常數對照表
