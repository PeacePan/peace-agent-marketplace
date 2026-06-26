---
name: jira-overview
description: WonderPet Jira RD 專案的全貌參考。涵蓋 cloudId、projectKey、9 種卡片類型（任務 / 漏洞 / 故事 / 大型工作 / Optimization / Discussion / Meeting / Subtask / Test）、狀態流（待辦事項 → 已接受 → 進行中 → 審核中 → IN TESTING → 完成）、優先順序、各類型必填的自訂欄位（驗收條件 / 正確行為 / 使用者故事 / 規格 / 代碼庫名稱）、專案名稱 / 代碼庫名稱選單對應、常見標籤（HOTFIX / CRM）、分支命名慣例與常用 JQL。任何要透過 MCP 查 / 建 / 改 RD 卡片、要解讀某張卡片的欄位含義、要列出特定主題 / 版本 / 狀態的卡片、或要把需求開成正確類型卡片時，都應先讀此 skill。
---

# Jira RD 專案總覽

WonderPet 工程團隊唯一的研發任務看板。所有功能需求、bug、優化、討論卡片都收在這個 project，跨 NorwegianForest / Maltese / Ragdoll / Lykoi / Labrador / Tiffany / Utonagan / OldEnglish / QueenslandHeeler / IrishTerrier / Corgi / DevonRex 等子系統。

本 skill 的目的：讓你在使用 Jira MCP 前就知道**該查哪個欄位、該開哪個類型、該填什麼**，避免每次都要重新探勘 schema。

---

## 連線常數

```
cloudId    = f338306a-4b54-421e-9209-2e9f451c67f7
site       = wonderpet.atlassian.net
projectKey = RD
projectId  = 10001
```

呼叫 `mcp__claude_ai_Atlassian__*` 系列工具時，這三個值通常需要。若 MCP 報「cloudId not found」，再用 `getAccessibleAtlassianResources` 重新取得。

---

## 議題類型（Issue Types）

RD 專案實際在用的 9 種卡片類型。注意 **Subtask 已停用**（hierarchyLevel = -1，僅保留歷史卡片），新卡不要開。**Test** 是測試用佔位符，不要開。

| 類型 | id | hierarchy | 用途 | 預設優先序 |
|---|---|---|---|---|
| **大型工作** (Epic) | 10010 | 1 | 跨 Sprint 的功能集合，作為一群任務 / 故事的容器 | — |
| **故事** (Story) | 10006 | 0 | 從使用者視角描述的功能；強調「使用者故事」 | High |
| **任務** (Task) | 10007 | 0 | 一般技術工作 / 開發項目（最常用，~80%） | Medium |
| **漏洞** (Bug) | 10008 | 0 | 線上或測試環境的錯誤 | High |
| **Optimization** | 10039 | 0 | 技術優化 / 重構，需指定代碼庫並寫優化效益 | Medium |
| **Discussion** | 10038 | 0 | PM 想與工程師討論、但不佔用 refine 時間的議題 | High |
| **Meeting** | 10026 | 0 | 會議紀錄卡 | — |
| ~~Subtask~~ | 10011 | -1 | （已停用） | — |
| ~~Test~~ | 10023 | 0 | （測試用，勿開） | — |

### 如何選類型

- 「使用者要 / 我要做某個功能」→ **故事** 或 **任務**：使用者導向用故事，技術導向用任務
- 「某個畫面 / 流程出錯了」→ **漏洞**
- 「程式碼慢、結構亂、要重構」→ **Optimization**
- 「我想跟工程師討論一個方向」→ **Discussion**
- 「跨多張卡片的大功能」→ **大型工作**（Epic），底下掛任務 / 故事 / 漏洞

---

## 狀態流（Workflow）

```
待辦事項 ──→ 已接受 ──→ 進行中 ──→ 審核中 ──→ IN TESTING ──→ 完成
   │                                                              ▲
   └────────────────→ 已取消 ────────────────────────────────────┘
```

| 狀態 | category | 意義 |
|---|---|---|
| 待辦事項 | To Do | 已建立，尚未排入 sprint 或尚未認領 |
| 已接受 | In Progress | 工程師認領、已開始評估 / 設計，但還沒動手寫 |
| 進行中 | In Progress | 正在實作 |
| 審核中 | In Progress | PR 開出來等 review |
| IN TESTING | In Progress | 合併到 staging，QA 驗收中 |
| 完成 | Done | 上線完成 |
| 已取消 | Done | 不做了（不會抓進 release notes） |

JQL 注意：status 名稱要用中文且加引號 — `status = "進行中"`、`status in ("IN TESTING", "審核中")`。

---

## 優先順序

由高到低：**Urgent / Highest / High / Medium / Low / Lowest**。

預設值依類型不同：
- Story / Bug / Discussion → **High**
- Task / Optimization → **Medium**

JQL 用英文：`priority = "Urgent"`、`priority in ("Highest", "High")`。

---

## 自訂欄位完整對照表

所有 RD 專案會用到的 `customfield_*`。標 ⚠️ 的是該類型 **建卡時必填**。

### 通用欄位（多數類型共有）

| Field ID | 名稱 | 型別 | 說明 |
|---|---|---|---|
| customfield_10016 | **Story point estimate** | number | 估點，sprint planning 用 |
| customfield_10019 | Rank | lexorank | 看板排序，系統自動處理 |
| customfield_10020 | **Sprint** | array | 所屬 sprint |
| customfield_10021 | Flagged | option | `Impediment` 標記受阻 |
| customfield_10030 | **驗收條件** | textarea | 該卡的 Acceptance Criteria |
| customfield_10031 | **驗收者** | user[] | 誰負責驗收（多人） |
| customfield_10033 | **分支名稱** | text | 對應的 git branch 名稱 |
| customfield_10067 | **專案名稱** | option | 大主題分類，見下方選單 |
| customfield_10100 | Design | design | Figma / 設計檔連結 |
| customfield_10103 | Vulnerability | any | 安全性議題追蹤 |
| customfield_10112 | **初始估點（參考用）** | number | 第一次估點，便於回溯估點偏差 |
| customfield_10266 | 討論紀錄 | textarea | refine / 討論留底 |
| customfield_10728 | Atlassian Project | atlas-project | Atlas Project 連結 |

### 各類型特有的必填欄位

| 類型 | 必填自訂欄位 | 用途 |
|---|---|---|
| **故事** (Story) | ⚠️ customfield_10060 **使用者故事**<br>⚠️ customfield_10030 **驗收條件**<br>customfield_10061 規格<br>customfield_10062 參考資料 | 「身為 X，我希望 Y，以達 Z」格式 |
| **任務** (Task) | ⚠️ customfield_10057 **規格**<br>⚠️ customfield_10030 **驗收條件**<br>customfield_10058 參考資料 | 技術規格，要可被驗收 |
| **漏洞** (Bug) | ⚠️ customfield_10059 **正確行為**<br>⚠️ customfield_10030 **驗收條件**<br>customfield_10038 **上線版本** | 預期的正確行為 + 修正版本號 |
| **Optimization** | ⚠️ customfield_10066 **代碼庫名稱**<br>⚠️ customfield_10061 **規格**<br>customfield_10106 優化效益 | 必須指定哪個 repo，並寫清楚效益 |
| **Discussion** | ⚠️ customfield_10030 **驗收條件**<br>customfield_10064 處理項目（含預設模板）<br>customfield_10058 參考資料 | 討論卡有預設「討論議題 / 原因 / 目前的想法」三段式 description |
| **大型工作** (Epic) | — | 僅需 summary + description |

---

## 「專案名稱」選單（customfield_10067）

這是跨類型共用的 **主題分類**，用來把分散在不同 sprint 的卡片串成一個大專案敘事。建卡時若屬於下列任一主題，請務必選擇：

| 值 | 顏色 | 主題 |
|---|---|---|
| SCM | — | 供應鏈管理 |
| SCM_長期回饋金 | — | 長期回饋金子題 |
| Emarsys | — | Emarsys CRM 同步 |
| POS 查詢優化 | — | POS 查詢效能優化 |
| DSV | GREEN | DSV 倉庫出貨整合 |
| 財務 | TEAL | 財務模組 |
| 財務報表拋轉 | — | 拋轉 NetSuite / ERP |
| 小白單優惠券 | — | 結帳後紙本優惠券 |
| 分批取 | — | 客訂分批取貨 |
| 客訂服務流程 | — | 客訂單服務流程 |
| 大智通 | — | 大智通 EDI |
| 定價綁折 | — | 定價綁定折扣 |
| APP | GREY_DARKER | APP 相關 |
| 贊助金 | GREY_DARKEST | 贊助金功能 |
| 新版結帳 | YELLOW_DARKER | POS 新版結帳改造 |

JQL：`"專案名稱" = "新版結帳"` 或 `cf[10067] = "DSV"`。

---

## 「代碼庫名稱」選單（customfield_10066，Optimization 必填）

對應到 monorepo `petpetgo/` 底下的子專案資料夾：

| 值 | 對應 repo / 模組 | 性質 |
|---|---|---|
| Maltese | maltese | POS Web App（門市使用的 React 前端） |
| Lykoi | lykoi | 資料中台 UI |
| JavaCat | javacat | 後端框架 / GraphQL client |
| NorCat | norwegianforest | 資料中台後端表格與腳本（簡稱 NorCat） |
| DevOps | devops | CI/CD、infra |
| Corgi | corgi | （請查 wiki） |
| DevonRex | devonrex | （請查 wiki） |
| OldEnglish | oldenglish | POSAgent 硬體代理 |
| IrishTerrier | irishterrier | NetSuite RESTlet 整合 |
| QueenslandHeeler | queenslandheeler | 盤點機 App |

更完整的 repo 對應請參考 `peace-wp-llm-wiki/wiki/index.md`。

---

## 常見標籤（labels）

`labels` 是 free-form，常見值：

- **HOTFIX** — 線上緊急修正，會走 hotfix 分支 + 加速 release 流程
- **HOTFIX-STAGING** — Staging 環境 hotfix
- **CRM** / **crm** — Emarsys / 會員 CRM 相關（注意大小寫沒一致，JQL 用 `labels in (CRM, crm)` 較保險）
- **新版結帳** — POS 新版結帳專案（也可用 customfield_10067 = "新版結帳"，labels 是輔助）
- **版更staging** — 已部署 staging、等版更
- **正式站驗收** — 已上正式站等驗收

---

## 分支命名慣例（customfield_10033）

從卡片實際資料觀察：

```
RD-<卡號>-<類型>/<代碼庫>/<簡短描述>
```

類型常見：
- `feat` / `feature` — 新功能
- `fix` — 一般修正
- `hotfix` — 線上 hotfix
- `docs` / `refactor` / `chore` — 同 conventional commits

代碼庫前綴用小寫，例：
- `RD-7487-feature/ragdoll/feversocial-qrcode-coupon`
- `RD-7622-hotfix/ragdoll/offline-sale-promotion-name-residue`
- `RD-7644-hotfix/norwegianforest/resync-failed-orders-to-wds`
- `RD-7563-feat/labrador/crm-pospet-push`

**Discussion 卡的分支預設 `Master`**（不會真的開分支，僅佔位）。

---

## 常用 JQL 範例

```jql
# 我認領的、還沒做完的卡
assignee = currentUser() AND statusCategory != Done ORDER BY priority DESC

# 某個 sprint 的所有卡（用 sprint id）
sprint = 123 AND project = RD

# 進行中或審核中的卡，依優先序
project = RD AND status in ("進行中", "審核中") ORDER BY priority DESC, updated DESC

# 找某個版本上線的所有卡
project = RD AND "上線版本" ~ "v2.85.0"

# 找某個主題的所有卡（含已完成）
project = RD AND "專案名稱" = "新版結帳" ORDER BY status, updated DESC

# 找所有 HOTFIX
project = RD AND labels = HOTFIX ORDER BY created DESC

# 找特定代碼庫的 Optimization 卡
project = RD AND issuetype = Optimization AND "代碼庫名稱" = "NorCat"

# 找最近一週新建的 Bug
project = RD AND issuetype = "漏洞" AND created >= -7d

# 我要驗收的卡（驗收者欄位）
"驗收者" = currentUser() AND status = "IN TESTING"
```

JQL 注意：
- **中文 status / 中文 issuetype 要加引號**：`status = "進行中"`、`issuetype = "漏洞"`
- 自訂欄位用 **名稱（中文）加引號**：`"專案名稱" = "DSV"`、`"代碼庫名稱" = "Maltese"`、`"上線版本" ~ "..."`
- 或用 `cf[fieldId]`：`cf[10067] = "DSV"`、`cf[10038] ~ "v2.85"`
- 文字欄位用 `~`（包含）而非 `=`：`"上線版本" ~ "v2"`

---

## 用 MCP 查 / 建卡片時的最小欄位集

### 查卡片：`searchJiraIssuesUsingJql` 推薦 fields

預設 fields（`summary, status, issuetype, priority, labels, ...`）已涵蓋多數情境。需要 RD 專案特定資訊時，明確加上：

```json
[
  "summary", "status", "issuetype", "priority", "labels", "assignee",
  "customfield_10016",  // Story point
  "customfield_10020",  // Sprint
  "customfield_10030",  // 驗收條件
  "customfield_10031",  // 驗收者
  "customfield_10033",  // 分支名稱
  "customfield_10038",  // 上線版本 (Bug)
  "customfield_10057",  // 規格 (Task)
  "customfield_10060",  // 使用者故事 (Story)
  "customfield_10061",  // 規格 (Story/Optimization)
  "customfield_10066",  // 代碼庫名稱 (Optimization)
  "customfield_10067",  // 專案名稱
  "customfield_10112"   // 初始估點
]
```

需要看 description 與 comments 時加 `"description", "comment"`。

要看「所有欄位」用 `["*all"]`，但回傳量很大，會被截斷到檔案。

### 建卡片：必填 + 推薦欄位

建立任何卡都需要：`project = RD` + `issuetype` + `summary`。

依類型補上必填自訂欄位（見上方對照表）。建議再加：
- `priority` — 不填會用該類型預設值
- `customfield_10067` 專案名稱 — 若屬於某主題
- `labels` — HOTFIX / CRM 等
- `customfield_10112` 初始估點 — 留估點歷史

---

## 與 wiki / 其他 skill 的關係

- 業務邏輯與 repo 細節 → `peace-wp-llm-wiki` skill（NorwegianForest / Ragdoll / Maltese / Labrador 等）
- POS Sentry 錯誤要開 RD 卡 → `pos-sentry-triage` / `maltese-sentry-triage` skill（含完整 epic id、必填欄位、踩雷）
- 開 PR 並回填卡片 → `github-update-pr-summary` skill

本 skill 只負責 **Jira 本身的結構知識**；業務面要求請走對應的領域 skill。

---

## 維護注意

- 自訂欄位 id 一旦發佈後極少變動，但 **新欄位 / 新選項** 會持續加。發現 schema 與本文件不符時，用 `getJiraIssueTypeMetaWithFields` 重新確認後更新本檔。
- `customfield_10067` 專案名稱選單會隨新專案上線而擴充，需要新主題時請 PM 在 Jira admin 新增選項，再回頭更新此檔。
- 「代碼庫名稱」與真實 monorepo 子目錄的對應若有新增，同步更新此檔以及 `peace-wp-llm-wiki/wiki/index.md`。
