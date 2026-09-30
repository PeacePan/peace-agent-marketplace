---
name: ragdoll-user-manual
description: 用於回答 Ragdoll POS 系統終端使用者的操作問題，並作為實機驗收時判斷「正確操作方式」的依據。涵蓋 checkout（一般/美容結帳合一入口）、summary（結帳摘要／付款確認）、salon-summary（美容結帳摘要／美容付款確認）、customer-display（顧客顯示螢幕）、print-preview（列印預覽）等各入口的 UI 流程說明。
---

# Ragdoll POS 使用手冊

## 系統概覽

Ragdoll 是寵物店 POS 系統的下一代版本（Next.js + Electron），實際路由如下
（依 `next/app` 目錄下的 `page.tsx` 實查得出）：

| 入口 | 路由 | 涵蓋狀態 |
|------|------|---------|
| 首頁 | `/` | ✅ 已撰寫（極簡導航頁；runtime 驗證缺口詳見 `entries/home/AGENT.md`——撰寫當下 dev 環境未啟動，全文僅依原始碼撰寫） |
| 結帳 | `/checkout` | ✅ 已撰寫主線 + 功能選單，其餘（美容模式、促銷/退貨/換購/外送/報表/暫結等）待補 |
| 美容結帳摘要 | `/salon-summary` | ✅ 已撰寫（重用 `/summary` 的付款元件，本章記錄美容專屬畫面與差異；2026-09-30 已 runtime 驗證進入流程、付款頁佈局與金額分項、外送停用、返回；**完成結帳、刷卡、宜睿停用提示、帶入未付款單仍僅依原始碼**，詳見 `entries/salon-summary/AGENT.md`） |
| 顧客顯示螢幕 | `/customer-display` | ✅ 已撰寫（runtime 驗證缺口詳見 `entries/customer-display/AGENT.md`——撰寫當下 dev 環境未啟動，全文僅依原始碼撰寫） |
| 結帳摘要 | `/summary` | ✅ 已撰寫（2026-09-30 已於 dev 視窗 runtime 驗證現金付款、完成結帳等主線；刷卡機、One 碼、宜睿等需外部設備的分支僅依原始碼，詳見 `entries/summary/AGENT.md`） |
| 列印預覽 | `/print-preview` | ✅ 已撰寫（runtime 驗證缺口詳見 `entries/print-preview/AGENT.md`） |

**注意**：`sidemenu`（`next/app/sidemenu/`）不是獨立路由，底下沒有 `page.tsx`；
`pos-menu-drawer` 是渲染在 `/checkout` 內的功能選單抽屜，其操作說明收在
`entries/checkout/` 底下，不是獨立入口。

## 結帳入口（`/checkout`）

- Agent 指引：`entries/checkout/AGENT.md`
- 操作流程索引：見 `entries/checkout/AGENT.md` 的「業務流程索引」表格

## 首頁（`/`）

- Agent 指引：`entries/home/AGENT.md`

## 結帳摘要／付款確認（`/summary`）

- Agent 指引：`entries/summary/AGENT.md`
- 操作流程索引：見 `entries/summary/AGENT.md` 的「業務流程索引」表格

## 美容結帳摘要／美容付款確認（`/salon-summary`）

- Agent 指引：`entries/salon-summary/AGENT.md`（付款區與 `/summary` 共用，先讀 `entries/summary/`）
- 操作流程索引：見 `entries/salon-summary/AGENT.md` 的「業務流程索引」表格

## 客顯二顯螢幕（`/customer-display`）

- Agent 指引：`entries/customer-display/AGENT.md`

## 列印預覽（`/print-preview`）

- Agent 指引：`entries/print-preview/AGENT.md`

## 待補範圍

以下尚未撰寫操作手冊，驗收流程遇到涉及這些範圍的驗收條件時，應標記「⚠️ 無法
驗證（手冊尚未涵蓋此範圍）」，不可憑空猜測操作方式。後續有驗收需求時，比照
`entries/checkout/` 的撰寫方式（先實查對應 `next/app/<入口>` 的真實檔案清單，
交叉比對 `test/e2e/pages/` 的對應 Page Object，可行時用 `ragdoll-electron` 工具
做 runtime 驗證）逐步補齊：

- `/checkout` 的其餘範圍（美容模式、促銷、退貨、換購、外送匯入、報表、暫結等，
  各自是獨立的對話框子系統，`next/app/checkout/components/` 底下有 20 幾個；
  其中「促銷結算對話框」是進入 `/summary` 的前一站，「美容促銷結算對話框」是進入
  `/salon-summary` 的前一站，兩者的內部操作仍待補，付款頁章節只記錄到「確認結帳」按下後）

## 與 `ragdoll-project-knowledge` 的分工

本手冊只記錄「操作路徑與畫面」，業務規則/限制的權威來源是同專案的
`ragdoll-project-knowledge` skill（`Ragdoll/.claude/skills/ragdoll-project-knowledge/`），
本手冊不重複維護規則細節。
