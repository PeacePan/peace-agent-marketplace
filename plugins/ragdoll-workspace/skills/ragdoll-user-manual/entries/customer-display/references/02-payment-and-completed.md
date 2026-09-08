# 付款中與完成畫面（二顯）

> 來源：原始碼（`next/app/customer-display/page.tsx`、`components/payment-screen.tsx`、
> `components/completed-screen.tsx`、`components/member-info-card.tsx`、
> `components/invoice-section.tsx`、`lib/customer-display/build-snapshot.ts`、
> `lib/customer-display/use-customer-display-sync.ts`）+ E2E Page Object
> （`test/e2e/pages/customer-display-screen-page.ts`）。
> ⚠️ 尚未經 runtime 畫面驗證（撰寫當下 Ragdoll dev 環境未啟動，
> `list_electron_windows` 回報找不到任何視窗；即使 dev 環境啟動，完整驗證
> 「已收合計」「結帳完成」等欄位仍需實際刷卡機/現金設備配合送出付款，故本文件
> 全篇皆僅依原始碼撰寫）。

## 適用情境

購物車已加入商品，主視窗進入促銷結算對話框（仍在 `/checkout`）或已進入
`/summary` 付款頁後，二顯切換為 `PaymentScreen`；完成付款後短暫（8 秒）切換
為 `CompletedScreen` 展示本次交易結果，之後自動回到 `IdleScreen`。

## 觸發條件（本頁無操作步驟，改記錄主視窗做了什麼操作會讓二顯畫面切換）

1. **Payment**：購物車非空或已識別會員成立，且（主視窗 `pathname === '/summary'`
   或促銷結算對話框開啟中）任一成立時觸發。對應主視窗操作為
   `entries/checkout/references/04-checkout-and-payment.md`「小計與結帳送出」
   步驟中點擊「小計」按鈕之後的流程；促銷結算對話框透過「確認結帳」關閉並
   `router.push('/summary')` 後，兩個觸發條件交棒，不會出現真空瞬間掉回
   `ShoppingScreen`。
2. **Completed**：購物車與會員皆已清空（結帳完成後系統清空）、結帳完成展示
   旗標為真時觸發，8 秒後由主視窗計時器自動重置，二顯隨之切回 `IdleScreen`；
   此後的實際刷卡機/現金收款畫面本次手冊未涵蓋，超出
   `04-checkout-and-payment.md` 範圍。

## 系統驗證行為（⚠️ 尚未實機驗證，依原始碼描述）

### PaymentScreen（`data-testid="customer-display-payment-screen"`）

- 已識別會員時，頂部同樣顯示 `MemberInfoCard`（同購物中畫面）。
- 左側「結帳明細」單一卡片：逐項商品名稱 × 數量、小計；下方「商品小計」
  合計；若有折扣（折扣列表非空）顯示折扣扣除區塊
  （`data-testid="customer-display-discounts-section"`），逐行
  （`data-testid="customer-display-discount-row"`）顯示折扣標籤與扣除金額
  （語意化紅字負數），折扣類型涵蓋商品促銷／會員優惠券／折扣碼／整單折扣／
  點數折抵五種。
- 右側依序：「發票方式」（`InvoiceSection`，同購物中畫面）→「已收合計」
  （`data-testid="payment-received-amount"`）→「應付金額」
  （`data-testid="payment-payable-amount"`，強調卡片，放最下方）。應付金額
  = 商品小計 − 折扣總額（不小於 0）。
- 已知限制：本畫面目前未顯示換購交易的「原訂單抵扣」「換購找零/差額」兩行
  資訊（主視窗 `/summary` 頁本身已有），純屬顯示完整度落差；應付金額數值
  本身與主視窗同源，不受此限制影響。

### CompletedScreen（`data-testid="customer-display-completed-screen"`）

- 圓形品牌色勾勾圖示進場動畫 + 「結帳完成」標題 + 副標「感謝您的惠顧，期待
  您再次光臨」。
- 消費總金額（`data-testid="completed-total-amount"`）。
- 「本次獲得點數」目前固定不顯示：POC 階段此欄位固定傳 `null`（原始碼註解
  「earnedPoints 維持傳 null，另外處理」），元件僅在非 null 時才渲染該欄位。
- 點數餘額（`data-testid="completed-point-balance"`）一律顯示欄位，非會員或
  查詢失敗（null）時以「－」佔位。
- 發票號碼（`data-testid="completed-invoice-no"`）：僅在有值時才顯示該欄位。
- 底部固定品牌 Slogan「♥ Thank You · 寵物公園 Pet Park ♥」。

## 注意事項

- 二顯視窗開啟前提、與主視窗解耦特性同 `01-idle-and-shopping.md`「注意事項」，
  不重複列出。
- `CompletedScreen` 顯示的消費總金額／點數餘額／發票號碼皆來自主視窗結帳
  階段 store 的完成快照，該快照必須在購物車被清空「之前」完成，避免讀到
  清空後的狀態；此為主視窗端的實作細節，本文件僅記錄其對客顯畫面資料正確性
  的影響。
- 付款中／結帳完成兩個畫面因需要實際刷卡機/現金設備配合送出付款才能觸發，
  本文件所有畫面內容描述皆為僅依原始碼撰寫、尚未經 runtime 驗證，需在下次
  有 Ragdoll dev 環境啟動且能操作實機設備的 session 補做。
