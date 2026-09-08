# 確認或取消列印

> 來源：原始碼（`next/app/print-preview/page.tsx`、`next/app/print-preview/layout.tsx`、
> `electron/main/settings/print-preview-manager.ts`）+ E2E Page Object
> （`test/e2e/pages/print-preview-window.ts`，實際場景見
> `test/e2e/6-delivery-mark-print/delivery-mark-print.spec.ts`）。
> ⚠️ 尚未經 runtime 驗證：本次手冊已涵蓋範圍內找不到可合法觸發列印預覽視窗的
> 操作路徑（唯一呼叫點屬 `SalesQueryDialog` 底下的外送單標記對話框，已被
> `entries/checkout/references/05-pos-menu-drawer-overview.md` 標註「超出本次
> 範圍」），撰寫當下 Ragdoll dev 環境亦未啟動。

## 適用情境

由某個列印動作觸發（呼叫端呼叫 `ragdollAPI.printPreview.open(html)`）後，
main process 動態開啟獨立的第二個 BrowserWindow 並彈出，展示即將列印的 PDF
內容，等待使用者確認或取消。目前程式碼中唯一的呼叫端是外送單標記資訊對話框的
「列印」按鈕（`delivery-mark-info-dialog/index.tsx` 的 `handlePrint`），但該
入口不在本次手冊範圍內，本篇只描述列印預覽視窗本身收到 `open()` 呼叫之後的
畫面與操作。

## 操作步驟

1. 預覽視窗開啟後，先顯示 `<div data-testid="print-preview-loading">`（PDF
   尚未就緒）。
2. 等待 `<embed data-testid="print-preview-embed">` 出現，代表 main process
   已推送 PDF bytes 完成，Chromium 內建 PDF viewer 已渲染呼叫端提供的內容。
3. 點擊「取消」或「確認列印」：
   - **取消**：一律可點擊，回報 `cancelled` 決定。
   - **確認列印**：PDF 就緒前（`print-preview-embed` 尚未出現）此按鈕
     disabled，無法點擊。

## 系統驗證行為

- 點擊「取消」或「確認列印」後，main process 的 `print-preview:decision`
  handler 會先 resolve 呼叫端 `open()` 等待中的 Promise，再呼叫
  `this.window?.close()`，預覽視窗應隨即關閉。
- 呼叫端收到 `'confirmed'` 才會執行真正的列印動作（如
  `printDeliverySlipForSale`），收到 `'cancelled'` 則直接略過，不觸發任何
  實體列印。
- E2E 的 `confirmPrint()` / `cancel()` 皆以 `Promise.all` 併發等待視窗
  `close` 事件與按鈕點擊動作（見 `print-preview-window.ts` 註解：決定回報後
  main process 幾乎同步呼叫 `close()`，視窗可能在點擊動作的 Promise resolve
  之前就已經關閉；若在點擊之後才掛上 `close` 事件監聽，會錯過已觸發過的事件
  永遠等不到）。這代表**視窗關閉可能發生得很快**，實機操作或後續補做 runtime
  驗證時，記錄視窗數變化或等待關閉的時機需與觸發點擊動作併發進行，不要先點擊
  再另外等待。
- 未收到任何決定即關閉視窗（含使用者直接按原生關閉鈕）一律視為 `'cancelled'`
  （`previewWindow.on('closed', ...)` 內部呼叫 `resolveDecision('cancelled')`）。

## 注意事項

- 同一時間只允許一個預覽視窗：呼叫端若在既有預覽視窗開啟中再次呼叫 `open()`，
  只會 `focus()` 既有視窗，不會產生第二個視窗，這次呼叫本身會直接 reject。
- 正式列印可能牽涉實體印表機動作，驗證此頁面時優先選「取消」驗證關閉行為，
  除非情境明確需要驗證「確認列印」後的實際列印結果。
- 本篇所有畫面內容與行為描述皆僅依原始碼撰寫，尚未經 `list_electron_windows` +
  `electron_take_screenshot` 之類的 runtime 驗證，待 checkout 外送單/報表等
  列印相關子功能補齊手冊、且該次撰寫時 Ragdoll dev 環境有啟動時，應一併補做。
