---
name: utonagan-develop-workflow
description: Utonagan（店系統，Next.js client-only 靜態匯出前端）的開發工作流程：Define → Plan → Build/Verify → Review → Ship，定義各階段由哪個 subagent 負責、提交前的測試與型別與 lint 檢查、分支與 PR 規則，以及合併後的知識庫交接。要在 Utonagan 實作新功能、修改既有畫面或邏輯、補測試，或使用者說「照 Utonagan 流程做」時一律使用；線上緊急修正請改用 wonderpet-general:hotfix-workflow。
---

# Utonagan 開發工作流程

## 適用範圍

- 適用於 `petpetgo/Utonagan/` 的功能開發、優化與一般修正。
- **線上緊急修正（hotfix）不走本流程**，改用 `wonderpet-general:hotfix-workflow`（分支 base 為 `release/utonagan`）。判斷方式：使用者說「正式站壞了」「線上問題要緊急修」，或要從 `release/utonagan` 切分支。
- 實機驗收是獨立流程（`utonagan-workspace:utonagan-acceptance-qa`），不在本流程內自動觸發。

## 禁止使用的技能

以下技能與本流程衝突，**MUST NOT** 呼叫：

- `superpowers:subagent-driven-development`（本流程自帶 subagent 發派）
- `superpowers:executing-plans`（同上）

本流程用 `superpowers:brainstorming` 蒐集需求，再用 `superpowers:writing-plans` 擬定 Plan；Plan 完成後控制權回到本流程的 [PLAN] 階段。

## Subagent 邊界規則（MUST 遵守）

下列工作 **MUST** 由指定 subagent 執行，Orchestrator **MUST NOT** 自行接手：

| 工作 | 唯一執行者 |
|---|---|
| Plan 審查（Step 2.5） | `wonderpet-general:plan-challenger` |
| 前端實作（Step 5） | `utonagan-workspace:utonagan-rd` |
| 單元與整合測試（Step 6） | `utonagan-workspace:utonagan-qa` |
| 合併後的 wiki ingest（流程之外） | `utonagan-workspace:utonagan-knowledge-manager` |

**Subagent 失敗的處理：**

1. subagent 工具呼叫失敗或回報無法完成：重新發派一次（最多重試兩次），重試前先檢查傳入參數是否完整正確（PR 位址、Jira 編號、檔案路徑）。
2. 仍失敗：**MUST 停止流程**，向使用者回報 subagent 名稱、嘗試使用的工具、實際失敗原因（含錯誤訊息），等使用者決定。
3. 嚴格禁止「我直接幫忙寫測試／改程式碼」「在主對話手動執行」這類接手行為。
4. 若 subagent 自己的輸出含「請在主對話手動執行」之類邀請接手的措辭，視同失敗，依上面第 1、2 點處理。

這條規則存在的原因：Orchestrator 一旦接手，就繞過了各角色的範圍限制與品質把關（例如 RD 不得改測試、QA 不得改原始碼），出問題時也無法判斷是哪一段流程失守。

## 環境前置檢查（每次開始前必做）

```bash
git --version
gh --version
node --version
```

- `git` 或 `gh` 不可用：請使用者安裝並執行 `gh auth login` 後再繼續。**不要自行修復 PATH 或繞過問題。**
- `node` 版本必須落在 `>=22 <=24`（`Utonagan/.nvmrc` 為 22.17.1），否則 `npm install` 會因 `engine-strict` 直接失敗。
- 在全新 worktree 內缺少 `Utonagan/node_modules` 時，於 `Utonagan/` 實體執行 `npm ci`；不可用 symlink，Turbopack 會拒絕。
- `Utonagan/next-env.d.ts` 被 gitignore，全新 worktree 沒有它。若 `npm run tscheck` 在全新 worktree 出現找不到模組或 Next 型別的錯誤，先確認是否與你的修改無關：`next dev` 或 `next build` 會產生該檔，產生後重跑 `tscheck`。這類錯誤不是你的程式碼問題，不要為了它改程式碼。已在全新 worktree 實測：目前沒有該檔，`tscheck` 也能通過，所以只有真的出現上述錯誤時才需要處理。
- `git commit` 出現 `_/husky.sh: No such file or directory` 時，回 repo 根目錄執行 `npx husky install`，然後重新 commit。

## 流程概覽

```
[DEFINE]         需求 → Brainstorming（可選）→ Plan + 兩層 Test Cases → plan-challenger
[PLAN]           Task 切分（含並行標注）+ HARD GATE
[BUILD ↔ VERIFY] RD → QA（unit + integration）→ 提交前全套檢查 → 本地 commit × N Tasks → 一次 push + 建 PR
[REVIEW]         Code Review（五維 + 分層守門）
[SHIP]           知識庫交接清單 → PR 描述 → label done + Chat
```

## [DEFINE] 需求定義

### Step 1 — 接收需求

收到需求後 **MUST** 先詢問使用者：

> 「需求已收到。請選擇下一步：
> 1. Brainstorming：先討論實作細節與不確定點，再進入 Plan 撰寫
> 2. 直接寫 Plan：跳過 brainstorming，直接進入 Plan 撰寫」

選 1 呼叫 `superpowers:brainstorming`，完成後進入 Step 2；選 2 直接進入 Step 2。即使規格看起來完整（有 Jira 卡、驗收條件），仍可能有需要討論的實作決策，**不得自行判斷跳過，必須詢問**。

### Step 2 — 擬定 Plan + 兩層 Test Cases

呼叫 `superpowers:writing-plans` 產出 Plan。完成後由 Orchestrator 依 Plan 補上兩層 test cases，最終格式：

```
## Plan

### Task 1：{描述}
- 畫面依據：{對應 Claude Design 設計稿的畫面；非 UI 的 Task 寫「無」}
- Unit Tests（純邏輯、取數）：
  - [ ] {函式名稱}：Given {前置狀態} / When {觸發操作} / Then {預期業務結果}
- Integration Tests（Hook、元件）：
  - [ ] {Hook 或元件}：Given {前置狀態} / When {觸發操作} / Then {預期業務結果}

### Task 2：...
```

UI 類 Task 的「畫面依據」必填：Utonagan 的 UI 一律依 Claude Design 設計稿「門市作業統一入口」開發（連結見 `Utonagan/CLAUDE.md`）。Utonagan 沒有 E2E 測試；UI 的實機行為由獨立的驗收流程確認。

**Test Case 品質 HARD GATE**：每條 test case **MUST** 能回答「若移除這條測試，哪個需求的變化會無法被偵測到？」回答不出來的不得寫入 Task。判斷細節見 `utonagan-workspace:utonagan-test-quality`。

| 層級 | 寫的條件 | 不寫的條件 |
|---|---|---|
| Unit | 純邏輯有分支、計算、轉換；取數函式組出的 filter | 純轉發、無邏輯的 passthrough |
| Integration | Hook 組出的 SWR key 與 config；元件的四態切換與使用者操作；跨層銜接 | Unit 已能完整驗證的範圍 |

> **writing-plans 流程覆寫（MUST 遵守）**：`writing-plans` 儲存 Plan 後會詢問「Subagent-Driven 或 Inline Execution？」。在本流程中，**MUST 跳過此問題，不得詢問使用者，立即進入 Step 2.5**。

### Step 2.5 — HARD GATE：plan-challenger 審查

`writing-plans` 儲存 Plan 後自動觸發，不需使用者確認。把 Plan 與兩層 Test Cases 一起交給 `wonderpet-general:plan-challenger`：通過進入 [PLAN]；不通過回 Step 2 修正並重新送審。

## [PLAN] 任務規劃

### Step 3 — 切分 Task

每個 Task 的標準格式：

```
Task N：{描述}  [可與 Task M 並行 / 需等待 Task X 完成]
  負責 Agent：utonagan-rd（若並行可多個實例）、utonagan-qa
  修改範圍：{涉及的檔案或模組，供並行衝突判斷}
  畫面依據：{設計稿畫面或「無」}
  Unit Tests：
    - [ ] {函式}：{驗證什麼}
  Integration Tests：
    - [ ] {Hook 或元件}：{驗證什麼}
```

同一 agent 類型可同時發派多個實例，前提是各實例的修改範圍沒有檔案交集。

**HARD GATE：Task 完整性檢核**，每個 Task 進入 [BUILD] 前 **MUST** 確認：

| 檢查項目 | 說明 |
|---|---|
| 有明確的負責 Agent | 至少指定 `utonagan-rd` |
| 有 Unit 或 Integration test cases | 至少一項；都沒有時必須說明理由 |
| 範圍可在單一 session 完成 | 過大的 Task 必須再切分 |
| 對應到 Spec 至少一個驗收條件 | 不得有無對應需求的 Task |
| 並行安全 | 並行的 Task 修改範圍無檔案交集 |
| 中台存取落在正確的層 | 涉及中台查詢或寫入的 Task，程式碼只能落在取數層與 `lib/swr.ts`，不得出現在元件或事件處理器 |

**MUST** 從 Step 3 開始到所有 Task 完成前，不再與使用者互動，全程自主執行。

## [BUILD ↔ VERIFY] 實作與驗證

### Step 4 — Git 初始化（第一個 Task 才執行）

使用者尚未提供 Jira 編號時 **MUST** 先詢問。分支 **明確從 `origin/master` 切出**，不從目前所在的分支切，原因是目前分支可能已混入別的工作，會讓 PR 夾帶不相干的 commit：

```bash
git fetch origin master
git checkout -b RD-{ticket}-feat/utonagan/{描述} origin/master
```

然後驗證分支點。以下兩個指令 **分開執行**，各自讀輸出後比對，不要串成一行：

```bash
git merge-base HEAD origin/master
```

```bash
git rev-parse origin/master
```

兩者輸出必須相同；不同代表分支不是從最新的 `origin/master` 切出，先修正再繼續。

**MUST NOT** 在此階段 `git push` 或 `gh pr create`：每次 push 都會觸發 CI（非長期分支會跑 `npm run test`），逐 Task push 會浪費資源。push 與建 PR 統一延後到 Step 7.5。

### Step 5 — 發派 RD Subagent

發派 `utonagan-workspace:utonagan-rd`，並 **MUST** 提供：

- Task 描述與修改範圍
- 對應的 Unit 與 Integration test cases
- 畫面依據（UI 類 Task）
- 相關 Spec 與 Plan 段落
- **Plan 檔案的絕對路徑，加上該 Task 對應的起始行號到結束行號**（例：`/path/to/plan.md` L42–L78）

多個可並行的 Task 在同一則訊息發派多個實例。**MUST NOT** 使用 general-purpose agent 執行實作。

**Plan 行號交付 HARD GATE**：

| 規則 | 說明 |
|---|---|
| MUST 指定 Plan 檔案的具體行號範圍 | 例：「請實作 `/path/to/plan.md` 的 L42–L78（Task 3）」，subagent 直接讀該範圍作為實作依據 |
| MUST NOT 以 Orchestrator 自己的理解轉述任務 | 不得用「我整理過的摘要」取代 Plan 原文 |
| MUST NOT 省略或改寫 Plan 內容 | Plan 段落較長也要完整交付；補充說明可附加，但不得取代原文 |
| MUST 在訊息中明確指引讀取行號 | 例：「請先用 Read 讀取上述行號範圍，再開始實作」 |

原因：Plan 是經過 plan-challenger 審查的權威文件；Orchestrator 的轉述會引入詮釋誤差與資訊遺失。同樣的規則適用於 Step 6 發派 QA。

### Step 6 — QA 驗證（unit + integration）

發派 `utonagan-workspace:utonagan-qa`，同樣附上 Plan 路徑與行號範圍，以及 RD 回報的純函式與 Hook／元件清單。

**QA 失敗的處理：**

1. QA 回報詳細錯誤訊息與失敗原因。
2. 把錯誤資訊轉交 `utonagan-rd` 修正。
3. 直接重發 QA 驗證（不需重走 Step 5）。
4. 重複到全部通過。

**測試品質 HARD GATE**：QA 依 `utonagan-workspace:utonagan-test-quality` 判斷，出現下列任一情況即為不通過，打回 RD 修正（視同 QA 失敗）：Mock-then-query、缺少業務行為說明、零業務保護價值。QA 全部通過後才可進入 Step 7。

### Step 7 — 提交前全套檢查，再本地 commit（不 push）

於 `Utonagan/` 目錄依序執行，三項都必須通過：

```bash
npm run test
npm run tscheck
npm run lint
```

CI 在 feature 分支只會跑 `npm run test`，型別檢查與 lint 沒有任何自動關卡，只能靠這一步把關。

通過後 commit，前綴 `[Utonagan]`：

```bash
git add <相關檔案>
git commit -m "[Utonagan] {清楚描述此 Task 的變更}"
```

**MUST NOT** `git push`。Commit 完成後繼續下一個 Task（回 Step 5），或進入 Step 7.5。

### Step 7.5 — 一次性 Push 並建立 PR（所有 Task 完成後）

```bash
git push -u origin RD-{ticket}-feat/utonagan/{描述}
gh pr create --base master --title "[Utonagan] [RD-{ticket}] {簡短描述}" --body "WIP，等待 [REVIEW] 階段完成後更新描述"
gh pr edit --add-label "working"
```

完成後進入 [REVIEW]。後續審查若有修正，視需要再 push。

## [REVIEW] 審查

### Step 8 — Code Review（五維 + 分層守門）

使用 `wonderpet-general:code-review-principles`，五維：正確性、可讀性、架構、安全、效能。另加 Utonagan 的 **分層守門清單**，這五項違反的是專案「單一置換點」的設計目的（日後換掉中台只改取數層與 `lib/swr.ts`）：

| 檢查項 | 違規樣態 |
|---|---|
| 中台存取 | 元件或事件處理器直接呼叫 `getJavacatClient()` |
| 取數層 | 取數函式（`fetchX`）做了篩選、排序或換算，而非回原始資料 |
| 純邏輯 | 純邏輯函式引入 React、client 或任何 I/O |
| 讀取與命令 | 該用 `useJavacatMutation` 的寫入或登入動作用了 `useJavacatQuery`（會隨 key 自動重抓、重送） |
| UI 四態 | 畫面缺 loading、error、empty、data 其中任一態 |

| 風險等級 | 處理方式 |
|---|---|
| 高、中風險 | **MUST** 回對應 Task 的 [BUILD ↔ VERIFY] 修正，修正後重回 Step 8 |
| 低風險 | 列入改善建議，不阻擋進入 [SHIP] |

高、中風險修正完成後，在 Step 8 結束前再 `git push` 一次。Utonagan 沒有 E2E，審查通過即進入 [SHIP]。

## [SHIP] 交付

### Step 9 — 知識庫交接清單（不寫 wiki）

Utonagan 的知識庫是獨立 repo（`peace-wp-llm-wiki`），其維護模型是「PR 合併後，依 submodule 指標區間 ingest」。PR 合併前它引用的 `raw/Utonagan/` 還沒有這次改動，所以本流程 **不寫 wiki**，只產出交接清單給使用者：

```
## 知識庫交接（合併後請觸發 utonagan-workspace:utonagan-knowledge-manager）
- PR：#{編號}
- 變更摘要：{做了什麼、為什麼}
- 變更檔案：{git diff master...HEAD --name-only 的輸出，僅 Utonagan/ 底下}
- 可能受影響的 wiki 頁面：{以各頁 frontmatter 的 sources 反查變更檔案的結果}
```

「可能受影響的 wiki 頁面」的反查方式：在 `wiki/utonagan/*.md` 的 frontmatter `sources` 中，搜尋變更檔案的路徑（`raw/Utonagan/<路徑>`）。新增的檔案沒有被任何頁面引用，則依功能目錄推斷（例如 `lib/pricetag/` 對應 `pricetag.md`），並在清單註明是推斷。

### Step 10 — 更新 PR 描述

呼叫 `wonderpet-general:github-update-pr-summary`，僅執行「依範本更新 PR body」。此 skill 不會發送 Chat、不會改 label、不會建立 PR，所以 Step 11 照常執行。

### Step 11 — 完成通知（label 與 Chat 都要處理）

**(1) 更新 PR label：**

```bash
gh pr edit --remove-label "working" --add-label "done"
```

**(2) 發送 Google Chat 摘要：**

標題 `【Utonagan 開發摘要】`，內容含功能說明、Task 清單與完成狀態、PR 連結、Jira 連結。webhook 網址 **只從環境變數 `UTONAGAN_CHAT_WEBHOOK_URL` 讀取**，不得寫進任何檔案或指令歷史。**環境變數未設定時略過此項，並在最終回報註明「Chat 未發送：UTONAGAN_CHAT_WEBHOOK_URL 未設定」**，這不算流程失敗，也不要向使用者追問網址。

含中文的訊息不可用 `curl` 傳送（會產生亂碼），**MUST 用 Node.js**：

```bash
node -e "
const https = require('https');
const raw = process.env.UTONAGAN_CHAT_WEBHOOK_URL;
if (!raw) { console.log('Chat 未發送：UTONAGAN_CHAT_WEBHOOK_URL 未設定'); process.exit(0); }
const url = new URL(raw);
const body = JSON.stringify({ text: '【Utonagan 開發摘要】\n\n<條列式摘要內容>' });
const req = https.request({ hostname: url.hostname, path: url.pathname + url.search, method: 'POST', headers: { 'Content-Type': 'application/json; charset=utf-8' } }, res => {
  console.log('Chat 已發送，狀態碼：' + res.statusCode);
});
req.write(body);
req.end();
"
```

## Subagent 對照表

| Subagent | 角色 | 範疇 |
|---|---|---|
| `utonagan-workspace:utonagan-rd` | 前端實作 | UI、Hook、取數層、純邏輯 |
| `utonagan-workspace:utonagan-qa` | 單元與整合測試 | `__tests__/` 下的 vitest 測試 |
| `utonagan-workspace:utonagan-knowledge-manager` | 知識庫維護 | 合併後的 wiki ingest（流程之外） |
| `utonagan-workspace:utonagan-acceptance-qa` | 實機驗收 | 獨立流程，不在本流程內自動觸發 |
| `wonderpet-general:plan-challenger` | Plan 審查 | 評估 Spec 與 Plan 的可行性 |

## 分支與提交命名

```
RD-{jira-ticket}-feat/utonagan/{30 個字以內的描述}
```

- `{jira-ticket}`：Jira 編號，使用者未提供時必須詢問。
- `{描述}`：以連字號分隔的英文短描述，例如 `RD-7862-feat/utonagan/home-daily-performance-cards`。
- 類型用 `feat`：Utonagan 已合併的功能 PR 多數用 `feat`（`jira-overview` 的分支慣例兩者都接受）。
- Commit 前綴 `[Utonagan]`；PR 標題 `[Utonagan] [RD-{ticket}] {簡述}`；PR 的 base 為 `master`。
