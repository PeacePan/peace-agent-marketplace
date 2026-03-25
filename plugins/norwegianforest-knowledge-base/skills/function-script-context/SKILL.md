---
name: function-script-context
description: >
  NorwegianForest 專案 function 腳本撰寫的技術背景知識。
  當需要撰寫或修改 policy、batchPolicy、batchBeforeUpdate、beforeUpdate 等
  table lifecycle hook 腳本時，務必先讀此 skill，避免寫出造成無限迴圈或效能問題的腳本。
---

# NorwegianForest 腳本撰寫技術背景知識

本 skill 提供撰寫 NorwegianForest function 腳本所需的核心技術知識。
請依需求查閱以下參考文件：

## 參考文件目錄

| 文件 | 內容摘要 | 何時閱讀 |
|-----|---------|---------|
| [sandbox-vm.md](references/sandbox-vm.md) | Sandbox VM 架構、Worker Pool、MyQuery 支援方法、執行限制 | 第一次接觸此專案、遇到逾時或記憶體問題 |
| [lifecycle-hooks.md](references/lifecycle-hooks.md) | 四種 hook 的觸發時機、ignorePolicy 行為差異對照表 | 撰寫任何 hook 腳本之前 |
| [insert-vs-update.md](references/insert-vs-update.md) | batchPolicy 的 INSERT vs UPDATE 情境、oldRecords 判斷 | 撰寫 batchPolicy 腳本 |
| [anti-loop-patterns.md](references/anti-loop-patterns.md) | userContent 旗標防循環機制、已知旗標清單、完整範例 | 腳本會觸發跨表更新時 |
| [transferorder-wh-lifecycle.md](references/transferorder-wh-lifecycle.md) | WH 調撥單 push 表身列的完整觸發鏈、冗餘 policy 分析與修正 | 修改 transferorder / dsvorder / dsvorderdetail 相關腳本 |
| [best-practices.md](references/best-practices.md) | 常見錯誤模式（✅/❌ 對比）、效能考量 | Code review 或撰寫新腳本 |

## 快速摘要

- **batchBeforeUpdate 無法被 ignorePolicy 跳過** — 這是最常被忽略的陷阱
- **batchPolicy INSERT 情境 oldRecords = undefined** — 邏輯中要明確處理
- **防循環用 userContent 旗標傳遞** — 不要用全域變數或其他機制
- **跨表觸發 policy 優先用 sentinel 欄位** — 例如 `updatedAtByTransferOrder: new Date()`
