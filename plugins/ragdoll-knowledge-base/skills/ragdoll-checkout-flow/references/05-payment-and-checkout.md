# Step 7-8：付款頁面與完成結帳

---

## Step 7：付款頁面（`/summary`）

**頁面**：`next/app/summary/page.tsx`

### 進入保護

頁面載入時（`useEffect`）檢查 `itemCount`：若購物車無商品且非結帳進行中 → 自動重新導向回 `/checkout`，防止使用者直接開啟 URL。

### 頁面佈局

**左側區塊**：

| 元件 | 說明 |
|------|------|
| `ProductDetailsBlock` | 商品明細（一般品 / 加購 / 贈品 / 點加金 / 促銷折扣負項） |
| `DiscountsTotalBlock` | 金額彙總（商品小計 / 各折扣明細 / 應付總額） |
| `PaymentBlock` | 付款方式選擇區（現金 / 信用卡） |

**右側區塊**：

| 元件 | 說明 |
|------|------|
| 發票設定顯示 | 唯讀展示（此頁不允許修改） |
| 連線指示燈 | 顯示發票機 / 刷卡機連線狀態 |
| `CheckoutButton` | 完成結帳按鈕 |

---

### 現金付款（CASH）

**Store**：`next/lib/stores/checkout/payment/use-payment.ts`

**UI 互動**：

| 操作 | 函數 | 說明 |
|------|------|------|
| 快捷金額按鈕 | `handleSelectCashOption(amount)` | 一鍵輸入固定金額（$500, $1,000 等） |
| `NumberKeypad` 輸入 | `handleCashAmountChange(amount)` | 手動輸入任意金額 |

**驗證**：`cashReceived >= total`
- 不足時顯示 toast 警告，`CheckoutButton` 維持禁用

**找零計算**：

```
change = cashReceived - total
change > 0 → 顯示找零金額（橘色）
change < 0 → 顯示「不足」提示（紅色）
change = 0 → 顯示「剛好」
```

---

### 信用卡付款（CREDIT_CARD）

**Hook**：`next/lib/hooks/use-credit-card.ts`

**前置檢查**（任一失敗則顯示錯誤，阻擋刷卡流程）：
1. `checkCreditCardDevice()` — 確認刷卡機已連線
2. `checkIsBusy()` — 確認刷卡機目前不在忙碌中

**刷卡機通訊生命週期**：

```
用戶點擊信用卡付款按鈕
    ↓
顯示 CreditCardProcessing 遮罩（佔滿畫面，防止操作）
    ↓
PROCESSING 狀態：
  - 90 秒倒數計時器啟動
  - 呼叫 ragdollAPI.processCreditCardSale(amount)
  - 等待刷卡機硬體回應
    ↓
    ├─ 授權成功 → SUCCESS 狀態
    │   - 記錄：卡號末四碼、授權碼（approvalCode）、終端機 ID
    │   - 遮罩消失，CheckoutButton 解除禁用
    │
    ├─ 授權失敗 → ERROR 狀態
    │   - 硬體錯誤代碼自動轉譯為中文訊息
    │   - 顯示錯誤原因，可重試
    │
    └─ 超時（90秒）→ TIMEOUT 狀態
        - 顯示超時提示，可重試
```

---

## Step 8：完成結帳

**元件**：`next/app/summary/components/checkout-button.tsx`

### `canCheckout()` 最終驗證

**信用卡**：`creditCardResult !== null`（已授權成功才允許結帳）
**現金**：`cashReceived >= total`（收款足夠才允許結帳）

---

### `handleCheckout` 完整 7 步執行序列

#### Step 1：建立銷售單

```typescript
await saleActions.createSale()
```

組裝並寫入 SQLite `offline_sale` 資料表，初始 `uploadStatus` 為 `PENDING`：

```
offline_sale {
  body: {
    saleNo: string,          // 銷售單號（門市代碼 + 流水號）
    total: number,           // 應付總額（折扣後）
    discount: number,        // 折扣總額
    saleTotal: number,       // 商品小計（商品促銷折扣後，整單折扣前）
    storeName: string,       // 門市名稱
    posConfigName: string,   // POS 機台名稱
    salerName: string,       // 銷售員姓名
    memberName: string|null, // 會員姓名（無會員為 null）
    issueInvoiceName: null,  // 發票號碼（此時尚未取號）
    uploadStatus: 'PENDING'  // 等待上傳至雲端
  },
  lines: {
    items: SaleLineItem[],   // 商品明細含名稱前綴、促銷標籤、變價資訊
    payments: PaymentLine[]  // 付款明細含方式、金額、找零、信用卡資訊
  }
}
```

---

#### Step 2：開立發票

```typescript
await saleActions.printInvoiceForSale()
```

**2a. 取號**（`total > 0` 時執行）：

```
pickEGUINo(posStoreName, posConfigName)
→ 從 pos_egui_no 資料表中取得當前可用的下一個發票號碼
```

**2b. 原子性 DB Transaction（`commitInvoice`）**：

三個操作在同一個 SQLite Transaction 中完成，確保一致性：

```
Transaction {
  Action A: pos_egui_no.offset += 1
  Action B: 建立 issue_invoice 記錄 {
              eguiNo,      // 發票號碼（如 AA12345678）
              randomCode,  // 4 位隨機碼
              carrierNo,   // 載具號碼（如適用）
              taxId,       // 統一編號（如適用）
              donateCode,  // 捐贈碼（如適用）
              issuedAt     // 開立時間
            }
  Action C: offline_sale.issueInvoiceName = eguiNo
}
若任一 Action 失敗 → 整個 Transaction 回滾，不執行列印
```

**2c. 列印模式判斷矩陣**：

| 條件 | 列印行為 |
|------|---------|
| `total > 0` + `invoiceType = print` | 發票聯 + 明細聯 |
| `total > 0` + `invoiceType = taxId` | 發票聯 + 明細聯 |
| `total > 0` + `invoiceType = carrier` | 僅明細聯（`onlyDetail: true`） |
| `total > 0` + `invoiceType = donate` | 僅明細聯（`onlyDetail: true`） |
| `total = 0` （任何發票類型） | 僅明細聯，**不取號、不建立** `issue_invoice` |

**2d. 靜默號碼同步**：

```typescript
ragdollAPI.syncInvoiceOffset()  // 失敗不阻斷結帳
```

將號碼使用進度同步回雲端，失敗時不顯示錯誤，由背景排程（Jobs）在下次機會補傳。

---

#### Step 3：開錢櫃（現金交易限定）

```typescript
if (paymentMethod === 'CASH') {
  await saleActions.openCashDrawerForSale()
}
```

透過 IPC 呼叫 Electron 主進程，驅動發票機發出開錢櫃電子信號。

---

#### Step 4：清除所有相關 Store

```typescript
itemsActions.clearAll()           // 清空購物車
memberActions.clear()             // 登出會員
addonActions.clear()              // 清除加購選擇
freebieActions.clear()            // 清除贈品選擇
pointPromotionActions.clear()     // 清除點加金選擇
saleActions.reset()               // 重置銷售狀態
paymentActions.reset()            // 重置付款狀態
invoiceActions.reset()            // 重置發票設定（保留預設值）
```

---

#### Step 5：顯示完成畫面

```typescript
setIsCompleted(true)  // 顯示結帳成功的完成畫面
```

---

#### Step 6：觸發背景上傳

```typescript
ragdollAPI.triggerUploadOfflineSales()
```

啟動背景同步任務，將 `offline_sale`（`uploadStatus = PENDING`）上傳至雲端 GraphQL API。上傳進度可透過 `use-upload-offline-sales.ts` hook 監聽。

---

### 結帳失敗處理

| 失敗點 | 行為 |
|--------|------|
| `createSale` 失敗 | 顯示錯誤，購物車資料保留，可重試 |
| `commitInvoice` Transaction 失敗 | 不執行列印，顯示錯誤，號碼未占用 |
| 列印失敗 | 發票號碼已記錄於 DB，需人工追蹤補印 |
| 錢櫃開啟失敗 | 銷售單已建立，不影響流程，僅顯示警告 |
