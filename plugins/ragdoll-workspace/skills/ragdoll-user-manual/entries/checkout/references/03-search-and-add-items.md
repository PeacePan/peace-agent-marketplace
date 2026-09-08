# 搜尋與加入商品（商品模式）

> 來源：原始碼（`next/app/checkout/components/item-input.tsx`）+ E2E Page Object
> （`test/e2e/pages/checkout-page.ts` 的 `scanItem`）。

## 適用情境

已開帳、已登入銷售員後，於商品模式下掃描或輸入貨號將商品加入購物車。

## 操作步驟

1. 確認左上角模式下拉選單（`data-testid="mode-dropdown-trigger"`）目前顯示
   「商品」（Barcode 圖示）。若目前是「美容」模式，點擊下拉開啟選單，選擇
   `data-testid="mode-option-item"` 切換回商品模式（**切換模式會清空購物車與
   已綁定會員**，需在加入商品/會員之前先確認模式）。
2. 於條碼輸入框（`data-testid="item-barcode-input"`，placeholder「掃描或輸入
   貨號 / 國際條碼」）輸入貨號或以掃描器輸入條碼，按 Enter 或點擊「查詢」按鈕
   送出。
3. 送出後查詢圖示會變成 loading 動畫（`data-testid="item-scan-loading"`），
   查詢中「查詢」按鈕文字變為「查詢中...」且 disabled。

## 系統驗證行為

- 掃碼查詢是非同步 IPC，耗時不固定；正確的等待方式是等待
  `item-scan-loading` 從畫面消失（代表本次查詢與寫入購物車已確實完成），
  **不能**單純等待固定時間，也不能只看購物車小計是否變化——時價／異業合作
  商品掃入後不會立即反映到小計，而是先彈出定價 Dialog（超出本次手冊範圍）。
- 輸入框右側原本顯示的清除按鈕（`X` icon）會在有輸入值且非 loading 狀態時
  出現，點擊可清空輸入框。

## 外送匯入

商品模式下，條碼輸入框右側另有「外送」按鈕（`data-testid="import-delivery-trigger"`），
點擊會開啟外送訂單匯入對話框。此功能本次手冊列為待補，不深入涵蓋。

## 注意事項

- 美容模式下（超出本次範圍）此區域改顯示「帶入未付款銷售」
  （`open-unpaid-sales-btn`）與「新增/修改服務」（`open-edit-services-btn`）
  兩個按鈕，兩者皆需在線（`disabled={!online}`）。
- 美容模式選項本身（`mode-option-salon`）在離線時 disabled，無法切換。
