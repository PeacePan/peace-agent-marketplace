# 首頁（`/`）Agent 指引

> ⚠️ 本文件僅依原始碼撰寫，尚未經 runtime 畫面驗證（撰寫當下 Ragdoll dev 環境
> 未啟動，`list_electron_windows` 回報找不到任何視窗），下次有 Ragdoll dev
> 環境啟動的 session 時應補做。

## 入口資訊

- 網址：`/`
- 本路由在桌面版應用程式內沒有導航入口——開機時主視窗直接載入 `/checkout`
  （`electron/main/main.ts` 的 entryURL 固定為 `<base>/checkout`），程式碼中
  也找不到任何連結導向 `/`；僅在手動輸入網址（或 dev 環境用瀏覽器開
  `localhost:3100`）時可見。
- 無需登入**銷售員**即可看到，但 `/` 不在
  `next/components/elements/app-initializer/index.tsx` 的裝置令牌 bypass
  名單內（該名單只有 `/customer-display`、`/print-preview`），所以仍要先過
  裝置令牌登入與資料同步，才會渲染到此頁。
- 主元件：`next/app/page.tsx`（`Home`）。

---

## 介面佈局（僅依原始碼撰寫，尚未經 runtime 畫面驗證）

依 `page.tsx` 的 CSS class 客觀描述：外層 `flex items-center justify-center`
容器撐滿視窗高度，內含一張 `max-w-3xl` 白色卡片；卡片內文字與按鈕在小螢幕
（預設）為 `items-center`（置中），`sm` 以上斷點為 `sm:items-start`（靠左）。
標題「萬達寵物 POS 桌面版」下方為按鈕格線（`grid`），預設單欄、`sm` 以上為
`sm:grid-cols-3` 三欄，內含兩個按鈕（`CheckoutButton`，`size="lg"`）。頁面
本身沒有獨立的 `components/` 子目錄、沒有 state、沒有 hook（`'use client'`
純靜態頁面）。實際視覺呈現（是否真的靠左或置中）尚未經 runtime 畫面驗證。

---

## 按鈕配置

| 按鈕 | 樣式 | 導向 |
|---|---|---|
| 開始結帳 | 實色（預設 `variant`） | `/checkout` |
| 訂單查詢 | 外框（`variant="outline"`） | `/summary` |

兩個按鈕都是 Next.js `<Link>` 純前端路由跳轉，原始碼未見任何 disabled 條件、
loading 狀態或前置 API 呼叫。「訂單查詢」點擊後會跳轉到 `/summary`，`/summary`
本身尚未撰寫手冊，此處只描述「點擊後會跳轉到 `/summary`」這個導航行為本身，
不描述 `/summary` 頁面內容。

---

## 業務流程索引

| 流程 | 參考檔案 |
|------|---------|
| 從首頁進入結帳或訂單查詢 | `references/01-navigate-from-home.md` |

---

## 與 `ragdoll-project-knowledge` 的分工

本文件只記錄操作路徑與畫面結構。業務規則與限制（如 `/summary` 頁面本身的
付款/結帳邏輯）的權威來源是同專案的 `ragdoll-project-knowledge` skill
（`Ragdoll/.claude/skills/ragdoll-project-knowledge/references/`），本文件不
重複維護規則細節，只在必要處連結過去。

---

## 重要限制（本次範圍內已確認）

- 本路由在桌面版應用程式內實質上不會被門市人員看到：開機時主視窗直接載入
  `/checkout`（見「入口資訊」），程式碼中沒有任何連結、按鈕或程式化導航
  （`router.push`/`router.replace`）指向 `/`，只有手動輸入網址才會抵達此頁。
