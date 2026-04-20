---
name: ragdoll-checkout-flow
description: >
  Ragdoll POS 結帳流程完整知識庫。涵蓋從銷售員登入、商品掃描、加購/贈品/點加金選擇、
  10 個折扣計算器管道、付款到發票列印的每個步驟的詳細程式碼邏輯、Store 架構與資料結構定義。

  以下情況必須參考此文件再動手：
  - 撰寫結帳流程相關的 E2E 測試（Playwright）或整合測試
  - 新增或修改任何促銷計算器（discount calculator）邏輯
  - 處理 /checkout 或 /summary 頁面的功能開發或 bug 修復
  - 修改加購（addon）、贈品（freebie）、點加金（point promotion）相關邏輯
  - 處理發票開立、付款流程、錢櫃等硬體整合
  - 理解 OfflineSaleLocalRecord 的組裝過程
  - 修改折扣計算的執行順序或計算邏輯
---

# Ragdoll 結帳流程知識庫

結帳流程入口：`next/app/checkout/page.tsx`（左右分欄佈局）
付款頁面入口：`next/app/summary/page.tsx`

## 流程總覽（8 步驟）

```
[Step 1] 銷售員輸入員工編號登入
    ↓
[Step 2] 顧客電話號碼登入（會員登入，可選）
    ↓
[Step 3] 掃描/輸入商品條碼（可掃 100+ 件商品，支援累加）
    ↓
[Step 4] 點擊小計 → 開啟加購/贈品/點加金對話框
    ↓
[Step 5] 選擇加購/贈品/點加金 → 點擊「確認選擇」
         觸發 10 個折扣計算器管道
    ↓
[Step 6] 促銷結算對話框（優惠券、點數折抵、折扣碼）
         每次變更重新觸發計算器管道
    ↓
[Step 7] 確認後跳轉 /summary → 選擇付款方式（現金/信用卡）
    ↓
[Step 8] 點擊完成結帳
         建立 offline_sale → 開立發票 → 開錢櫃 → 清除購物車
```

---

## 各章節參考文件

### 登入流程
參見 [references/01-login.md](./references/01-login.md)（Step 1-2）：
- `saler-login.tsx` 員工驗證邏輯與 Store actions
- 會員三階段搜尋策略、Deferred Promise 模式、點數排序規則
- 登入後並行載入的 6 個非同步資源

### 商品掃描
參見 [references/02-scan-items.md](./references/02-scan-items.md)（Step 3）：
- `useBindFocus` 焦點鎖定機制（POS 連續掃碼核心）
- `scanItem` 完整流程、會員價即時同步機制
- 變價功能（`adjustItemPrice`）稽核規則、`normalItems` / `adjustPriceItems` 合併策略

### 加購/贈品/點加金
參見 [references/03-addon-gift-dialog.md](./references/03-addon-gift-dialog.md)（Step 4-5）：
- `handleSubtotalClick` 進入驗證條件
- 三個分頁（加購 / 贈品 / 點加金）各自的選擇邏輯與業務限制
- `handleAddonGiftConfirm` 完整執行序列（分組加入 Store → 重置 → 觸發計算 → 開啟對話框）

### 促銷結算
參見 [references/04-promotion-summary-dialog.md](./references/04-promotion-summary-dialog.md)（Step 6）：
- 左側商品群組展示邏輯
- 優惠券券號驗證流程
- 點數折抵三重上限校準邏輯
- 折扣碼套用流程

### 付款與完成結帳
參見 [references/05-payment-and-checkout.md](./references/05-payment-and-checkout.md)（Step 7-8）：
- `/summary` 頁面進入保護與佈局
- 現金/信用卡付款邏輯（含刷卡機 90 秒計時狀態機）
- `CheckoutButton.handleCheckout` 完整 7 步執行序列
- 發票取號原子性保障、列印模式判斷矩陣

### 折扣計算器
參見 [references/06-discount-calculators.md](./references/06-discount-calculators.md)：
- `CheckoutDiscountIterate` 迭代資料結構
- 10 個計算器的詳細輸入 / 邏輯步驟 / 輸出
- 金額計算彙總公式（`saleTotal` / `total` / `discount`）

### 資料結構
參見 [references/07-data-structures.md](./references/07-data-structures.md)：
- 所有核心 TypeScript 介面定義
- 商品名稱發票前綴規則（`[會]` / `[定]` / `[指]` / `[加]` / `[贈]`）
- 發票類型對應行為矩陣

### 硬體整合
參見 [references/08-hardware.md](./references/08-hardware.md)：
- 所有 `ragdollAPI` IPC 呼叫清單與說明
- 連線狀態監控邏輯與對結帳流程的影響
- 信用卡交易生命週期（`use-credit-card.ts`）

### Store 與檔案索引
參見 [references/09-stores-index.md](./references/09-stores-index.md)：
- 15 個 Checkout Store 的職責、State 欄位、Actions 清單
- 所有結帳元件、Hooks、共用工具的完整路徑索引
