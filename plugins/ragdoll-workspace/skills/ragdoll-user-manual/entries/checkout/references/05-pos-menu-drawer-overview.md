# 功能選單（`PosMenuDrawer`）按鈕總覽

> 來源：原始碼（`next/app/sidemenu/pos-menu-drawer/index.tsx`、
> `next/app/checkout/components/checkout-header.tsx`）。

## 適用情境

驗收「POS 系統功能按鈕不可因業務狀態 disabled、一律改為可點擊 + toast 說明」
這類規範時（例如 RD-8153），本篇是功能選單所有按鈕的權威清單，含目前已落地
與尚未落地 toast 模式的按鈕。

## 操作步驟：開啟功能選單

1. 點擊頂欄「功能選單」按鈕（`data-testid="pos-menu-btn"`）。未登入銷售員時
   此按鈕 disabled（`disabled={!salerName}`，見 `checkout-header.tsx`）。
2. 右側滑出 Drawer，依「商品」（`data-testid="menu-tab-item"`）／「美容」
   （`data-testid="menu-tab-salon"`）分頁呈現。預設分頁對應目前的結帳模式，
   但可在 Drawer 內自由切換分頁瀏覽，不影響實際結帳模式。

## 商品分頁按鈕清單

| 按鈕 | data-testid | 點擊行為 |
|---|---|---|
| 開帳 / 修改開帳金額 | `menu-opening-btn` | 已開帳時顯示「已開帳」Badge；`reportStatus === 'REOPEN'` 時 disabled 且改導向清帳；否則開啟 `OpeningEntryDialog`（見 `02-open-register.md`） |
| 關帳 | （無） | `reportStatus === 'CLOSED'` 時 disabled；否則開啟 `ClosingEntryDialog`（超出本次範圍） |
| 銷售查詢(退換貨) | `menu-exchange-return-btn` | 已關帳或外送平台訂單鎖定時 disabled；否則呼叫 `onExchangeReturn` callback（開啟 `SalesQueryDialog`，超出本次範圍） |
| 價格查詢 | `menu-price-search-btn` | 呼叫 `onPriceSearch` callback（超出本次範圍） |
| 客訂 | `menu-customer-order-btn` | 呼叫 `handleCustomerOrder`：未登入銷售員時 toast「請先登入銷售員」且不開啟對話框；否則開啟 `CustomerOrderDialog`（超出本次範圍） |
| 截角（截角兌換） | `menu-voucher-redemption-btn` | 呼叫 `handleVoucherRedemption`：非正式 WonderPet 會員時 toast「截角兌換前，請先完成會員登入」；未開帳（`currentReport` 為 null）時 toast「請先開帳後再進行截角兌換」；兩關都過才開啟 `VoucherRedemptionDialog` |
| 分批取 | `menu-batch-pickup-query-btn` | 開啟 `BatchPickupQueryDialog`（超出本次範圍） |
| 專櫃管理 | （無） | 僅 `isSailorCounterClosed` 非 null/undefined（支援專櫃門市）時才渲染此按鈕 |

## 美容分頁按鈕清單

| 按鈕 | data-testid | 點擊行為 |
|---|---|---|
| 銷售查詢(退換貨) | `menu-salon-return-btn` | 呼叫 `onSalonReturn` callback，開啟 `SalonSalesQueryDialog`（超出本次範圍） |
| 活動列表 | （無） | **尚未實作**：呼叫 `handleMenuClick('活動列表')`（無 callback），觸發 `toast({ description: '活動列表 功能開發中', variant: 'info' })`，不開啟任何畫面 |
| 工單列表 | （無） | **尚未實作**：呼叫 `handleMenuClick('工單列表')`（無 callback），觸發 `toast({ description: '工單列表 功能開發中', variant: 'info' })`，不開啟任何畫面 |

## 「disabled 按鈕改 toast」規範的落地現況

`handleMenuClick(action, callback?)` 的邏輯是：有 callback 就執行，沒有 callback
就顯示 `${action} 功能開發中` 的 info 級 toast。「活動列表」「工單列表」這兩個
美容分頁按鈕**目前是可點擊的**（沒有被 HTML `disabled` 屬性擋住），點擊後會顯示
toast 說明尚未實作，而不是呈現灰階不可點擊狀態——這正是「功能按鈕不可因業務
狀態 disabled、一律改為可點擊 + toast 說明」規範已經落地的範例。

驗收此類規範時，操作方式是：

1. 開啟功能選單，切到對應分頁。
2. 觀察目標按鈕是否呈現可點擊樣式（非灰階、無 `disabled` 屬性）。
3. 點擊該按鈕，確認**沒有**因為按鈕本身 disabled 而完全無反應，而是出現
   toast 提示或正常開啟對應功能畫面。
4. 用 `read_electron_logs` 或畫面觀察確認 toast 文字內容是否合理說明「為何
   無法使用」或正確導向對應功能。

## 注意事項

- 商品分頁的多數按鈕（開帳除外）在對應前置條件不滿足時，目前仍是用 HTML
  `disabled` 屬性擋住（例如「關帳」在 `CLOSED` 狀態 disabled、「銷售查詢
  (退換貨)」在已關帳時 disabled），**不是**全部都已改為「可點擊 + toast」模式。
  驗收涉及商品分頁按鈕的條件時，需先確認該按鈕本次驗收範圍是否包含在
  「改為可點擊」的規範要求內，不可一概而論。
