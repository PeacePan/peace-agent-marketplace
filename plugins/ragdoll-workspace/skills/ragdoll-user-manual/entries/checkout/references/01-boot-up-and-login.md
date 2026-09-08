# 開機與銷售員登入

> 來源：原始碼（`next/app/checkout/page.tsx`、`components/saler-login.tsx`）+
> E2E Page Object（`test/e2e/pages/checkout-page.ts`）+ 2026-09-08 對真實啟動的
> Ragdoll dev 環境（`http://localhost:3100/checkout`）截圖驗證。

## 適用情境

機台開機後，需先登入銷售員才能進行任何結帳相關操作（掃描、開帳、小計等）；
`PosMenuDrawer`（功能選單）在未登入銷售員時整個 disabled。

## 操作步驟

1. 應用程式啟動後先看到根路由 `/`（極簡導航頁，見 `entries/home/AGENT.md`），
   點擊「開始結帳」按鈕才會進入 `/checkout`。
2. 未登入時，頂欄 `SalerLogin` 顯示唯讀輸入框（`data-testid="saler-input"`，
   placeholder「輸入員編」）。點擊輸入框會開啟數字鍵盤 Popover
   （`data-testid="saler-keypad-popover"`）。
3. 於鍵盤輸入員工工號（數字字串），按 Enter 確認（或點擊「登入」按鈕，
   `data-testid="saler-login-btn"`，輸入為空時此按鈕 disabled）。
4. 登入成功後，畫面顯示「銷售員: {顯示名稱}」（`data-testid="saler-name-display"`）
   與「登出」按鈕（`data-testid="saler-logout-btn"`）。登入成功**不會**額外跳出
   toast 提示（RD-7567 已移除，只會清掉先前殘留的 toast）。

## 系統驗證行為

- 登入失敗時依錯誤碼顯示對應 toast：`USER_NOT_FOUND`→「找不到此銷售員」、
  `USER_DISABLED`→「此帳號已停用」、`API_ERROR`→「登入失敗，請稍後再試」。
- 登入中鍵盤輸入框與登入按鈕會顯示 loading 狀態（按鈕文字變為「驗證中...」）。

## 登出

點擊「登出」按鈕（`saler-logout-btn`）立即登出，並強制重新彈出鍵盤要求重新
登入（未登入狀態下鍵盤無法被外部關閉）。

## 注意事項

- 已登入時點擊姓名文字（`saler-name-display`）可重新開啟鍵盤切換銷售員。
- ⚠️ 待確認：「切換銷售員」對進行中購物車/會員狀態的影響，原始碼未在
  `saler-login.tsx` 內直接處理購物車清空邏輯，需人工在實機環境確認實際行為。
