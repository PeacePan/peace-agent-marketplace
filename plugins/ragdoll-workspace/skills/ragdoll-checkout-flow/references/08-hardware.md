# 硬體整合與連線監控

---

## IPC 呼叫清單

所有硬體操作透過 `ragdollAPI`（Electron `contextBridge` 暴露的 preload API）從渲染進程呼叫主進程。

| `ragdollAPI` 方法 | 呼叫位置 | 說明 |
|-------------------|----------|------|
| `salerLogin(employeeId)` | `use-saler.ts` | 銷售員員工認證 |
| `fetchItem(query)` | `use-items.ts` | 查詢商品資料（條碼/貨號） |
| `calcBestPosPromotion(params)` | `use-pos-promotion.ts` | 在主進程執行最佳促銷演算法 |
| `processCreditCardSale(amount)` | `use-credit-card.ts` | 驅動刷卡機執行交易 |
| `checkCreditCardDevice()` | `use-connection.ts` | 檢查刷卡機連線狀態 |
| `checkInvoiceDevice()` | `use-connection.ts` | 檢查發票機連線狀態 |
| `commitInvoice(params)` | `use-sale.ts` | 原子性寫入發票號碼（DB Transaction） |
| `printInvoice(params)` | `use-sale.ts` | 驅動發票機列印發票聯或明細聯 |
| `openCashDrawer()` | `use-sale.ts` | 透過發票機信號開啟錢櫃 |
| `syncInvoiceOffset()` | `use-sale.ts` | 將發票號碼使用進度同步至雲端 |
| `triggerUploadOfflineSales()` | `checkout-button.tsx` | 啟動背景同步任務 |
| `on(event, handler)` | 多個 hooks | 訂閱主進程事件（進度、完成等） |

---

## 連線狀態監控

**Store**：`next/lib/stores/checkout/connection/use-connection.ts`
**Hook**：`next/lib/hooks/use-connection-monitor.ts`

### 連線狀態值

```typescript
type DeviceConnectionStatus = 'CONNECTED' | 'DISCONNECTED' | 'CHECKING'

interface ConnectionState {
  invoiceDevice: DeviceConnectionStatus  // 發票機
  creditCardDevice: DeviceConnectionStatus  // 刷卡機
}
```

### `use-connection-monitor.ts` 監控邏輯

```
在 CheckoutHeader、SummaryPage 等頁面掛載時啟動：

1. 監聽瀏覽器 window 'online' 事件
   → 網路恢復時：呼叫 checkAllDevices()（重新偵測所有硬體）

2. 監聽瀏覽器 window 'offline' 事件
   → 網路斷開時：立即將所有設備標記為 DISCONNECTED

3. 頁面初次載入：呼叫 checkAllDevices()
```

### 連線狀態對結帳流程的影響

| 設備 | 狀態 | 在流程中的影響 |
|------|------|--------------|
| 發票機 | `DISCONNECTED` | `handlePromotionSummaryConfirm` 中阻擋跳轉至 `/summary`，顯示警告 |
| 刷卡機 | `DISCONNECTED` | 信用卡付款按鈕顯示警告，`checkCreditCardDevice()` 失敗阻擋刷卡 |

---

## 信用卡交易生命週期

**Hook**：`next/lib/hooks/use-credit-card.ts`

這個 Hook 封裝了刷卡機通訊的完整狀態機，避免主進程的硬體代碼直接暴露給 UI 層。

### 狀態機定義

```typescript
type CreditCardState =
  | 'IDLE'        // 待機，等待用戶觸發
  | 'CHECKING'    // 正在確認設備連線
  | 'PROCESSING'  // 正在與刷卡機通訊（等待刷卡）
  | 'SUCCESS'     // 授權成功
  | 'ERROR'       // 授權失敗或刷卡機回傳錯誤
  | 'TIMEOUT'     // 超時（90 秒無回應）
```

### 狀態轉移圖

```
IDLE
  ↓ 用戶點擊信用卡付款
CHECKING（前置檢查：連線 + 忙碌）
  ↓ 檢查通過
PROCESSING（90 秒倒數開始）
  ├─ 刷卡成功    → SUCCESS（記錄卡號末四碼、授權碼、終端機 ID）
  ├─ 刷卡失敗    → ERROR（顯示中文錯誤訊息）
  └─ 90 秒超時   → TIMEOUT（顯示超時提示）

SUCCESS / ERROR / TIMEOUT
  ↓ 用戶確認或重試
IDLE（重置為待機狀態）
```

### 支援的交易類型

| 方法 | 說明 |
|------|------|
| `processSale(amount)` | 一般刷卡消費 |
| `processVoid(params)` | 刷卡消費撤銷 |
| `processRefund(params)` | 刷卡退款 |

### 錯誤代碼轉譯

刷卡機回傳的硬體代碼（如 `ERR_051`、`ERR_116` 等）由 Hook 內建的映射表自動轉換為中文訊息（如「卡片無效」、「餘額不足」），避免銷售員看到技術性錯誤代碼。

---

## 發票機操作

**Hook**：`next/lib/hooks/use-invoice-device.ts`

封裝了發票機的所有操作，包含：
- 發票列印（含完整格式化的發票資料組裝）
- 明細列印（`onlyDetail: true`）
- 錢櫃開啟信號

### 列印失敗處理策略

發票號碼通過 `commitInvoice` 原子性寫入後，即使後續列印失敗：
- 發票號碼已記錄於 `issue_invoice` 資料表
- 銷售單（`offline_sale`）中的 `issueInvoiceName` 已更新
- 不影響雲端同步（發票序號仍會上傳）
- 需人工追蹤補印（透過後台查詢 `issue_invoice` 紀錄）

---

## 背景同步任務監控

**Hook**：`next/lib/hooks/use-upload-offline-sales.ts`

```typescript
// 透過 IPC 事件監聽上傳進度
ragdollAPI.on('UPLOAD_PROGRESS', (progress) => {
  // progress: { current: number, total: number, percentage: number }
})

ragdollAPI.on('UPLOAD_COMPLETE', () => {
  // 全部上傳完成
})

ragdollAPI.on('UPLOAD_ERROR', (error) => {
  // 某筆上傳失敗（會重試）
})
```

**Hook**：`next/lib/hooks/use-sync-data.ts`

監控商品資料同步（促銷活動、商品資料、點數活動等）的進度，透過相同的 IPC 事件機制顯示即時百分比。
