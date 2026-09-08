# 客顯二顯螢幕入口（`/customer-display`）Agent 指引

> ⚠️ 本文件僅依原始碼撰寫，尚未經 runtime 畫面驗證（撰寫當下 Ragdoll dev 環境
> 未啟動，`list_electron_windows` 回報找不到任何視窗），下次有 Ragdoll dev
> 環境啟動的 session 時應補做；結帳完成 phase 需實際送出付款才能觸發，需具備
> 可操作的刷卡機/現金設備才能完整驗證，付款中 phase 可由點擊小計、進入促銷
> 結算對話框驗證，不需要實體設備，見 `references/02-payment-and-completed.md`
> 開頭標註。

## 入口資訊

- 網址：`/customer-display`
- **渲染機制：獨立的第二個 Electron `BrowserWindow`，不是主視窗內的路由跳轉**
  （`electron/main/settings/customer-display-manager.ts` 的 `open()` 會另外
  建立一個 `BrowserWindow` 並載入此路由；`test/e2e/pages/customer-display-screen-page.ts`
  檔頭註解亦明確寫「二顯是獨立的第二個 BrowserWindow」）。畫面透過 IPC 訂閱
  主視窗推送的 `CustomerDisplaySnapshot`（channel `customer-display:snapshot`）
  被動更新，**本身沒有任何可互動的按鈕**，是一個唯讀的顧客端顯示畫面。
- 開關入口：主視窗頂欄「二顯」按鈕（`data-testid="customer-display-toggle"`）
  或 F9 快捷鍵，屬 `entries/checkout/AGENT.md` 範圍（見其「介面佈局」表格頂欄
  一列的「二顯切換」），本文件不重複撰寫該按鈕細節。
- 主元件：`next/app/customer-display/page.tsx`（`CustomerDisplayPage`）。
- 專用 Layout：`next/app/customer-display/layout.tsx`——最小結構（淺色底、
  全螢幕、字級整體放大 150%），不引用主頁面的 sidebar / toolbar / toaster
  等 UI 元件，確保二顯畫面乾淨、不受主視窗 UI 干擾。

---

## 介面佈局（僅依原始碼撰寫，尚未經 runtime 畫面驗證）

依主視窗推送的 `snapshot.view` 分派四個 phase 畫面，非 `CHECKOUT_*` 一律
fallback 至 IdleScreen：

| Phase | UI 元件 | 觸發條件（摘要，詳見對應 references） |
|---|---|---|
| `CHECKOUT_IDLE` | `IdleScreen` | 購物車空、未識別會員，且非結帳完成後 8 秒展示期間；或購物車非空／已識別會員，但主視窗離開 `/checkout`、`/summary`（例如切到美容結帳摘要）且促銷結算對話框未開啟 |
| `CHECKOUT_SHOPPING` | `ShoppingScreen` | 購物車非空或已識別會員，且主視窗在 `/checkout` 路由、促銷結算對話框未開啟 |
| `CHECKOUT_PAYMENT` | `PaymentScreen` | 購物車非空或已識別會員，且主視窗在 `/summary` 路由或促銷結算對話框開啟中 |
| `CHECKOUT_COMPLETED` | `CompletedScreen` | 購物車與會員皆已清空、結帳完成旗標為真（完成後 8 秒自動回 `CHECKOUT_IDLE`） |

各 phase 畫面內容詳見「業務流程索引」對應的 references 文件。

---

## 按鈕配置

**無可互動按鈕，本頁為唯讀顯示。** `page.tsx` 與四個 phase 元件
（`idle-screen.tsx`／`shopping-screen.tsx`／`payment-screen.tsx`／
`completed-screen.tsx`）及其共用子元件（`invoice-section.tsx`／
`member-info-card.tsx`）皆未見任何按鈕、輸入框或 `onClick` handler，純粹
依 IPC 推送的快照被動渲染。型別定義（`electron/main/types/customer-display.ts`）
雖保留 `PHONE_CONFIRMATION`／`OTP_DISPLAY`／`CUSTOM_MESSAGE`／`SIGNATURE_REQUEST`
等互動 view 骨架，但註解明確標示「POC 階段僅實作 4 個 CHECKOUT_* view」，
`page.tsx` 對非 `CHECKOUT_*` 的 view 一律 fallback 至 `IdleScreen`，目前不會
渲染這些互動畫面。

---

## 業務流程索引

| 流程 | 參考檔案 |
|------|---------|
| 閒置與購物中畫面 | `references/01-idle-and-shopping.md` |
| 付款中與完成畫面 | `references/02-payment-and-completed.md` |

---

## 與 `ragdoll-project-knowledge` 的分工

本文件只記錄操作路徑與畫面結構。業務規則與限制（如 phase 判斷優先序、促銷
結算對話框開啟期間為何改判為 `CHECKOUT_PAYMENT`、`completedSnapshot` 快照
時序等細節）的權威來源是同專案的 `ragdoll-project-knowledge` skill
（`Ragdoll/.claude/skills/ragdoll-project-knowledge/references/`），本文件
不重複維護規則細節，只在必要處連結過去。

---

## 重要限制（本次範圍內已確認）

- 二顯視窗必須先被主視窗開啟才存在（見「開關入口」）。若 `list_electron_windows`
  只回報一個視窗，代表二顯目前未開啟或連線失敗，需先確認雙螢幕/F9 設定，而非
  直接判定畫面異常。
- 二顯 renderer 完全解耦主視窗 Zustand store，純以 IPC 被動接收快照更新
  （`use-customer-display-snapshot.ts` 註解），無法透過主視窗 DOM/store 間接
  驗證二顯畫面內容，必須直接對二顯視窗操作（screenshot / query DOM）。
- 結帳完成 phase 需實際送出付款才能觸發，需要實際刷卡機/現金設備才能完整
  驗證；付款中 phase 可由點擊小計、進入促銷結算對話框驗證，不需要實體設備。
  本次手冊該部分僅依原始碼撰寫，見 `references/02-payment-and-completed.md`
  開頭標註。
