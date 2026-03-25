# 所有 Store 與檔案索引

---

## 結帳相關 Store 完整清單

所有 Store 位於 `next/lib/stores/checkout/`，採用專案自定義的 `createStore` 架構（基於 Zustand）。

### 銷售員 Store

**路徑**：`next/lib/stores/checkout/saler/use-saler.ts`

| State | 型別 | 說明 |
|-------|------|------|
| `saler` | `Saler \| null` | 目前登入的銷售員 |

| Action | 說明 |
|--------|------|
| `login(employeeId)` | 員工認證登入 |
| `logout()` | 清除登入狀態 |

---

### 會員 Store

**路徑**：`next/lib/stores/checkout/member/use-checkout-member.ts`

| State | 型別 | 說明 |
|-------|------|------|
| `member` | `WonderPetMember \| null` | 登入會員資料 |
| `storeCoupons` | `Promise<PetParkCoupon[] \| null>` | 門市優惠券（非同步） |
| `salonCoupons` | `Promise<PetParkCoupon[] \| null>` | 美容優惠券（非同步） |
| `availablePoints` | `Promise<number \| null>` | 可用總點數（非同步） |
| `remainingPoints` | `Promise<number \| null>` | 扣除預計折抵後剩餘點數 |
| `historySales` | `Promise<MemberHistorySale[] \| null>` | 近 3 個月消費紀錄 |
| `pets` | `Promise<PosPet[] \| null>` | 名下寵物清單 |

| Action | 說明 |
|--------|------|
| `setMember(value)` | 三階段搜尋 + 並行非同步載入 |
| `redeemPoints(points)` | 預扣點數 |
| `recoverPoints(points)` | 退回點數 |
| `clear()` | 登出並清除所有資料 |

---

### 商品 Store

**路徑**：`next/lib/stores/checkout/items/use-items.ts`

| State | 型別 | 說明 |
|-------|------|------|
| `normalItems` | `CheckoutItem[]` | 一般商品列表 |
| `adjustPriceItems` | `CheckoutItem[]` | 變價商品列表 |

| Action | 說明 |
|--------|------|
| `scanItem(query)` | 掃碼主入口（優先累加，否則查 API） |
| `addItem(item)` | 直接新增商品 |
| `updateItemAmount(name, amount)` | 更新數量 |
| `adjustItemPrice(params)` | 變價並分拆至 `adjustPriceItems` |
| `clearAll()` | 清空購物車 |

---

### 加購 Store

**路徑**：`next/lib/stores/checkout/items/use-addons.ts`

| State | 型別 | 說明 |
|-------|------|------|
| `addonItems` | `FreebieCheckoutItem[]` | 已選加購商品 |
| `applyPosFreebies` | `PosFreebieLocalRecord[]` | 關聯活動原始記錄 |

| Action | 說明 |
|--------|------|
| `addAddonItems(items, posFreebie)` | 加入並合併同活動同料件 |
| `posAddonCalculator(iterate)` | 折扣計算器（計算器 1） |
| `clear()` | 清除選擇 |

---

### 贈品 Store

**路徑**：`next/lib/stores/checkout/items/use-freebies.ts`

| State | 型別 | 說明 |
|-------|------|------|
| `freebieItems` | `FreebieCheckoutItem[]` | 已選贈品 |
| `applyPosFreebies` | `PosFreebieLocalRecord[]` | 關聯活動原始記錄 |

| Action | 說明 |
|--------|------|
| `addFreebieItems(items, posFreebie)` | 加入贈品（price = 0） |
| `posFreebieCalculator(iterate)` | 折扣計算器（計算器 2） |
| `clear()` | 清除選擇 |

---

### 點加金 Store

**路徑**：`next/lib/stores/checkout/discount/point-promotion/use-point-promotion.ts`

| State | 型別 | 說明 |
|-------|------|------|
| `validPointPromotions` | `Promise<PointPromotionLocalRecord[] \| null>` | 有效活動清單 |
| `pointItems` | `PointPromotionStateItem[]` | 已兌換商品 |
| `totalPoints` | `number \| null` | 本次使用總點數 |

| Action | 說明 |
|--------|------|
| `updateValidPointPromotions()` | 載入有效活動 |
| `redeemPointItem(promotionName, item)` | 兌換（含驗證 + 扣點） |
| `redeemPointItemByBarcode(barcode)` | 條碼掃描兌換 |
| `removePointItem(promotionName, itemName)` | 移除並退點 |
| `pointPromotionCalculator(iterate)` | 折扣計算器（計算器 4） |
| `clear()` | 清除所有兌換 |

---

### 會員優惠券 Store

**路徑**：`next/lib/stores/checkout/discount/member-coupon/use-member-coupon.ts`

提供三個計算器：計算器 3（商品型）、計算器 5（商品折扣型）、計算器 7（整單折扣型）。

---

### POS 商品促銷 Store

**路徑**：`next/lib/stores/checkout/discount/pos-promotion/use-pos-promotion.ts`

提供計算器 6：`posPromotionCalculator`（核心商品促銷，呼叫 Electron 端最佳解演算法）。

---

### 整單折扣 Store

**路徑**：`next/lib/stores/checkout/discount/order-discount/use-order-discount.ts`

提供計算器 8：`orderDiscountCalculator`（滿額整單折扣）。

---

### 折扣碼 Store

**路徑**：`next/lib/stores/checkout/discount/pos-coupon/use-pos-coupon.ts`

提供計算器 9：`posCouponCalculator`（手動折扣碼）。

---

### 點數折抵 Store

**路徑**：`next/lib/stores/checkout/discount/member-points/use-member-points.ts`

提供計算器 10：`memberPointsCalculator`（點數折現）。

---

### 銷售 Store（計算器管道入口）

**路徑**：`next/lib/stores/checkout/sale/use-sale.ts`
**最複雜的 Store**，依賴所有其他結帳 Store。

| State | 型別 | 說明 |
|-------|------|------|
| `sale` | `SaleData` | 含 `currentSale`、`isSubmitting`、`submitError`、`invoicePrinted`、`cashDrawerOpened` |
| `iteratedDiscount` | `CheckoutDiscountInOut \| null` | 10 個計算器疊代後的最終結果 |

| Action | 說明 |
|--------|------|
| `calculateCheckoutDiscount()` | 依序執行 10 個折扣計算器的入口函數 |
| `createSale()` | 組裝 `OfflineSaleLocalRecord` 並寫入 SQLite |
| `printInvoiceForSale()` | 取號 → 原子性寫入 DB → 列印 |
| `openCashDrawerForSale()` | 呼叫硬體開錢櫃 |
| `reset()` | 重置所有銷售狀態 |

---

### 付款 Store

**路徑**：`next/lib/stores/checkout/payment/use-payment.ts`

| State | 型別 | 說明 |
|-------|------|------|
| `payment.selectedMethod` | `PaymentMethod \| null` | 選定的付款方式 |
| `payment.cashReceived` | `number` | 收取的現金金額 |
| `payment.creditCardResult` | `CreditCardResult \| null` | 信用卡授權結果 |

| Action | 說明 |
|--------|------|
| `selectMethod(method)` | 切換付款方式 |
| `setCashReceived(amount)` | 設定收款金額 |
| `processCreditCardPayment(amount)` | 啟動刷卡流程 |
| `canCheckout(total)` | 驗證是否可以結帳 |
| `reset()` | 重置付款狀態 |

---

### 發票設定 Store

**路徑**：`next/lib/stores/checkout/invoice/use-invoice.ts`

| State | 型別 | 說明 |
|-------|------|------|
| `invoice.type` | `InvoiceType` | 發票類型（print / carrier / taxId / donate） |
| `invoice.carrierNo` | `string` | 載具號碼 |
| `invoice.taxId` | `string` | 統一編號 |
| `invoice.donateCode` | `string` | 捐贈碼 |

| Action | 說明 |
|--------|------|
| `setType(type)` | 切換發票類型 |
| `setCarrierNo(value)` | 設定載具（含格式驗證） |
| `setTaxIdWithValidation(value)` | 設定統編（含 8 碼驗證） |
| `setDonateCode(value)` | 設定捐贈碼 |
| `reset()` | 重置為預設值 |

---

### 連線狀態 Store

**路徑**：`next/lib/stores/checkout/connection/use-connection.ts`

| State | 型別 | 說明 |
|-------|------|------|
| `connection.invoiceDevice` | `DeviceConnectionStatus` | 發票機連線狀態 |
| `connection.creditCardDevice` | `DeviceConnectionStatus` | 刷卡機連線狀態 |

| Action | 說明 |
|--------|------|
| `checkAllDevices()` | 偵測所有硬體連線 |
| `checkInvoiceDevice()` | 僅偵測發票機 |
| `checkCreditCardDevice()` | 僅偵測刷卡機 |

---

## 結帳元件完整路徑索引

### 結帳頁面（`/checkout`）

| 路徑 | 說明 |
|------|------|
| `next/app/checkout/page.tsx` | 主入口（流程協調中心） |
| `next/app/checkout/components/saler-login.tsx` | 銷售員登入 |
| `next/app/checkout/components/member-login/index.tsx` | 會員登入主元件 |
| `next/app/checkout/components/member-login/member-points-info.tsx` | 會員點數顯示 |
| `next/app/checkout/components/member-login/member-coupon-info.tsx` | 會員優惠券顯示 |
| `next/app/checkout/components/member-login/member-pet-info.tsx` | 會員寵物統計 |
| `next/app/checkout/components/item-input.tsx` | 商品條碼掃描輸入 |
| `next/app/checkout/components/cart-list.tsx` | 購物車列表 |
| `next/app/checkout/components/cart-item/index.tsx` | 購物車商品行（多態） |
| `next/app/checkout/components/checkout-header.tsx` | 頁面頂部（連線狀態、開錢櫃） |
| `next/app/checkout/components/checkout-info-bar.tsx` | 資訊列（銷售員、時鐘刷新） |
| `next/app/checkout/components/checkout-summary.tsx` | 金額彙總顯示 |
| `next/app/checkout/components/invoice-options.tsx` | 發票選項 |
| `next/app/checkout/components/price-change-dialog.tsx` | 商品變價對話框 |
| `next/app/checkout/components/number-keypad.tsx` | 數字鍵盤 Popover |
| `next/app/checkout/components/addon-gift-dialog/index.tsx` | 加購/贈品/點加金對話框 |
| `next/app/checkout/components/addon-gift-dialog/barcode-input.tsx` | 對話框內條碼掃描 |
| `next/app/checkout/components/promotion-summary-dialog/index.tsx` | 促銷結算確認對話框 |
| `next/app/checkout/components/promotion-summary-dialog/left-panel/promotion-item-list.tsx` | 左側商品群組展示 |
| `next/app/checkout/components/promotion-summary-dialog/right-panel/member-coupon-section.tsx` | 優惠券輸入 |
| `next/app/checkout/components/promotion-summary-dialog/right-panel/member-points-section.tsx` | 點數折抵調整 |
| `next/app/checkout/components/promotion-summary-dialog/right-panel/discount-code-section.tsx` | 折扣碼輸入 |

### 付款頁面（`/summary`）

| 路徑 | 說明 |
|------|------|
| `next/app/summary/page.tsx` | 付款結帳頁面 |
| `next/app/summary/components/checkout-button.tsx` | 完成結帳按鈕（7 步序列） |
| `next/app/summary/components/product-details-block/index.tsx` | 商品明細展示 |
| `next/app/summary/components/discounts-total-block/index.tsx` | 金額彙總展示 |
| `next/app/summary/components/payment-block/index.tsx` | 付款方式選擇 |
| `next/app/summary/components/credit-card-processing.tsx` | 刷卡處理遮罩 |

---

## Hooks 完整路徑索引

| 路徑 | 說明 |
|------|------|
| `next/lib/hooks/use-bind-focus.ts` | 全域掃描器焦點鎖定 |
| `next/lib/hooks/use-credit-card.ts` | 信用卡交易生命週期管理 |
| `next/lib/hooks/use-connection-monitor.ts` | 自動連線維護 |
| `next/lib/hooks/use-invoice-device.ts` | 發票機與錢櫃操作封裝 |
| `next/lib/hooks/use-sync-data.ts` | 資料同步進度監控 |
| `next/lib/hooks/use-upload-offline-sales.ts` | 離線銷售單上傳進度監控 |
| `next/lib/hooks/use-pos-config.ts` | POS 門市與機台設定讀取 |
| `next/lib/hooks/use-client-value.ts` | SSR/Client 差異處理（Hydration 防護） |
| `next/lib/hooks/use-cleanup-refs.ts` | 自動清理 Ref 機制 |

---

## 共用工具（`shared/`）完整路徑索引

| 路徑 | 說明 |
|------|------|
| `shared/utils/promotion.ts` | 促銷效果提取（`getBasePriceByDiscountBase`、`extractPromotionEffects`），跨主進程與渲染進程共用 |
| `shared/utils/sale-calculation.ts` | 金額計算工具函數 |
| `shared/utils/invoice.ts` | 發票號碼格式化與驗證工具 |
| `shared/utils/general.ts` | 通用工具函數 |
| `shared/utils/algorithm.ts` | 通用演算法（排序、搜尋等） |
| `shared/consts.ts` | 全域常數定義（通路代碼、付款方式常數等） |
