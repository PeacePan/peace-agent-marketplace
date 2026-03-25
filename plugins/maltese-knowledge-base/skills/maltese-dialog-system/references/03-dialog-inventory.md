# 各元件 Dialog 清單與 childProps 分析

本文件列出 SaleConsole 四個子元件中所有 `openDialog` 呼叫，並標記是否需要 `childProps`。

**判讀方式**：
- 無標記 = 可直接 `openDialog(name)` 開啟，不需要任何額外參數
- `[dialogProps]` = 需要 `dialogProps`（如標題），但不需要 `childProps`
- `[childProps]` = 需要 `childProps`，不可無參數開啟

---

## item/Checkout（`src/components/layouts/saleConsole/item/Checkout.tsx`）

### 可無參數開啟的 Dialog

| Dialog 名稱 | 說明 |
|-------------|------|
| `priceSearch` | 價格搜尋 |
| `itemSaleSearch` | 一般銷售查詢 |
| `exchangeSale` | 換貨 |
| `fullReturn` | 全退 |
| `orderDiscount` | 整單折扣 |
| `coupon` | 優惠券 |
| `pocketPromotion` | 口袋促銷 |
| `voucherExchange` | 禮券兌換 |
| `addon` | 加購 |
| `freebie` | 贈品 |
| `stashSaleBoard` | 暫存銷售看板 |
| `pointPromotion` | 點加金促銷 |
| `importDeliveryOrder` | 匯入調撥單 |
| `partialSearchOrExchange` | 部分查詢或換貨 |
| `customerOrder` | 客訂單 |
| `depositWithdraw` | 存提款 |
| `addItemsWithAmount` | 批次加入商品 |
| `importInvoiceInfo` | 匯入發票資訊 |
| `clearAll` | 全部清除 |

### 需要 childProps 的 Dialog

| Dialog 名稱 | childProps 內容 | 說明 |
|-------------|----------------|------|
| `afterClickSummary` | `AfterClickSummaryProps` | 點擊小計後的結算摘要 |
| `memberPointUsage` | `{ saleConsoleType: 'item' }` | 會員點數使用 |
| `petParkCouponUsage` | `{ saleConsoleType: 'item' }` | 寵物公園優惠券使用 |
| `itemDepositPoint` | `{ items, channel: PointApplyChannel.STORE, ... }` | 商品點數存入 |
| `petparkCouponUsageChosen` | `dialogProps: { disableBackdropClose: true }` | 寵物公園優惠券選擇確認 |

### 動態開啟的 Dialog

| 觸發條件 | Dialog 名稱 | 說明 |
|----------|-------------|------|
| 開帳/關帳狀態判斷 | `closingEntry` 或 `openingEntry` | 依 `entryMsg` 變數決定 |

---

## item/Management（`src/components/layouts/saleConsole/item/Management.tsx`）

### 可無參數開啟的 Dialog

| Dialog 名稱 | dialogProps | 說明 |
|-------------|-------------|------|
| `closingEntry` | — | 關帳 |
| `openingEntry` | — | 開帳 |
| `editOpeningEntryLog` | — | 編輯開帳紀錄 |
| `expenditureList` | — | 支出列表 |
| `sumReport` | — | 彙總報表 |
| `dailyReport` | — | 日報表 |
| `expenditureApplication` | — | 支出申請 |
| `batchPrint` | — | 批次列印 |
| `itemPriceChange` | `{ title: '一般貨價卡異動資訊' }` | 一般貨價卡異動 |
| `corporatePrintPriceCard` | — | 企業貨價卡列印 |
| `promotionItemBatchPrintV2` | `{ title: '' }` | 促銷品批次列印 |
| `promotionItemPriceChange` | `{ title: '促銷貨價卡異動資訊' }` | 促銷貨價卡異動 |
| `itemPromotionPriceChange` | — | 商品促銷價格異動 |
| `storeCounterSumReport` | `{ title: '速報-店內專櫃' }` | 店內專櫃速報 |
| `storeCounterDailyReport` | `{ title: '店內專櫃日報表' }` | 店內專櫃日報表 |
| `printItemReceipt` | `{ title: '驗收單列表' }` | 驗收單列表 |

### 需要 childProps 的 Dialog

| Dialog 名稱 | childProps 內容 | 說明 |
|-------------|----------------|------|
| `salesTarget` | `{ isClosed: reportStatus === PosReportStatus.CLOSED }` | 日業績目標 |
| `newStorePrintPriceCard` | `{ sheetRows }` + `dialogProps` | 新門市貨價卡列印 |

---

## salon/Checkout（`src/components/layouts/saleConsole/salon/Checkout.tsx`）

### 可無參數開啟的 Dialog

| Dialog 名稱 | 說明 |
|-------------|------|
| `serviceSaleSearch` | 美容銷售查詢 |
| `workSheetList` | 工作單列表 |
| `unpaidSaleSearch` | 未付款銷售查詢 |
| `salonCoupon` | 美容優惠券 |
| `importInvoiceInfo` | 匯入發票資訊 |
| `salonPromotionList` | 美容促銷列表 |
| `salonFullReturn` | 美容全退 |
| `packageServiceItemReturn` | 套裝服務商品退貨 |
| `cancelSale` | 取消銷售 |
| `salonClearAll` | 美容全部清除 |
| `addOrEditServiceItem` | 新增或編輯美容服務項目 |

### 需要 childProps 的 Dialog

| Dialog 名稱 | childProps 內容 | 說明 |
|-------------|----------------|------|
| `memberPointUsage` | `{ saleConsoleType: 'salon' }` | 會員點數使用 |
| `petParkCouponUsage` | `{ saleConsoleType: 'salon' }` | 寵物公園優惠券使用 |
| `salonDepositPoint` | `{ channel: PointApplyChannel.SALON, ... }` | 美容點數存入 |

### 動態開啟的 Dialog

| 觸發條件 | Dialog 名稱 | 說明 |
|----------|-------------|------|
| 開帳/關帳狀態判斷 | `closingEntry` 或 `openingEntry` | 依 `entryMsg` 變數決定 |

---

## salon/Management（`src/components/layouts/saleConsole/salon/Management.tsx`）

### 所有 Dialog 皆可無參數開啟

| Dialog 名稱 | 說明 |
|-------------|------|
| `closingEntry` | 關帳 |
| `openingEntry` | 開帳 |
| `editOpeningEntryLog` | 編輯開帳紀錄 |
| `expenditureList` | 支出列表 |
| `salonSumReport` | 美容彙總報表 |
| `dailyReport` | 日報表 |
| `salonSalesTarget` | 美容日業績目標 |
| `expenditureApplication` | 支出申請 |

---

## 跨元件共用的 Dialog

以下 Dialog 在多個元件中都有觸發按鈕：

| Dialog 名稱 | 出現於 |
|-------------|--------|
| `closingEntry` | item/Checkout（動態）、item/Management、salon/Checkout（動態）、salon/Management |
| `openingEntry` | item/Checkout（動態）、item/Management、salon/Checkout（動態）、salon/Management |
| `editOpeningEntryLog` | item/Management、salon/Management |
| `expenditureList` | item/Management、salon/Management |
| `dailyReport` | item/Management、salon/Management |
| `expenditureApplication` | item/Management、salon/Management |
| `importInvoiceInfo` | item/Checkout、salon/Checkout |
