# 從首頁進入結帳或訂單查詢

> 來源：原始碼（`next/app/page.tsx`、`next/app/summary/page.tsx:121,143-148`）。
> 尚未經 runtime 畫面驗證（撰寫當下 Ragdoll dev 環境未啟動，`list_electron_windows`
> 回報找不到任何視窗）。

## 適用情境

應用程式啟動後的第一個畫面，無需登入即可看到。使用者由此選擇進入「結帳」或
「訂單查詢」兩條路徑之一。

## 操作步驟

1. 應用程式啟動後直接顯示 `/` 首頁：標題「萬達寵物 POS 桌面版」+ 兩個並排
   按鈕。
2. 點擊「開始結帳」按鈕會導向 `/checkout`（見 `entries/checkout/AGENT.md`）。
3. 點擊「訂單查詢」按鈕會導向 `/summary`（`/summary` 頁面本身尚未撰寫手冊，
   見下方「系統驗證行為」的已知限制）。

## 系統驗證行為

- 兩個按鈕都是 Next.js `<Link>` 純前端路由跳轉，原始碼未見任何 disabled
  條件、loading 狀態或前置 API 呼叫，理論上點擊後會立即成功導航。
- `/summary` 頁面本身有一段守門邏輯（`next/app/summary/page.tsx:121,143-148`）：
  進入頁面時若購物車品項數（`itemCount`，由 `iteratedDiscount.items` 加總）
  為 0，且非結帳流程中（`isCheckoutInProgress === false`），會呼叫
  `router.replace('/checkout')` 立即導回 `/checkout`。由首頁直接點擊
  「訂單查詢」時購物車必為空，因此實際會先短暫掠過 `/summary` 再被導回
  `/checkout`，而非停留在 `/summary`。

## 注意事項

- 「訂單查詢」這個按鈕文字所暗示的用途（查詢歷史訂單）與 `/summary` 實際
  頁面內容（結帳流程中的付款/摘要頁）之間的落差，本文件不評論其合理性，
  僅如實記錄原始碼行為。
- ⚠️ 待確認：上述導回 `/checkout` 瞬間的實際畫面表現（是否有可見閃爍、
  `/checkout` 落地時呈現什麼狀態）尚未經 runtime 驗證，需在 Ragdoll dev
  環境啟動時補做。
