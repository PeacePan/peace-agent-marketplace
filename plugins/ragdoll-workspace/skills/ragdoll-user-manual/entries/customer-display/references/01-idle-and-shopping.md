# 閒置與購物中畫面（二顯）

> 來源：原始碼（`next/app/customer-display/page.tsx`、`components/idle-screen.tsx`、
> `components/shopping-screen.tsx`、`components/member-info-card.tsx`、
> `components/invoice-section.tsx`、`hooks/use-customer-display-snapshot.ts`、
> `lib/customer-display/build-snapshot.ts`、`lib/customer-display/idle-banners.ts`）
> + E2E Page Object（`test/e2e/pages/customer-display-screen-page.ts`）。
> ⚠️ 尚未經 runtime 畫面驗證（撰寫當下 Ragdoll dev 環境未啟動，
> `list_electron_windows` 回報找不到任何視窗）。

## 適用情境

二顯視窗開啟後，主視窗尚未開始銷售（購物車空、未識別會員）時顯示
`IdleScreen`；主視窗於 `/checkout` 路由掃入商品或識別會員後，二顯切換為
`ShoppingScreen`。

## 觸發條件（本頁無操作步驟，改記錄主視窗做了什麼操作會讓二顯畫面切換）

1. **Idle**：二顯開啟後預設即為 `IdleScreen`（`useCustomerDisplaySnapshot`
   初始值 `{ view: 'CHECKOUT_IDLE' }`），主視窗尚未推送任何非 IDLE 快照，或
   購物車與會員皆已清空且結帳完成展示旗標為否時亦回到此畫面。
2. **Shopping**：主視窗於 `/checkout` 路由下，購物車商品明細非空，或已透過
   會員資訊卡查詢識別出正式會員，任一成立，且促銷結算對話框未開啟，二顯即
   切換為 `ShoppingScreen`（對應主視窗操作見
   `entries/checkout/references/03-search-and-add-items.md`「搜尋與加入商品」
   步驟）。
3. 已識別會員但尚未刷入商品時，`ShoppingScreen` 顯示「會員歡迎卡片」而非
   「最後刷入商品卡片」；兩者為互斥的左側區塊，二擇一顯示。

## 系統驗證行為（依原始碼描述各區塊顯示的資料；⚠️ 尚未實機驗證）

### IdleScreen（`data-testid="customer-display-idle-screen"`）

- 上方為漸層背景輪播卡片，每張含「本期主打」標籤 + 大標題 + 副標題 + 補充
  說明三層字級。多張 banner 時每 4.5 秒自動切換一張並同步更新下方圓點指示器；
  僅 1 張時不啟動計時器、不顯示圓點指示器，維持恆定顯示——目前 `idle-banners.ts`
  的假資料（`cIdleBanners`）只有 1 筆（「新會員首購禮」），故現況必為恆定
  顯示、無輪播切換，尚不接 NorwegianForest 表格或後台管理 UI。
- 下方固定顯示品牌歡迎標語「★ 歡迎光臨寵物公園 · 帶來您毛孩最好的陪伴 ★」。

### ShoppingScreen（`data-testid="customer-display-shopping-screen"`）

- 已識別會員時，頂部顯示 `MemberInfoCard`（`data-testid="customer-display-member-info"`）：
  第一行為姓名 + 卡別徽章（黑卡＝黑底、金卡＝金底，其餘沿用品牌色）+ 會員點數
  + 升級/維持黑卡差額；第二行為會籍期間 + 會員編號 + 遮蔽後手機號碼（如
  `0912-***-2345`）。未識別會員時整個卡片不渲染。
- 左側依狀態三選一：
  - 已刷入商品：顯示最後刷入商品名稱（`data-testid="last-scanned-item-name"`）
    + 定價（劃線）與會員價（強調）雙欄，兩者皆取自商品主檔，與購物車是否已
    識別會員無關。
  - 尚無商品但已識別會員：顯示會員點數、升級/維持黑卡差額、會員優惠券張數
    （門市/美容/通用三類分別統計）、目前發票設定（`InvoiceSection`）。
  - 兩者皆無：提示文字「請刷入商品條碼」。
- 右側固定寬度購物明細清單，逐項顯示商品名稱、單價 × 數量、小計，超出可視
  高度時原生捲動；底部固定提示文字「促銷折抵金額將於結算時顯示」——本畫面
  **不**逐項顯示折扣明細（折扣須待促銷結算對話框開啟、二顯切至
  `PaymentScreen` 才會顯示，見 `02-payment-and-completed.md`）。

## 注意事項

- 二顯視窗必須先被主視窗開啟才存在（由主視窗頂欄「二顯」按鈕或 F9 快捷鍵
  觸發，屬 `entries/checkout/AGENT.md` 範圍，本文件不重複撰寫）。若
  `list_electron_windows` 只回報一個視窗，代表二顯目前未開啟或連線失敗，
  需先確認雙螢幕/F9 設定，而非直接判定畫面異常。
- 二顯 renderer 完全解耦主視窗 Zustand store，純以 IPC `customer-display:snapshot`
  channel 被動接收快照更新，因此無法透過主視窗 DOM/store 間接驗證二顯畫面
  內容，必須直接對二顯視窗操作（screenshot / query DOM）。
- 輪播 banner 目前只有假資料，未接中台真實資料或後台管理 UI；未來若替換資料
  來源，`IdleScreen` 元件與 `IdleBanner` 型別皆不需變動（見 `idle-banners.ts`
  註解）。
