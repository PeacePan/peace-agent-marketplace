---
name: ragdoll-user-manual
description: 用於回答 Ragdoll POS 系統終端使用者的操作問題，並作為實機驗收時判斷「正確操作方式」的依據。涵蓋 checkout（一般/美容結帳合一入口）等各入口的 UI 流程說明。
---

# Ragdoll POS 使用手冊

## 系統概覽

Ragdoll 是寵物店 POS 系統的下一代版本（Next.js + Electron），實際路由如下
（依 `next/app` 目錄下的 `page.tsx` 實查得出）：

| 入口 | 路由 | 涵蓋狀態 |
|------|------|---------|
| 開機/機台選擇 | `/` | 待補（本次僅在 checkout 手冊內簡述如何從這裡進入 `/checkout`） |
| 結帳 | `/checkout` | ✅ 本次已撰寫主線 + 功能選單，其餘（美容模式、促銷/退貨/換購/外送/報表/暫結等）待補 |
| 美容結帳摘要 | `/salon-summary` | 待補 |
| 顧客顯示螢幕 | `/customer-display` | 待補 |
| 結帳摘要 | `/summary` | 待補 |
| 列印預覽 | `/print-preview` | 待補 |

**注意**：`sidemenu`（`next/app/sidemenu/`）不是獨立路由，底下沒有 `page.tsx`；
`pos-menu-drawer` 是渲染在 `/checkout` 內的功能選單抽屜，其操作說明收在
`entries/checkout/` 底下，不是獨立入口。

## 結帳入口（`/checkout`）

- Agent 指引：`entries/checkout/AGENT.md`
- 操作流程索引：見 `entries/checkout/AGENT.md` 的「業務流程索引」表格

## 待補範圍

以下尚未撰寫操作手冊，驗收流程遇到涉及這些範圍的驗收條件時，應標記「⚠️ 無法
驗證（手冊尚未涵蓋此範圍）」，不可憑空猜測操作方式。後續有驗收需求時，比照
`entries/checkout/` 的撰寫方式（先實查對應 `next/app/<入口>` 的真實檔案清單，
交叉比對 `test/e2e/pages/` 的對應 Page Object，可行時用 `ragdoll-electron` 工具
做 runtime 驗證）逐步補齊：

- `/`（開機/機台選擇）
- `/checkout` 的其餘範圍（美容模式、促銷、退貨、換購、外送匯入、報表、暫結等）
- `/salon-summary`、`/customer-display`、`/summary`、`/print-preview`

## 與 `ragdoll-project-knowledge` 的分工

本手冊只記錄「操作路徑與畫面」，業務規則/限制的權威來源是同專案的
`ragdoll-project-knowledge` skill（`Ragdoll/.claude/skills/ragdoll-project-knowledge/`），
本手冊不重複維護規則細節。
