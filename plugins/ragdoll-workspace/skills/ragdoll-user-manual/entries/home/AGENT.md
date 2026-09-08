# 首頁（`/`）Agent 指引

> ⚠️ 本文件僅依原始碼撰寫，尚未經 runtime 畫面驗證（撰寫當下 Ragdoll dev 環境
> 未啟動，`list_electron_windows` 回報找不到任何視窗），下次有 Ragdoll dev
> 環境啟動的 session 時應補做。

## 入口資訊

- 網址：`/`
- 無需登入即可看到，是應用程式啟動後的第一個畫面。
- 主元件：`next/app/page.tsx`（`Home`）。

---

## 介面佈局（僅依原始碼撰寫，尚未經 runtime 畫面驗證）

單欄置中佈局：標題「萬達寵物 POS 桌面版」，下方並排兩個按鈕（`CheckoutButton`，
`size="lg"`）。頁面本身沒有獨立的 `components/` 子目錄、沒有 state、沒有
hook（`'use client'` 純靜態頁面）。

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
