# `ragdoll-electron` MCP 工具眉角

Step 5 實機操作前掃一遍；點擊不如預期時回來查。這些都是實測踩過的坑，不是推測。

## 通則

- **工具回報「成功」≠ 狀態真的變了。** 點到背景層、點到同名元素、填到別的欄位，工具都照樣回「成功」。每個關鍵操作後截圖（或讀狀態）確認。
- **用 `electron_get_page_structure` 取得按鈕的 `className`，組出唯一 selector**（例：只有「帶入」鈕同時有 `bg-primary` 與 `h-8`，所以 `button.bg-primary.h-8` 唯一命中；標頭「立即同步」是 `h-auto`、「小計」是 `h-12`）。
- **泛用 selector 會點到被彈窗遮住的背景元素。** CDP 的 JS click 不受遮罩阻擋——`button.bg-primary` 曾點到標頭的「立即同步」，`button.h-9.border-input` 曾點到會員的「歷史消費」。這兩個只是唯讀動作，但同樣的失誤若發生在「取消銷售」「確認結帳」就是事故。
- **對話框是一層層疊的**：`Escape` 關閉最上層。結算彈窗（美容結帳優惠彙整）按 `Escape`＝退回「帶入清單」並放棄帶入，是不付款收尾的好方法。
- 同一個 selector 約 1 秒內、同一個元素約 2 秒內重複點擊會被節流（`Element click prevented - too soon after previous click`），拆成獨立呼叫並在被擋時重試。

## 下拉與選單

- Radix `DropdownMenu`／`Popover` 觸發鈕用 `electron_click_by_text` 常在同一次呼叫內被判成「點了又點到外部」而立刻關閉，看起來沒反應。穩定做法：先點一次讓它拿到 focus，再 `electron_press_key(key: "Enter")` 開啟，選項用 CSS selector（如 `[role="menuitem"]:nth-of-type(2)`）或 `click_by_text` 點。（例：結帳頁左上角「商品 ▾」是商品／美容模式切換器。）
- 原生／Radix `<Select>` combobox 同理：點開後 `Enter` 選預設第一項，或用 CSS selector 指定。
- 剛按完觸發鈕馬上 `press_key` 有時會被吞掉（鍵盤還沒掛載）：中間夾一次截圖。

## `electron_click_by_text`

- 對含中文的較長字串，有時會因內部 `btoa` 丟出 `Latin1 range` 錯誤——工具限制，不是操作錯誤，改用 `electron_click_by_selector`。
- **同一畫面多個同字按鈕時可能命中錯的**：商品搜尋與會員搜尋都有「查詢」；疊了多層 Dialog 時，「帶入」「取消」「關閉」「退貨」在不同層都有，可能命中背景那層而仍回報成功（已實測：查 DB 發現資料根本沒寫入才發現點錯層）。改用 selector，或先用 Escape 退到單層再點。

## `electron_fill_input`

- 用 placeholder 定位時，回報的目標名稱常不是輸入框本身（曾回報填入「查詢」按鈕，或整個數字鍵盤的文字容器），**結果不可信**；「全部清除」之後輸入框重繪，也曾完全沒填進去（送出後跳「請輸入會員資訊」）。
- 頁面上只有一個輸入框時用 `selector: "input"`，之後 `electron_press_key("Enter")` 在該輸入框內送出（不要靠按鈕文字比對），並用截圖確認內容。

## 數字鍵盤（員編登入、機台代號）

- 這類輸入框是自訂鍵盤 UI，`fill_input` 無效。逐位 `electron_click_by_text("7")`，**每位一次獨立呼叫**；即使如此仍常被節流擋下（實測約四成），被擋就重試同一位。
- 員編 `0` 與 `1` 會重複出現，務必逐位確認；送出前**截圖核對輸入框顯示的數字**，再按「確認」。
- 如果頁面剛重載、Next 正在重新編譯，按鍵會被吃掉，等頁面穩定再輸入。

## `electron_eval`

- 安全掃描器會擋下**任何含 `=` 的程式碼**（連 `input[type="number"]`、箭頭函式 `=>`、`===` 都會被擋）。
- 帶回呼函式的表達式（`.filter(function…)`、`.map(function…)`）實測會**不報錯、直接回 `null`**；`indexOf` 與字串內含中文也疑似受影響（未逐一隔離）。只有 `.length` 這類簡單表達式與數字回傳穩定。
- 所以 `eval` 只拿來做簡單的點擊或讀數字，例如：
  ```js
  document.getElementsByTagName('input')[4].parentElement.getElementsByClassName('bg-destructive')[0].click()
  ```
  需要「找到哪顆按鈕」時，用 `get_page_structure`＋`click_by_selector`，不要在 `eval` 裡寫搜尋邏輯。

## 日期範圍選擇器

shadcn `Calendar` popover，不是純文字輸入框：點日期文字按鈕開啟月曆後，用 `electron_click_by_selector` 點 `button.rdp-button_previous`／`.rdp-button_next` 換月，再用 `electron_click_by_text` 點日期數字。

## 實體列印會凍住整個 renderer

在沒有連接實體 POS 印表機的 macOS 開發環境下，觸發任何列印流程（折讓證明單、發票、小白單…）會讓整個 renderer 的 JS event loop 凍結：`electron_take_screenshot`／`electron_eval` 的 CDP `Runtime.evaluate` 全部逾時，而且單獨殺列印 utility 子程序（`printing.mojom.UnsandboxedPrintBackendHost`）救不回來，因為卡住的是原生系統列印對話框。

- **最好的因應是提前避開**：條件不是明確要求「確認紙本內容」時，改用 SQL 查欄位值（如 `credit_note_no`／`credit_note_id`）驗證邏輯，不點會觸發列印的「確認完成」類按鈕；真的要驗版面，改用程式碼追蹤（讀版面組裝函式，確認欄位值原樣輸出），並在報告標明是論證、不是肉眼比對。
- **已凍住時的唯一解法**是結束 Electron 主程序再重啟。這是少數需要強殺的情況，但仍只殺**自己 worktree** 的：
  ```bash
  ps -eo pid,command | grep "electron/dist/electron/main/main.js" | grep <你的 worktree 名>   # 找主程序 PID
  kill -9 <PID>
  lsof -nP -iTCP:3100 -sTCP:LISTEN     # 重啟後若 EADDRINUSE，找出殘留的 next-server 並 kill
  ```
  不要用 `pkill -9 -f "electron/dist/…"`——會殺掉整台機器上所有 Ragdoll。
