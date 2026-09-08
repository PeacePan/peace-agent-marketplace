# 小計與結帳送出（商品模式）

> 來源：原始碼（`next/app/checkout/components/checkout-summary.tsx`）+ E2E Page
> Object（`test/e2e/pages/checkout-page.ts` 的 `clickSubtotal`）。

## 適用情境

購物車已加入商品、已開帳後，點擊「小計」送出結帳，進入後續加購/贈品/促銷結算
流程（此後續流程本次手冊列為待補）。

## 操作步驟

1. 確認右側「結帳摘要」卡顯示「銷售小計」、（有折扣時）「折扣金額」、
   「總金額」（`data-testid="cart-total-display"`）。
2. 若卡片顯示「檢查數量」欄位（`data-testid="qty-check-input"`，僅在
   `showQtyCheck` 為真且購物車有品項時出現，`itemCount === 0` 時 disabled），
   輸入與購物車實際商品總件數一致的數字（畫面文字刻意不顯示件數本身，防止
   人員照抄畫面件數規避人工點數核對）。在此欄位按 Enter 等同點擊小計。
3. 點擊「小計」按鈕（`data-testid="subtotal-btn"`）。商品模式下此按鈕的
   disabled 條件是：loading 中、外部 `disabled` prop、或被檢查數量守門鎖定
   （`isSubtotalLockedByQtyCheck`）；未開帳時的 disabled 邏輯屬於
   `guardCheckout` 範疇（見 `02-open-register.md`）。

## 系統驗證行為

- 送出中按鈕文字變為「資料處理中...」並顯示 loading 圖示。
- 外送通路小計後會先開揀貨數量檢查彈窗（超出本次手冊範圍），一般門市/美容
  情境則直接進入加購/贈品彈窗或促銷摘要彈窗（皆超出本次範圍）。

## 全部清除

「全部清除」按鈕（`data-testid="clear-all-btn"`，loading 中 disabled）點擊後
彈出二次確認對話框（標題「清除」，內文「請再次確認是否要清除所有資料」），
需點擊「確定」（`data-testid="clear-all-confirm"`）才會真正清空，點擊「關閉」
可取消。

## 交易暫結

「小計」列旁另有 `SuspendTransactionPanel`（交易暫結／取回功能），本次手冊
列為待補，不深入涵蓋其操作細節。

## 注意事項

- 美容模式（超出本次範圍）的小計按鈕邏輯不同：依 `useSalonOnlineGate` 離線時
  disabled，且點擊交由父層 `onSalonSubtotal` 處理。
- 促銷/折扣/加購/贈品的計算與畫面（小計之後的流程）本次手冊未涵蓋，涉及這些
  範圍的驗收條件應標記「⚠️ 無法驗證（手冊尚未涵蓋此範圍）」。
