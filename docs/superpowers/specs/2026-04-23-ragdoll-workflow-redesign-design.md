# Design：Ragdoll Develop Workflow 重新設計

**日期：** 2026-04-23
**狀態：** 已確認，待實作

---

## 背景與動機

現有 `ragdoll-develop-workflow` 與 gigaai Agent Skills Playbook 的六階段開發生命週期對照後，符合度約 55–58%。主要缺口集中在：

- **TDD 缺失**：流程是 RD 實作 → QA 驗收（test-after），test cases 無明確定義時機
- **Code Review 維度不完整**：缺乏架構、可讀性兩個明確維度
- **Knowledge Manager 位置不正確**：應在整體開發完成後才做文件歸檔
- **PR 描述更新未納入**：`github-update-pr-summary` 尚未整合進流程

重新設計目標：以 gigaai 六階段為結構框架，保有現有所有 Ragdoll agent，補齊關鍵缺口。

---

## 設計決策

| 決策 | 選擇 | 理由 |
|---|---|---|
| 對齊程度 | 以 Ragdoll 實際需要為主，gigaai 為參考框架 | 不強求逐 skill 對齊，保留 plan-challenger、validator 等 Ragdoll 特有 gate |
| TDD 責任歸屬 | Plan 階段定義 test cases | 測試案例是 spec 的一部分，RD 和 QA 共用同一份驗收標準 |
| 三層測試分工 | Unit / Integration / E2E 明確分層 | E2E 只測整體流程，Integration 覆蓋跨模組，Unit 覆蓋邏輯隔離 |
| Code Review vs E2E 順序 | Code Review 先，E2E 後 | Code Review 可能導致主程式大幅修正，E2E 應測最終穩定版本 |
| Knowledge Manager 時機 | SHIP 階段，全部 Task 完成後 | 文件歸檔是整體產出的彙整，不是每個 Task 的阻塞點 |
| 並行 Task | 同一 agent 類型可多實例並行 | 修改範圍不重疊時，同類 agent 可同時發派多個實例 |

---

## 整體架構

```
[DEFINE]  需求 → Brainstorming（可選）→ Plan + 三層 Test Cases → plan-challenger
[PLAN]    Task 切分（含並行標注）+ HARD GATE
[BUILD ↔ VERIFY]  RD → QA（unit+integration）→ commit → validator  × N Tasks
[REVIEW]  Code Review（五維）→ E2E QA（UI 改動時）
[SHIP]    Knowledge Manager → PR 完善 → PR 描述更新 → label done → Chat
```

---

## 各階段細節

### [DEFINE] 需求定義

**Step 1 — 接收需求**

收到需求後，**MUST** 詢問使用者：

> 「需求已收到。請選擇下一步：
> 1. Brainstorming — 先討論實作細節與不確定點，再進入 Plan 撰寫
> 2. 直接寫 Plan — 跳過 brainstorming，直接進入 Plan 撰寫」

- 選 1 → 呼叫 `superpowers:brainstorming`，完成後進入 Step 2
- 選 2 → 直接進入 Step 2

**Step 2 — 擬定 Plan + 三層 Test Cases**

呼叫 `superpowers:writing-plans` 產出 Plan。writing-plans 完成後，orchestrator 根據 Plan 內容補充定義三層 test cases（不依賴 writing-plans 修改其輸出格式）。最終產出格式如下：

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

**Step 2.5 — HARD GATE：plan-challenger 審查**

將 Plan + 三層 Test Cases 一起交給 `ragdoll-workspace:ragdoll-plan-challenger`：

- **通過** → 進入 PLAN 階段
- **不通過** → 回 Step 2 修正，重新提交審查

---

### [PLAN] 任務規劃

**Step 3 — 切分 Task**

每個 Task 的標準格式：

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

**HARD GATE — Task 完整性檢核**

每個 Task 進入 BUILD 前，**MUST** 確認：

| 檢查項目 | 說明 |
|---|---|
| 有明確的負責 Agent | 至少指定一個 RD subagent |
| 有 Unit 或 Integration test cases | 兩者至少一項；若都沒有，必須說明理由 |
| Task 範圍可在單一 session 完成 | 過大的 Task 必須進一步切分 |
| 每個 Task 對應到 Spec 至少一個驗收條件 | 不得有無對應需求的 Task |
| 並行標注安全 | 並行的 Task 修改範圍無檔案交集（plan-challenger 已審查） |

**MUST** 從 Step 3 開始到所有 Task 完成前，不再與使用者互動，全程自主執行。

---

### [BUILD ↔ VERIFY] 實作與驗收（每個 Task 重複）

**Step 4 — Git 初始化（第一個 Task 才執行）**

```bash
source ~/.bashrc && git --version && gh --version

git checkout -b RD-{ticket}-feature/ragdoll/{描述}
gh pr create --title "[Ragdoll][RD-{ticket}] {簡短描述}"
gh pr edit --add-label "working"
```

**Step 5 — 發派 RD Subagent**

| 情境 | 做法 |
|---|---|
| Task 涉及 Electron 層 | 發派 `ragdoll-electron-rd` |
| Task 涉及 Next.js 層 | 發派 `ragdoll-next-rd` |
| 兩層都涉及 | 同時發派兩個 |
| 多個可並行 Task | 同一則訊息發派多個 Agent 實例 |

發派時 **MUST** 提供：Task 描述、修改範圍、Unit / Integration test cases、相關 Spec / Plan 段落。

**Step 6 — QA 驗收（unit + integration）**

| RD | QA |
|---|---|
| `ragdoll-electron-rd` | `ragdoll-electron-qa` |
| `ragdoll-next-rd` | `ragdoll-next-qa` |

QA 失敗：回報詳細錯誤 → 轉交 RD 修正 → 直接重發 QA（不重走 Step 5）→ 重複直到通過。

**Step 7 — Commit + Validator**

```bash
git add <相關檔案>
git commit -m "[Ragdoll] {清楚描述此 Task 的變更}"
git push
```

前景執行 `ragdoll-workspace:ragdoll-validator`（PR 位址 + Jira Ticket）：

- **通過** → 繼續下一個 Task（回 Step 5）或進入 REVIEW
- **不通過** → 轉交 RD 修正，修正後重走 Step 6 → Step 7

---

### [REVIEW] 審查

**Step 8 — Code Review（五維把關）**

呼叫 `wonderpet-general:code-review-principles`：

| 維度 | 說明 |
|---|---|
| 正確性 | 邏輯正確、資料完整性、Breaking Change |
| 可讀性 | 命名一致、職責單一、決策有記錄 |
| 架構 | 模組邊界清晰、依賴方向正確 |
| 安全 | 注入防護、敏感資料、權限邊界 |
| 效能 | N+1、索引、記憶體、全量掃描 |

| 風險等級 | 處理方式 |
|---|---|
| 高風險 | **MUST** 回對應 Task 的 BUILD ↔ VERIFY 修正後再回 Step 8 |
| 中風險 | 記錄於 PR comment，由使用者決定是否修正 |
| 低風險 | 列入改善建議，不阻擋進入 SHIP |

**Step 9 — E2E QA（有 UI 改動時）**

發派 `ragdoll-workspace:ragdoll-e2e-qa`，執行 DEFINE 階段定義的 E2E test cases。

- **通過** → 進入 SHIP
- **失敗** → 定位失敗的 Task，轉交對應 RD 修正，修正後重走 BUILD ↔ VERIFY 該 Task，再回 Step 9

若無 UI 改動 → 跳過，直接進入 SHIP。

---

### [SHIP] 交付

**Step 10 — Knowledge Manager（整體文件歸檔）**

前景等待 `ragdoll-workspace:ragdoll-knowledge-manager` 完成。

發派時提供：所有 Task 變更摘要、完整修改檔案清單（`git diff main...HEAD --name-only`）、完整 Spec / Plan。

```bash
git add <知識庫文件>
git commit -m "[Ragdoll] docs: 更新知識庫文件"
git push
```

**Step 11 — PR 完善**

呼叫 `wonderpet-general:github-create-pr-steps`，帶入 Ragdoll 參數：

| 參數 | 值 |
|---|---|
| 分支命名規則 | `RD-{ticket}-feature/ragdoll/{30字以內描述}` |
| PR 標題格式 | `[Ragdoll][RD-{ticket}] {簡短描述}` |

**Step 12 — 更新 PR 描述**

呼叫 `wonderpet-general:github-update-pr-summary`：
1. 偵測 PR 是否含 NorwegianForest 資料夾變更 → 選對應範本
2. 從分支名稱解析 ticket 編號
3. 填入實作摘要後更新 PR body

**Step 13 — 完成通知**

```bash
gh pr edit --remove-label "working" --add-label "done"
```

發送 Google Chat 摘要，標題：`【Ragdoll 開發摘要】`，內容：功能說明、Task 清單、PR 連結、Jira Ticket 連結。

---

## 禁止使用的技能

以下技能與本工作流程衝突，**MUST NOT** 呼叫：

- `superpowers:subagent-driven-development`（本流程自帶 Subagent 發派）
- `superpowers:executing-plans`（同上）

---

## 受影響的其他 Skill（需同步更新）

| Skill | 需要的修改 |
|---|---|
| `wonderpet-general:code-review-principles` | 新增「架構」維度（模組邊界、依賴方向）；強化「可讀性」維度，使其明確獨立於「程式碼品質」 |
| `superpowers:writing-plans` | 輸出格式需包含三層 test cases（Unit / Integration / E2E），plan-challenger 審查時一併帶入 |
