# Ragdoll Workflow Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 ragdoll-develop-workflow 重構為 gigaai 六階段（Define → Plan → Build/Verify → Review → Ship）結構，並同步更新 code-review-principles 補齊架構與可讀性兩個維度。

**Architecture:** 兩個 SKILL.md 檔案分別修改，互相獨立。Task 1 先更新 code-review-principles，Task 2 再重寫 ragdoll-develop-workflow（因後者在 REVIEW 階段明確引用前者）。

**Tech Stack:** Markdown skill files, git

---

## File Structure

| 動作 | 檔案路徑 |
|---|---|
| Modify | `plugins/wonderpet-general/skills/code-review-principles/SKILL.md` |
| Rewrite | `plugins/ragdoll-workspace/skills/ragdoll-develop-workflow/SKILL.md` |

---

### Task 1：更新 code-review-principles — 新增架構與可讀性維度

**Files:**
- Modify: `plugins/wonderpet-general/skills/code-review-principles/SKILL.md`

- [ ] **Step 1：確認目前 code-review-principles 的現有維度**

  讀取檔案並確認目前有 8 個維度（資料完整性、型別安全、安全性、效能、Breaking Change、測試覆蓋、第三方依賴、程式碼品質），且缺少「架構」與「可讀性」兩個明確維度。

  ```bash
  grep "^### " plugins/wonderpet-general/skills/code-review-principles/SKILL.md
  ```

  預期輸出：
  ```
  ### 1. 資料完整性（最高優先）
  ### 2. 型別安全
  ### 3. 安全性
  ### 4. 效能
  ### 5. Breaking Change 偵測
  ### 6. 測試覆蓋
  ### 7. 第三方依賴
  ### 8. 程式碼品質
  ```

- [ ] **Step 2：在「型別安全」之後插入「架構」維度**

  在 `### 2. 型別安全` 區塊結束後、`### 3. 安全性` 之前，插入以下內容：

  ```markdown
  ### 3. 架構

  - [ ] **模組邊界清晰**：每個模組/檔案是否只做一件事？對外介面是否最小化，不暴露內部細節？
  - [ ] **依賴方向正確**：是否存在循環依賴？依賴是否只往單一方向流動（例如 UI → Store → Service）？
  - [ ] **抽象層次一致**：同一層的程式碼是否在相同的抽象層次上操作？是否有層次跳躍（UI 直接操作 DB）？
  - [ ] **封裝完整**：內部實作細節是否正確隱藏？消費端是否被迫知道不應知道的細節？
  - [ ] **過度設計檢查**：新增的抽象、中間層、介面是否有明確存在理由？是否存在 YAGNI 違反？
  ```

  原本的 `### 3. 安全性` 至 `### 8. 程式碼品質` 的編號依序往後遞增為 4–9。

- [ ] **Step 3：在「程式碼品質」區塊前插入「可讀性」維度**

  在新編號的 `### 9. 程式碼品質` 之前，插入以下內容：

  ```markdown
  ### 8. 可讀性

  - [ ] **命名表達意圖**：函式、變數、型別的命名是否清楚表達其目的，不需要讀內容才能理解？
  - [ ] **函式長度合理**：單一函式是否可以不捲動螢幕閱讀完？複雜邏輯是否有適當的分割？
  - [ ] **巢狀層次適當**：是否存在深度超過 3 層的條件巢狀？可否以 early return 或分割函式改善？
  - [ ] **相同概念一致命名**：相同的業務概念在不同檔案中是否使用相同名稱？
  - [ ] **非直覺決策有說明**：設計限制、特殊處理、workaround 是否有說明「為什麼」而非「做了什麼」？
  ```

- [ ] **Step 4：更新 description frontmatter**

  將 frontmatter 的 `description` 更新為：

  ```yaml
  description: PR Code Review 原則與檢查清單。當需要審查 Pull Request、進行程式碼審查、或評估大型重構的品質與風險時使用。涵蓋正確性（資料完整性、Breaking Change、測試覆蓋）、可讀性、架構、安全性、效能、型別安全、第三方依賴等面向，對應 gigaai 五維審查標準。
  ```

- [ ] **Step 5：驗證最終維度清單**

  ```bash
  grep "^### " plugins/wonderpet-general/skills/code-review-principles/SKILL.md
  ```

  預期輸出（共 10 個維度，含 2 個新增）：
  ```
  ### 1. 資料完整性（最高優先）
  ### 2. 型別安全
  ### 3. 架構
  ### 4. 安全性
  ### 5. 效能
  ### 6. Breaking Change 偵測
  ### 7. 測試覆蓋
  ### 8. 可讀性
  ### 9. 第三方依賴
  ### 10. 程式碼品質
  ```

- [ ] **Step 6：Commit**

  ```bash
  cd /Users/peacepan/workspace/peace-agent-marketplace
  git add plugins/wonderpet-general/skills/code-review-principles/SKILL.md
  git commit -m "feat(code-review-principles): 新增架構與可讀性兩個審查維度，對應 gigaai 五維標準"
  ```

---

### Task 2：重寫 ragdoll-develop-workflow — gigaai 六階段結構

**Files:**
- Rewrite: `plugins/ragdoll-workspace/skills/ragdoll-develop-workflow/SKILL.md`

- [ ] **Step 1：備份現有檔案內容（確認變更前後差異）**

  ```bash
  wc -l plugins/ragdoll-workspace/skills/ragdoll-develop-workflow/SKILL.md
  ```

  預期：現有檔案約 275 行（含 Mermaid flowchart 與 Step 1–7 流程）。

- [ ] **Step 2：完整覆寫 SKILL.md 為六階段結構**

  以下為完整新內容，覆寫整個檔案：

  ````markdown
  ---
  name: ragdoll-develop-workflow
  description: 定義 Ragdoll 專案的六階段開發工作流程（Define → Plan → Build/Verify → Review → Ship），確保從需求定義到交付的每個階段都有對應的 agent、三層測試策略與品質把關。
  ---

  # Ragdoll 開發工作流程

  ## 禁止使用的技能

  以下技能與本工作流程衝突，**MUST NOT** 呼叫：

  - `superpowers:subagent-driven-development`（本流程自帶 Subagent 發派）
  - `superpowers:executing-plans`（同上）

  本流程使用 `superpowers:brainstorming` 做需求蒐集，再使用 `superpowers:writing-plans` 擬定 Plan，Plan 完成後控制權回歸本流程的 [PLAN] 階段。

  ---

  ## 環境前置檢查（每次開始工作前必做）

  在進行任何 git / gh 操作前，必須先確認以下工具可用：

  ```bash
  source ~/.bashrc
  git --version
  gh --version
  ```

  - 若 `git` 不可用：請使用者安裝 Git 並重新開啟終端機後再繼續。
  - 若 `gh` 不可用：請使用者安裝 GitHub CLI 並執行 `gh auth login` 完成身分驗證後再繼續。

  **工具未就緒時，不要嘗試自行修復 PATH 或繞過問題，直接告知使用者完成安裝與驗證後再回來。**

  若 `git commit` 出現 `_/husky.sh: No such file or directory`，執行：

  ```bash
  cd .. && npx husky install
  ```

  然後重新 commit。

  ---

  ## 流程概覽

  ```
  [DEFINE]         需求 → Brainstorming（可選）→ Plan + 三層 Test Cases → plan-challenger
  [PLAN]           Task 切分（含並行標注）+ HARD GATE
  [BUILD ↔ VERIFY] RD → QA（unit+integration）→ commit → validator  × N Tasks
  [REVIEW]         Code Review（五維）→ E2E QA（UI 改動時）
  [SHIP]           Knowledge Manager → PR 完善 → PR 描述更新 → label done → Chat
  ```

  ---

  ## [DEFINE] 需求定義

  ### Step 1 — 接收需求

  收到需求後，**MUST** 先詢問使用者：

  > 「需求已收到。請選擇下一步：
  > 1. Brainstorming — 先討論實作細節與不確定點，再進入 Plan 撰寫
  > 2. 直接寫 Plan — 跳過 brainstorming，直接進入 Plan 撰寫」

  - 選 1 → 呼叫 `superpowers:brainstorming`，完成後進入 Step 2
  - 選 2 → 直接進入 Step 2

  > 注意：即使規格看起來完整（含 Jira ticket、驗收條件、功能描述），仍可能存在實作決策需要討論。**不得自行判斷跳過，必須詢問使用者。**

  ### Step 2 — 擬定 Plan + 三層 Test Cases

  呼叫 `superpowers:writing-plans` 產出 Plan。writing-plans 完成後，orchestrator 根據 Plan 內容補充定義三層 test cases（不依賴 writing-plans 修改其輸出格式）。最終產出格式：

  ```
  ## Plan

  ### Task 1：{描述}
  - 負責層：Electron / Next.js / 兩者
  - Unit Tests：
    - [ ] {函式/元件名稱}：{驗證什麼}
  - Integration Tests：
    - [ ] {跨哪些模組}：{驗證什麼互動}

  ### Task 2：...

  ## E2E Test Cases（整體流程，所有 Task 完成後才執行）
  - [ ] {完整使用者流程場景 1}
  - [ ] {完整使用者流程場景 2}
  ```

  三層分工原則：

  | 層級 | 寫的條件 | 不寫的條件 |
  |---|---|---|
  | Unit | 邏輯有分支、計算、轉換，可獨立驗證 | 純轉發、無邏輯的 passthrough |
  | Integration | 跨 Store / IPC / API 的互動，Unit 無法覆蓋 | Unit 已能完整驗證的範圍 |
  | E2E | 使用者可見的完整流程（每條流程只寫一個） | 內部模組細節，Integration 已覆蓋的 |

  ### Step 2.5 — HARD GATE：plan-challenger 審查

  將 Plan + 三層 Test Cases 一起交給 `ragdoll-workspace:ragdoll-plan-challenger`：

  - **通過** → 進入 [PLAN] 階段
  - **不通過** → 回 Step 2 修正，重新提交審查

  ---

  ## [PLAN] 任務規劃

  ### Step 3 — 切分 Task

  根據 Plan 切分為多個 Task，每個 Task 的標準格式：

  ```
  Task N：{描述}  [可與 Task M 並行 / 需等待 Task X 完成]
    負責 Agent：
      - ragdoll-electron-rd（Instance A，若並行）
      - ragdoll-next-rd
    修改範圍：{涉及的檔案或模組，供並行衝突判斷}
    Unit Tests：
      - [ ] {函式/元件}：{驗證什麼}
    Integration Tests：
      - [ ] {跨哪些模組}：{驗證什麼}
  ```

  > 同一 agent 類型可同時發派多個實例，前提是各實例的修改範圍無檔案交集。

  **HARD GATE — Task 完整性檢核**

  每個 Task 進入 [BUILD] 前，**MUST** 確認：

  | 檢查項目 | 說明 |
  |---|---|
  | 有明確的負責 Agent | 至少指定一個 RD subagent |
  | 有 Unit 或 Integration test cases | 兩者至少一項；若都沒有，必須說明理由 |
  | Task 範圍可在單一 session 完成 | 過大的 Task 必須進一步切分 |
  | 每個 Task 對應到 Spec 至少一個驗收條件 | 不得有無對應需求的 Task |
  | 並行標注安全 | 並行的 Task 修改範圍無檔案交集 |

  **MUST** 從 Step 3 開始到所有 Task 完成前，不再與使用者互動，全程自主執行。

  ---

  ## [BUILD ↔ VERIFY] 實作與驗收

  每個 Task（或並行批次）依序執行以下步驟。

  ### Step 4 — Git 初始化（第一個 Task 才執行）

  若使用者尚未提供 Jira Ticket 編號，**MUST** 詢問後再繼續。

  ```bash
  source ~/.bashrc && git --version && gh --version

  git checkout -b RD-{ticket}-feature/ragdoll/{描述}
  gh pr create --title "[Ragdoll][RD-{ticket}] {簡短描述}"
  gh pr edit --add-label "working"
  ```

  ### Step 5 — 發派 RD Subagent

  | 情境 | 做法 |
  |---|---|
  | Task 涉及 Electron 層 | 發派 `ragdoll-workspace:ragdoll-electron-rd` |
  | Task 涉及 Next.js 層 | 發派 `ragdoll-workspace:ragdoll-next-rd` |
  | 兩層都涉及 | 同時發派兩個 |
  | 多個可並行 Task | 同一則訊息發派多個 Agent 實例 |

  發派時 **MUST** 提供：
  - Task 描述與修改範圍
  - 對應的 Unit / Integration test cases
  - 相關 Spec / Plan 段落

  **MUST NOT** 使用 general-purpose agent 執行 RD 任務。

  ### Step 6 — QA 驗收（unit + integration）

  | RD | QA |
  |---|---|
  | `ragdoll-workspace:ragdoll-electron-rd` | `ragdoll-workspace:ragdoll-electron-qa` |
  | `ragdoll-workspace:ragdoll-next-rd` | `ragdoll-workspace:ragdoll-next-qa` |

  若 Task 同時涉及兩層，兩個 QA subagent 可並行發派。

  **QA 失敗的處理：**
  1. QA 回報詳細錯誤訊息與失敗原因
  2. 將錯誤資訊轉交對應 RD subagent 修正
  3. 直接重發 QA subagent 驗證（**不需重走 Step 5**）
  4. 重複直到全部通過

  **QA 全部通過後才可進入 Step 7。**

  ### Step 7 — Commit + Validator

  ```bash
  git add <相關檔案>
  git commit -m "[Ragdoll] {清楚描述此 Task 的變更}"
  git push
  ```

  前景執行 `ragdoll-workspace:ragdoll-validator`（傳入 PR 位址 + Jira Ticket 位址）：

  - **通過** → 繼續下一個 Task（回 Step 5）或進入 [REVIEW]
  - **不通過** → 轉交 RD 修正，修正後重走 Step 6 → Step 7

  ---

  ## [REVIEW] 審查

  所有 Task 完成後進入此階段。

  ### Step 8 — Code Review（五維把關）

  呼叫 `wonderpet-general:code-review-principles`：

  | 維度 | 檢查重點 |
  |---|---|
  | 正確性 | 邏輯正確、資料完整性、Breaking Change |
  | 可讀性 | 命名清晰、函式長度合理、非直覺決策有說明 |
  | 架構 | 模組邊界清晰、依賴方向正確、無過度設計 |
  | 安全 | 注入防護、敏感資料、權限邊界 |
  | 效能 | N+1、索引、記憶體、全量掃描 |

  | 風險等級 | 處理方式 |
  |---|---|
  | 高風險（資料遺失、安全漏洞、production 崩潰） | **MUST** 回對應 Task 的 [BUILD ↔ VERIFY] 修正，修正後重回 Step 8 |
  | 中風險 | 記錄於 PR comment，由使用者決定是否修正 |
  | 低風險 | 列入改善建議，不阻擋進入 [SHIP] |

  ### Step 9 — E2E QA（有 UI 改動時）

  發派 `ragdoll-workspace:ragdoll-e2e-qa`，執行 [DEFINE] 階段定義的 E2E test cases。

  - **通過** → 進入 [SHIP]
  - **失敗** → 定位失敗的 Task，轉交對應 RD 修正，修正後重走 [BUILD ↔ VERIFY] 該 Task，再回 Step 9

  若需求**不含 UI 改動** → 跳過此步，直接進入 [SHIP]。

  ---

  ## [SHIP] 交付

  ### Step 10 — Knowledge Manager（整體文件歸檔）

  前景等待 `ragdoll-workspace:ragdoll-knowledge-manager` 完成整體知識庫更新。

  發派時提供：
  - 所有 Task 的變更摘要
  - 完整修改檔案清單（`git diff main...HEAD --name-only`）
  - 完整 Spec / Plan 內容

  完成後 commit：

  ```bash
  git add <知識庫文件>
  git commit -m "[Ragdoll] docs: 更新知識庫文件"
  git push
  ```

  ### Step 11 — PR 完善

  呼叫 `wonderpet-general:github-create-pr-steps`，帶入 Ragdoll 專案參數：

  | 參數 | 值 |
  |---|---|
  | 分支命名規則 | `RD-{ticket}-feature/ragdoll/{30字以內描述}` |
  | PR 標題格式 | `[Ragdoll][RD-{ticket}] {簡短描述}` |
  | E2E QA Subagent | `ragdoll-workspace:ragdoll-e2e-qa` |
  | Code Review 失敗回報對象 | `ragdoll-workspace:ragdoll-electron-rd`、`ragdoll-workspace:ragdoll-next-rd` |
  | Google Chat 摘要標題 | `【Ragdoll 開發摘要】` |

  ### Step 12 — 更新 PR 描述

  呼叫 `wonderpet-general:github-update-pr-summary`：

  1. 偵測 PR 是否含 NorwegianForest 資料夾變更 → 選對應範本
  2. 從分支名稱解析 ticket 編號
  3. 填入實作摘要後更新 PR body

  ### Step 13 — 完成通知

  ```bash
  gh pr edit --remove-label "working" --add-label "done"
  ```

  發送 Google Chat 摘要，標題：`【Ragdoll 開發摘要】`，內容包含：
  - 本次實作的功能說明
  - Task 清單與完成狀態
  - PR 連結
  - Jira Ticket 連結

  ---

  ## Subagent 對照表

  | Subagent | 角色 | 技術範疇 |
  |---|---|---|
  | `ragdoll-workspace:ragdoll-electron-rd` | Electron 開發 | SQLite、IPC、Node.js 後端 |
  | `ragdoll-workspace:ragdoll-next-rd` | Next.js 開發 | 前端 UI、Store、API 串接 |
  | `ragdoll-workspace:ragdoll-e2e-qa` | E2E 測試 | Playwright、結帳流程測試 |
  | `ragdoll-workspace:ragdoll-electron-qa` | Electron 測試 | Electron 層功能驗證 |
  | `ragdoll-workspace:ragdoll-next-qa` | Next.js 測試 | Next.js 層功能驗證 |
  | `ragdoll-workspace:ragdoll-validator` | 需求驗證 | 比對 PR 代碼變更與 Jira Ticket 驗收標準 |
  | `ragdoll-workspace:ragdoll-knowledge-manager` | 知識庫歸檔 | 更新專案知識庫文件（SHIP 階段整體執行） |
  | `ragdoll-workspace:ragdoll-plan-challenger` | Plan 審查 | 評估 Spec 與 Plan 可行性 |

  ---

  ## 分支命名規則

  ```
  RD-{jira-ticket}-feature/ragdoll/{30個字以內的描述}
  ```

  - `{jira-ticket}`: Jira Ticket 編號（若使用者未提供，必須詢問）
  - `{描述}`: 以連字號分隔的英文短描述，30 字以內

  **範例：**
  - `RD-6857-feature/ragdoll/checkout-e2e-testing`
  - `RD-1234-feature/ragdoll/discount-calculator-fix`
  ````

- [ ] **Step 3：驗證六個階段標題都存在**

  ```bash
  grep "^## \[" plugins/ragdoll-workspace/skills/ragdoll-develop-workflow/SKILL.md
  ```

  預期輸出：
  ```
  ## [DEFINE] 需求定義
  ## [PLAN] 任務規劃
  ## [BUILD ↔ VERIFY] 實作與驗收
  ## [REVIEW] 審查
  ## [SHIP] 交付
  ```

- [ ] **Step 4：驗證禁止技能清單存在**

  ```bash
  grep "MUST NOT" plugins/ragdoll-workspace/skills/ragdoll-develop-workflow/SKILL.md
  ```

  預期：至少出現 2 行（subagent-driven-development、executing-plans）。

- [ ] **Step 5：Commit**

  ```bash
  cd /Users/peacepan/workspace/peace-agent-marketplace
  git add plugins/ragdoll-workspace/skills/ragdoll-develop-workflow/SKILL.md
  git commit -m "feat(ragdoll-develop-workflow): 重構為 gigaai 六階段結構，新增三層測試、並行 Task、PR 描述更新"
  ```

---

## Self-Review

**Spec coverage 檢查：**

| Spec 需求 | 對應 Task |
|---|---|
| TDD — Plan 階段定義 test cases | Task 2 Step 2（三層 test cases 格式） |
| 三層測試分工（Unit / Integration / E2E） | Task 2 Step 2（分工原則表格） |
| plan-challenger 審查 Plan + test cases | Task 2 Step 2.5 |
| 並行 Task 標注（含檔案交集判斷） | Task 2 Step 3 |
| Code Review 五維（新增架構、可讀性） | Task 1（code-review-principles 更新） |
| Code Review 先於 E2E | Task 2 Step 8 → Step 9 順序 |
| Knowledge Manager 移至 SHIP | Task 2 Step 10 |
| github-update-pr-summary 整合 | Task 2 Step 12 |
| 禁止技能清單 | Task 2 Step 2（禁止區塊） |

**Placeholder 掃描：** 無 TBD / TODO。Task 2 Step 2 的完整 SKILL.md 內容已完整列出，無缺漏佔位符。

**型別一致性：** 兩個 Task 修改的是不同檔案，無交叉引用問題。Task 1 新增的維度名稱（「架構」、「可讀性」）與 Task 2 的 Step 8 維度表格一致。
