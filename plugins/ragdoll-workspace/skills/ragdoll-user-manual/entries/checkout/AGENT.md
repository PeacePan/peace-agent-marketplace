# 結帳入口（`/checkout`）Agent 指引

## 入口資訊

- 網址：`/checkout`
- 頁面標題：「萬達寵物 POS 應用程式」，品牌列顯示「寵物公園 v1.0.0」
- 主元件：`next/app/checkout/page.tsx`（`CheckoutPage`）

**本文件範圍**：本次僅涵蓋「一般商品模式的主線」（登入 → 開帳 → 掃碼加入商品 →
小計）與「功能選單（`pos-menu-drawer`）按鈕總覽」。`/checkout` 同時承載一般商品
與美容兩種模式（見下方「與美容模式的關係」），美容模式本身、促銷結算、退貨、
換購、外送匯入、暫結等其餘功能本次列為待補（見 `ragdoll-user-manual/SKILL.md`
索引），涉及這些範圍的驗收條件應標記「⚠️ 無法驗證（手冊尚未涵蓋此範圍）」。

---

## 介面佈局（已用 `electron_take_screenshot` + `electron_get_page_structure` 對真實啟動的 Ragdoll dev 環境驗證，2026-09-08）

三欄式佈局：

| 區域 | 位置 | 內容 |
|------|------|------|
| 頂欄（品牌列） | 最上方 | 左：品牌名「寵物公園 vX.X.X」+ 檢查更新；右：連線狀態（已連線/發票機/二顯切換）、`SalerLogin`（銷售員資訊或登入輸入框 + 登出按鈕）、「開錢櫃」按鈕、「功能選單」按鈕（`PosMenuDrawer`） |
| 資訊列 | 頂欄下方 | 門市、機台、銷售人員、通路（如「門市銷售」）、帳務日、銷售時間、資料同步時間 + 「立即同步」按鈕 |
| 左側：商品輸入與清單 | 中間偏左 | 模式下拉選單（商品/美容）+ 條碼/貨號輸入框 + 「查詢」+ 「外送」按鈕；下方「商品明細」列表區 |
| 右側：會員與結帳 | 右側 | 「會員資訊」卡（手機號碼/會員編號/員工編號輸入 + 查詢）、「發票方式」卡（手機載具/統一編號/捐贈發票）、「結帳摘要」卡（銷售小計、總金額、檢查數量、「小計」按鈕、「全部清除」、「交易暫結」） |

**未開帳時的遮罩**：商品明細區顯示「目前為關帳狀態，如需結帳請先完成開帳動作」
與一個「立即開帳」按鈕（實機截圖已確認此文字與按鈕存在）。這是除了「功能選單 →
開帳」之外，另一個能開啟開帳對話框的入口。

**銷售員未登入時**：頂欄的 `SalerLogin` 顯示輸入框（`data-testid="saler-input"`）
與「登入」按鈕（`data-testid="saler-login-btn"`）；輸入框本身是唯讀觸發器，點擊
會開啟數字鍵盤 Popover（`saler-keypad-popover`）輸入工號後按 Enter 確認。登入後
顯示銷售員姓名（`data-testid="saler-name-display"`，格式「銷售員: {displayName}」）
與「登出」按鈕（`data-testid="saler-logout-btn"`）。

---

## 開帳狀態守門（`guardCheckout`，MUST 先確認再驗收——見 `ragdoll-acceptance-workflow` Step 0b）

`next/app/checkout/page.tsx:149-165`：

- `isCheckoutDisabled = openCloseEntryState.reportStatus !== 'OPENED'`
- `guardCheckout()`：`reportStatus === 'REOPEN'` 時 toast「已超過營業時間，請先至
  功能選單重新開帳」；其餘非 `OPENED` 狀態 toast「請先至功能選單進行開帳」。
- 掃描、數量變更、移除、變價、小計等操作型動作在執行前都會呼叫 `guardCheckout()`，
  未開帳時全部被攔下。

---

## 與美容模式的關係

`item-input.tsx` 有模式下拉選單（`data-testid="mode-dropdown-trigger"`，選項
`mode-option-item`「商品」/ `mode-option-salon`「美容」）。切換模式會清空購物車
與已綁定會員（`page.tsx` 的 `handleModeSwitch`／`resetCheckoutState`），所以測試
時 MUST 先切模式再登入會員。本文件僅涵蓋「商品」模式；美容模式列入待補。

---

## 功能選單（`PosMenuDrawer`，`next/app/sidemenu/pos-menu-drawer/index.tsx`）

觸發按鈕：頂欄「功能選單」（`data-testid="pos-menu-btn"`），未登入銷售員時
`disabled`。開啟後是右側滑出的 Drawer，依「商品／美容」分頁呈現（預設分頁對應
目前的結帳模式，使用者仍可在 Drawer 內自由切換分頁瀏覽，不影響實際結帳模式）。

### 商品分頁（`data-testid="menu-tab-item"`）

| 按鈕 | data-testid | 說明 / disabled 條件 |
|---|---|---|
| 開帳 / 修改開帳金額 | `menu-opening-btn` | 已開帳時顯示「已開帳」Badge，點擊變成「修改當班金額」；`reportStatus === 'REOPEN'`（跨日未關帳）時 disabled，且點擊會被導去先清帳 |
| 關帳 | （無 testid） | `reportStatus === 'CLOSED'` 時 disabled |
| 銷售查詢(退換貨) | `menu-exchange-return-btn` | 已關帳或外送平台訂單鎖定（`isLockedByImport`）時 disabled |
| 價格查詢 | `menu-price-search-btn` | — |
| 客訂 | `menu-customer-order-btn` | 點擊時若未登入銷售員會 toast「請先登入銷售員」並不開啟 |
| 截角（截角兌換） | `menu-voucher-redemption-btn` | 點擊時若非正式 WonderPet 會員 toast「截角兌換前，請先完成會員登入」；若未開帳 toast「請先開帳後再進行截角兌換」 |
| 分批取 | `menu-batch-pickup-query-btn` | — |
| 專櫃管理 | （無 testid） | 僅支援專櫃門市時顯示（`isSailorCounterClosed` 非 null/undefined） |

### 美容分頁（`data-testid="menu-tab-salon"`）

| 按鈕 | data-testid | 說明 |
|---|---|---|
| 銷售查詢(退換貨) | `menu-salon-return-btn` | 開啟 `SalonSalesQueryDialog` |
| 活動列表 | （無 testid） | **尚未實作**：點擊觸發 `toast({ description: '活動列表 功能開發中' })`，不開啟任何畫面 |
| 工單列表 | （無 testid） | **尚未實作**：點擊觸發 `toast({ description: '工單列表 功能開發中' })`，不開啟任何畫面 |

> 「活動列表」「工單列表」這兩個尚未實作、改用 toast 提示的按鈕，正是
> 「功能按鈕不可因業務狀態 disabled、一律改為可點擊 + toast 說明」這個既有規範
> 已經落地的範例（見 `next/app/sidemenu/pos-menu-drawer/index.tsx:74-78` 的
> `handleMenuClick`）。

---

## 業務流程索引

| 流程 | 參考檔案 |
|------|---------|
| 開機與銷售員登入 | `references/01-boot-up-and-login.md` |
| 開帳 | `references/02-open-register.md` |
| 搜尋與加入商品 | `references/03-search-and-add-items.md` |
| 小計與結帳送出 | `references/04-checkout-and-payment.md` |
| 功能選單按鈕總覽 | `references/05-pos-menu-drawer-overview.md` |

---

## 與 `ragdoll-project-knowledge` 的分工

本文件只記錄操作路徑與畫面結構。業務規則與限制（如截角兌換的完整守門邏輯、
開帳時「卡帳」偵測與處理流程等）的權威來源是同專案的 `ragdoll-project-knowledge`
skill（`Ragdoll/.claude/skills/ragdoll-project-knowledge/references/`），本文件
不重複維護規則細節，只在必要處連結過去。

---

## 重要限制（本次範圍內已確認）

- 未開帳（`reportStatus !== 'OPENED'`）時無法掃描、變更數量、移除、變價、小計。
- 客訂功能需先登入銷售員。
- 截角兌換需先登入正式會員 + 已開帳。
- 切換商品/美容模式會清空購物車與已綁定會員。
- 「活動列表」「工單列表」目前僅顯示「功能開發中」提示，尚未有實際功能。
