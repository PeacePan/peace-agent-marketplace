---
name: maltese-dialog-system
description: >
  Maltese POS Dialog 系統完整知識庫。涵蓋 UICtrllerContext 架構、DialogContentName 型別定義、
  dialogStack 生命週期（openDialog → closeDialog → clearDialog），
  以及 SaleConsole 四個子元件（item/Checkout、item/Management、salon/Checkout、salon/Management）
  各自擁有的 Dialog 清單與 childProps 依賴分析。

  以下情況必須參考此文件再動手：
  - 新增或修改 Maltese Dialog（包含 Task Dialog 與非 Task Dialog）
  - 修改 UICtrllerContext 的 dialogStack、openDialog、closeDialog、clearDialog 邏輯
  - 需要知道某個 Dialog 屬於哪個 SaleConsole 子元件
  - 需要判斷某個 Dialog 是否需要 childProps 才能開啟
  - 修改 SaleConsole 的 tab 結構或 Dialog 觸發按鈕
  - 實作與 Dialog 生命週期相關的 hook 或 side effect
---

# Maltese Dialog 系統知識庫

## 核心檔案位置

| 用途 | 檔案路徑 |
|------|----------|
| Dialog 管理 Context | `src/contexts/uiCtrller.tsx` |
| SaleConsole 主元件 | `src/components/layouts/saleConsole/index.tsx` |
| SaleConsole 介面定義 | `src/components/layouts/saleConsole/interface.ts` |
| item/Checkout | `src/components/layouts/saleConsole/item/Checkout.tsx` |
| item/Management | `src/components/layouts/saleConsole/item/Management.tsx` |
| salon/Checkout | `src/components/layouts/saleConsole/salon/Checkout.tsx` |
| salon/Management | `src/components/layouts/saleConsole/salon/Management.tsx` |
| TaskName 型別定義 | `src/components/tasks/interface.ts` |

---

## 各章節參考文件

### UICtrllerContext 架構
參見 [references/01-uictrller-context.md](./references/01-uictrller-context.md)：
- `dialogStack` 資料結構與最大層數限制
- `openDialog` / `closeDialog` / `clearDialog` 完整生命週期
- `DialogContentName` = `TaskName` + 非 Task Dialog 名稱的聯合型別
- `UICtrllerDialogProps` 各欄位說明

### SaleConsole 元件結構
參見 [references/02-sale-console-structure.md](./references/02-sale-console-structure.md)：
- SaleConsole 的 tab 結構（item: 結帳/商品/管理，salon: 結帳/管理）
- 頁面對應關係（`/checkout` → item、`/salon` → salon）
- BootUp `isCompleted` 與 SaleConsole 掛載的前置條件

### 各元件 Dialog 清單與 childProps 分析
參見 [references/03-dialog-inventory.md](./references/03-dialog-inventory.md)：
- 四個子元件各自的 `openDialog` 呼叫清單
- 每個 Dialog 是否需要 `childProps`（可否無參數開啟）
- 每個 Dialog 附帶的 `dialogProps`（例如標題）

### myFuncCompFactory 模式
UICtrllerContext 及大部分 Maltese Context 都使用 `myFuncCompFactory` 產生。
若需深入了解此模式，請參考 `maltese-knowledge-base:maltese-libs` skill。
