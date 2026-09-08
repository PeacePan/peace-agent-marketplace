# 列印預覽入口（`/print-preview`）Agent 指引

> ⚠️ 本文件僅依原始碼撰寫，觸發此視窗的入口目前不在已撰寫手冊的範圍內，尚未經
> runtime 畫面驗證，待 checkout 列印相關功能（外送單/報表等）補齊手冊後應補做
> runtime 驗證。撰寫當下 Ragdoll dev 環境亦未啟動（`list_electron_windows` 回報
> 找不到任何視窗）。

## 入口資訊

- 網址：`/print-preview`
- **渲染機制：獨立的第二個 Electron `BrowserWindow`，不是主視窗內的路由跳轉，
  也沒有可從 UI 直接導航進入的入口**（`electron/main/settings/print-preview-manager.ts`
  的 `PrintPreviewManager.open(html)` 由呼叫端在使用者觸發某個列印動作時動態
  建立；建立流程：先以 `show:false` 建立隱藏視窗 → `loadURL('about:blank')` →
  `executeJavaScript` 寫入呼叫端傳入的 HTML → `printToPDF()` 取得 PDF bytes
  （不落地暫存檔）→ 導向 `/print-preview` 路由 → `maximize()` + `show()`）。
- 同一時間只允許一個預覽視窗：已開啟時再次呼叫 `open()` 會 `focus()` 既有視窗並
  直接 reject 這次呼叫，不會產生第二個視窗。主視窗關閉時 `main.ts` 會一併呼叫
  `printPreviewManager.close()`，避免預覽視窗孤立殘留。
- **本次範圍內找不到可合法觸發的入口**：`grep -rln "printPreview.open" next/
  electron/`（排除 build 產物）只找到一處呼叫點——
  `next/app/checkout/components/sales-query-dialog/components/delivery-mark-info-dialog/index.tsx`
  的「列印」按鈕（外送單標記資訊對話框）。此對話框掛在「銷售查詢(退換貨)」
  （`menu-exchange-return-btn`）之下的 `SalesQueryDialog` 內，而
  `entries/checkout/references/05-pos-menu-drawer-overview.md` 已明確將
  `SalesQueryDialog` 標註「超出本次範圍」，故本次手冊已涵蓋範圍內沒有任何一個
  合法可操作的觸發點，本文件全篇僅依原始碼撰寫。
- 主元件：`next/app/print-preview/page.tsx`（`PrintPreviewPage`）。
- 專用 Layout：`next/app/print-preview/layout.tsx`——`fixed inset-0` 撐滿整個
  視窗（黑底 + 置中白色內容欄，寬度沿用 `--app-width`），因為此視窗會被
  main process `maximize()`，不能沿用其餘頁面 `h-(--app-height)` 的 768px
  固定高度慣例；不引用主頁面的 sidebar / toolbar / toaster 等 UI 元件。

---

## 介面佈局（僅依原始碼撰寫，尚未經 runtime 畫面驗證）

上下兩段式佈局：上方為 PDF 內容區（`flex-1 overflow-hidden`），下方為固定在
底部的按鈕列（`border-t` 分隔）。

`page.tsx` mount 時呼叫 `ragdollAPI.printPreview.ready()` 通知 main process
可以推送 PDF bytes，並訂閱 `onPdfReady`：

- **尚未收到 PDF bytes**：顯示 `<div data-testid="print-preview-loading">列印
  預覽準備中...</div>`。
- **收到 bytes 後**：以 `URL.createObjectURL` 組出 blob URL，餵給
  `<embed data-testid="print-preview-embed" type="application/pdf">`，由
  Chromium 內建 PDF viewer 渲染（blob URL 為當前文件產生的同源資源，不受預覽
  視窗 origin 是 `app://` 或 `http://localhost` 影響，不會被 `webSecurity` 擋
  下）。

---

## 按鈕配置

| 按鈕 | 樣式 | 行為 |
|---|---|---|
| 取消 | 外框（`variant="outline"`），一律可點擊 | 呼叫 `ragdollAPI.printPreview.decision('cancelled')` |
| 確認列印 | 實色（預設 `variant`），`disabled={!pdfUrl}` | 呼叫 `ragdollAPI.printPreview.decision('confirmed')` |

兩者皆呼叫 main process 的 `print-preview:decision` handler：先 resolve
`open()` 呼叫端等待中的 Promise（回傳 `'confirmed'` 或 `'cancelled'`），再
`this.window?.close()` 關閉本視窗；呼叫端（如
`delivery-mark-info-dialog/index.tsx` 的 `handlePrint`）收到 `'confirmed'`
才會真正執行列印動作，`'cancelled'` 則直接略過。**「確認列印」在 PDF 尚未就緒
（`pdfUrl` 為 `null`）前 disabled，避免使用者在空白畫面下誤觸發列印。**

---

## 業務流程索引

| 流程 | 參考檔案 |
|------|---------|
| 確認或取消列印 | `references/01-confirm-or-cancel-print.md` |

---

## 與 `ragdoll-project-knowledge` 的分工

本文件只記錄操作路徑與畫面結構。業務規則與限制（如 `PrintPreviewManager` 的
單一視窗互斥機制、PDF 不落地暫存檔改以 IPC 直接推送 bytes 的安全考量等細節）
的權威來源是同專案的 `ragdoll-project-knowledge` skill
（`Ragdoll/.claude/skills/ragdoll-project-knowledge/references/`），本文件不
重複維護規則細節，只在必要處連結過去。

---

## 重要限制（本次範圍內已確認）

- 本次手冊已涵蓋範圍內沒有任何一個可合法觸發列印預覽視窗的操作路徑，唯一的
  原始碼呼叫點（外送單標記資訊對話框的「列印」按鈕）屬 `SalesQueryDialog`，已
  被 `entries/checkout/references/05-pos-menu-drawer-overview.md` 明確標註
  「超出本次範圍」。
- 本文件全篇畫面內容、按鈕行為皆僅依原始碼撰寫，未經 `list_electron_windows` +
  `electron_take_screenshot` 之類的 runtime 驗證，待 checkout 外送單/報表等
  列印相關子功能補齊手冊、且該次撰寫時 Ragdoll dev 環境有啟動時，應一併補做
  本入口的 runtime 驗證。
