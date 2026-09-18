---
name: hotfix-workflow
description: 通用型 hotfix（線上緊急修正）完整工作流程，涵蓋 systematic-debugging 根因調查、Jira 漏洞票的決策與建立、從 release/<代碼庫> 切出 hotfix 分支、writing-plans 撰寫修復計畫、plan-challenger 審查、依計畫實作、push 建立 PR 並用 github-update-pr-summary 填寫描述、以及 code-review-principles 自我審查直到無中高風險為止的完整迴圈。適用於 petpetgo 底下任何子專案（NorwegianForest / Ragdoll / Maltese / Labrador / JavaCat 等），不綁定特定專案。當使用者說「線上出問題要緊急修」「這是 hotfix」「正式站壞了要修一下」「這個 bug 要走 hotfix 流程」「幫我查這個 production 問題的根因並修掉、開 PR」，或提到要從 release 分支切修復分支、要走完整的緊急上線修正流程時，都應優先觸發此 skill，取代零散地個別呼叫 systematic-debugging / jira-create-issue-rule / writing-plans 等單一技能。
---

# Hotfix 修復工作流程

把「線上/正式站出現異常，需要緊急修正」這件事，從根因調查一路帶到 PR 準備合併，串接六個既有 skill/agent，確保每個階段都有明確的把關點，不會有人跳過根因調查直接猜著改、或跳過審查直接送 PR。

## 這支 skill 解決什麼問題、不解決什麼問題

- **解決**：已知（或懷疑）正式環境有異常，需要走「調查根因 → 開票（可選）→ 切 hotfix 分支 → 擬 Plan → 審 Plan → 實作 → 開 PR → 自我審查」全程的情境。
- **不解決**：全新功能開發（那是各專案自己的 develop workflow，例如 `ragdoll-workspace:ragdoll-develop-workflow`）。這兩者最大差異是**分支基準**（hotfix 從 `release/*` 切、feature 通常從 `master`/`train/*` 切）與**起手式**（hotfix 必須先做根因調查，feature 從需求 brainstorm 開始）。若專案已有自己的 develop workflow，兩者不衝突——本 skill 專門補「release 分支上的緊急修正」這一段。

---

## 流程總覽

```
[PRE-FLIGHT]  HARD GATE：確認所有會用到的 skill / agent 都已安裝，缺一個就終止
      │
[ROOT CAUSE]  systematic-debugging 找根因（HARD GATE，未完成不得往下走）
      │
[TICKET]      已有票號？沿用；沒有 → 問使用者是否要開 Jira 漏洞票
      │
[BRANCH]      驗證 release/<代碼庫> 基準存在 → 切 hotfix 分支
      │
[PLAN]        writing-plans 撰寫修復計畫
      │
[PLAN GATE]   HARD GATE：plan-challenger 審查，不過打回 [PLAN]
      │
[BUILD]       依 Plan 逐 Task 實作（executing-plans）+ 本地測試 + commit
      │
[PR]          一次性 push + gh pr create（WIP）→ github-update-pr-summary 填正式描述
      │
[REVIEW]      HARD GATE：自行用 code-review-principles 審查整個 PR
      │             高/中風險 → 回 [BUILD] 修正 → 重新 push → 回 [REVIEW]
      │             低風險 → 記錄建議，不阻擋
      ▼
   完成（高風險=0 且 中風險=0）
```

---

## [PRE-FLIGHT] HARD GATE：相依 Skill / Agent 安裝檢查

這支 skill 本身不做任何事，它靠串接一串既有 skill/agent 才能跑完整個 hotfix 流程。**一旦其中一個缺漏，不能用「我自己模擬它應該做的事」或「找一個功能相近的頂替」來蒙混過去**——例如缺 plan-challenger 就自己充當審查者、缺 jira-create-issue-rule 就憑印象手刻 ADF——這樣做出來的結果沒有經過該 skill 內建的查證步驟與踩雷知識，等於整個把關機制形同虛設。

**MUST** 在開始 [ROOT CAUSE] 之前，先核對目前可用的 skill 清單（system-reminder 裡「available skills」/「skills available for use with the Skill tool」那份列表）與可用 agent 清單（system-reminder 裡「Available agent types for the Agent tool」那份列表），確認以下**一律必查**的項目都在清單中：

| Skill / Agent | 種類 | 用在哪個階段 |
|---|---|---|
| `superpowers:systematic-debugging` | Skill | [ROOT CAUSE] |
| `superpowers:writing-plans` | Skill | [PLAN] |
| `wonderpet-general:plan-challenger` | **Agent** | [PLAN GATE] |
| `superpowers:executing-plans` | Skill | [BUILD]（預設執行方式） |
| `wonderpet-general:github-update-pr-summary` | Skill | [PR] |
| `wonderpet-general:code-review-principles` | Skill | [REVIEW] |
| `peace-wp-llm-wiki` 或 `wonderpet-general:jira-overview`（兩者擇一存在即可） | Skill | [BRANCH] 確認代碼庫名稱 |

以下是**條件式**依賴，只有真的會走到對應分支時才需要，在該分支發生前再檢查一次即可，不需要在一開始就檔住整個流程：

| Skill | 用在哪個分支 | 檢查時機 |
|---|---|---|
| `wonderpet-general:jira-create-issue-rule` + `wonderpet-general:jira-overview` | [TICKET] 使用者選「是，建立 Jira 漏洞票」 | 使用者選「是」之後、實際呼叫前 |
| `superpowers:subagent-driven-development` | [BUILD] 改用平行 subagent 執行（非預設） | 決定改用這個路徑之前 |

**任一項目缺漏時**：

1. **MUST** 立即終止整個工作流程，不執行任何後續步驟（包含目前正在做的步驟）。
2. 清楚告知使用者：缺少哪個 skill/agent（給完整名稱，如 `wonderpet-general:plan-challenger`）、以及需要先完成安裝/啟用後才能重新呼叫這支 skill。
3. **MUST NOT** 用名稱相似或功能局部重疊的其他 skill/agent 頂替。
4. **MUST NOT** 跳過該步驟、憑自己對這個 skill「應該會產出什麼」的猜測直接寫出對應內容再繼續往下走。

---

## 環境前置檢查

進行任何 git / gh 操作前先確認工具可用：

```bash
source ~/.bashrc
git --version
gh --version
```

`git` 或 `gh` 不可用時，請使用者自行安裝/登入後再繼續，不要嘗試繞過或自行修 PATH。

---

## [ROOT CAUSE] 根因調查

**MUST** 呼叫 `superpowers:systematic-debugging`，完整走完 Phase 1～3（讀錯誤訊息、重現、追資料流、形成單一假設並驗證），才能進入下一階段。

理由：hotfix 最容易犯的錯就是「看起來很急，先照著症狀改一版再說」，但沒找到根因的修法通常只是把 bug 換個地方重現，正式站緊急修正比一般開發更承受不起這種來回。

**產出**（後面幾個階段都要用到，先記錄下來）：
- 根因描述（哪個檔案/哪段邏輯、為什麼會這樣）
- 可重現步驟或既有證據（log、Sentry、資料庫查詢結果等）
- 若已嘗試過的假設有被推翻，一併記錄推翻理由（避免下一階段的人重複繞同一圈）

> 若受害範圍、影響版本等資訊使用者一開始沒提供，這裡是問清楚的時機，而不是等到要建票時才發現缺資訊。

---

## [TICKET] Jira 漏洞票的決策與建立

### 已有票號的情況

若使用者一開始就提供了 Jira 票號（如 `RD-8123`），直接用 `getJiraIssue` 讀出來確認：
- issuetype 是否為「漏洞」（Bug，id 10008）。若不是，提醒使用者這張票的類型，但**不要自作主張改類型**——尊重使用者指定的票。
- 票是否存在、能否讀到。讀不到就停下告知，不要臆測票號打錯還是票不存在。

確認完直接進入 [BRANCH]。

### 沒有票號的情況

**MUST** 用 `AskUserQuestion` 詢問使用者是否要建立 Jira 漏洞票，並附上 [ROOT CAUSE] 階段整理出的根因摘要供對方判斷（多數 hotfix 之所以要開票，是為了讓這次修正在版本歷史與其他人眼中可追溯）：

1. **是，建立 Jira 漏洞票**（推薦）——後續 PR、分支都能掛上票號，方便追蹤與驗收
2. **否，不建票**——僅適合真的來不及走票務流程的緊急情境，PR 描述會註記「未建票」

選「是」時：**先依 [PRE-FLIGHT] 的條件式依賴表，確認 `wonderpet-general:jira-create-issue-rule` 與 `wonderpet-general:jira-overview` 都在目前可用的 skill 清單中**——缺任一個就依 [PRE-FLIGHT] 的規則終止並告知使用者安裝，不要因為下面已經寫好欄位對照表就自己動手刻 ADF 送出，該 skill 涵蓋的建立流程、Issue Link 設定等細節本文件並未整段複製。確認都在後，呼叫 `wonderpet-general:jira-create-issue-rule`，依下列方式收斂範圍（因為這裡只開一張單一 Bug 票，不是拆解大型工作）：

- **跳過**它的「階段 2 範圍 Brainstorm」與「階段 3 方案比較與切分」——這兩階段是給「一個大型工作要拆成多張互相銜接的票」用的，單一 hotfix bug 不需要。
- **套用**它的「階段 4 內容撰寫」分層原則與 ADF 範本，但欄位對照改用**漏洞類型**（`wonderpet-general:jira-overview` 的「各類型特有必填欄位」表），不是它範例預設的任務類型欄位：

  | 欄位 | Field ID | 內容 |
  |---|---|---|
  | 正確行為 | `customfield_10059` | 這個功能/流程原本應該怎麼運作（給所有人看，業務語言） |
  | 驗收條件 | `customfield_10030` | ADF `taskList`，物理/操作等價的可驗收步驟 |
  | 上線版本 | `customfield_10038` | 這次修正預計隨哪個版本上線 |
  | 討論紀錄 | `customfield_10266` | ADF `expand` 包住，把 [ROOT CAUSE] 的根因分析整段放進去（可用 `paragraph` + `codeBlock`，範本見 jira-create-issue-rule） |
  | labels | — | 加上 `HOTFIX` |

- 建立前若這個票有明確 Parent Epic，依使用者提供或既有慣例掛上；沒有就不強求。

選「否」時：記下「本次修正未建立 Jira 票」，帶到 [PR] 階段的描述裡，直接進入 [BRANCH]。

---

## [BRANCH] 建立 hotfix 分支

### Step 1：確認代碼庫名稱（資料夾/分支前綴用的小寫英文）

用 `peace-wp-llm-wiki` 的 `wiki/index.md` 或 `wonderpet-general:jira-overview` 的「代碼庫名稱」選單確認專案對應的小寫代碼庫名稱（如 NorwegianForest→`norwegianforest`、Ragdoll→`ragdoll`、Maltese→`maltese`、Labrador→`labrador`、JavaCat→`javacat`）。查不到或有疑慮就直接問使用者，不要用猜的。

### Step 2：HARD GATE — 驗證分支基準

**MUST NOT** 直接假設 `release/<代碼庫>` 這個名字照字面存在就切下去。先做：

```bash
git fetch origin
git branch -r | grep "release/<代碼庫>"
```

理由：曾發生過「使用者指示切 master，但實際上該專案的正式站基準是另一條裸分支」的案例（NorwegianForest 的 `release/norwegianforest` 就是這種裸分支，且每次都要重新查證、不能假設它固定不變）。若找不到預期的 `release/<代碼庫>`，或使用者指定的基準跟你預期的不一樣，**停下來跟使用者確認**，不要自己選一個看起來合理的分支硬切。

若該 Jira 票（有開票的話）掛了 `HOTFIX` 或 `HOTFIX-STAGING` label，一併確認 label 內容跟你打算切的基準是否一致。

### Step 3：切分支

命名規則（沿用 `wonderpet-general:jira-overview` 記載的慣例，卡號在最前）：

```
RD-<票號>-hotfix/<代碼庫>/<30字以內描述>
```

沒有票號（[TICKET] 階段選了「否」）時，省略票號前綴：`hotfix/<代碼庫>/<描述>`。

```bash
git checkout -b RD-<票號>-hotfix/<代碼庫>/<描述> origin/release/<代碼庫>
```

> ⚠️ 若後續才補開了 Jira 票，**不要**把已經開了 PR 的分支改名——GitHub 的 PR 會因為 head 分支改名而關閉且無法重開。要嘛開票的決策提前到切分支之前定案，要嘛之後開新分支、開新 PR，並在新 PR 描述註明取代關係。

---

## [PLAN] 撰寫修復計畫

**MUST** 呼叫 `superpowers:writing-plans`，Spec 來源是 [ROOT CAUSE] 的根因調查內容，加上（若有）[TICKET] 階段的 Jira 票內容。

> **流程覆寫（MUST 遵守）**：`writing-plans` 存完 Plan 後，慣例上會問「Subagent-Driven 還是 Inline Execution？」。**本流程 MUST 跳過這個問題**，不詢問使用者，直接進入下面的 [PLAN GATE]。原因是 Plan 必須先通過 plan-challenger 審查才能談怎麼實作，太早問執行方式等於預設 Plan 一定會過。

---

## [PLAN GATE] HARD GATE：plan-challenger 審查

`wonderpet-general:plan-challenger` 是一個 **Agent（用 Agent 工具 dispatch，不是用 Skill 工具呼叫）**。發派時附上：

- [ROOT CAUSE] 的完整根因調查內容（不要只給自己整理過的摘要，理由跟下面「Plan 交付」一樣：轉述會引入詮釋誤差）
- Plan 檔案的絕對路徑
- Jira 票連結（若有）

**通過** → 進入 [BUILD]。
**不通過** → 回 [PLAN] 依回饋修正，重新送審，不得跳過重審直接動手實作。

**Subagent 失敗處理**：plan-challenger 呼叫失敗或回報無法完成時，重新發派一次（檢查傳入參數是否完整），最多兩次重試；仍失敗就停下來，把 agent 名稱、嘗試的動作、實際失敗原因回報給使用者，**不要**自己代替它下審查結論。

---

## [BUILD] 依 Plan 實作

**Plan 交付 HARD GATE**：無論是自己在當前 session 實作、還是發派其他 subagent 實作，一律**直接讀取 Plan 檔案的具體行號範圍**作為依據，不得用自己對 Plan 的理解轉述替代 Plan 原文——轉述會遺失 Plan 裡的細節，造成實作跟審查通過的版本兜不起來。

**執行方式**：預設用 `superpowers:executing-plans` 在目前 session 循序執行 Plan 的每個 Task（hotfix 範圍通常是單一根因、影響檔案有限，循序執行的檢查點反而比拆多個 subagent 更容易掌握全貌）。若 Plan 本身標注了多個確實互不相依、可平行的 Task，可以改用 `superpowers:subagent-driven-development`——但改用前先依 [PRE-FLIGHT] 確認它確實在可用 skill 清單中，缺了就維持用 `superpowers:executing-plans` 循序執行，不要自己土法煉鋼拆平行 subagent。

> 若目前專案本身已經有自己專屬的實作 subagent（例如 Ragdoll 的 `ragdoll-electron-rd` / `ragdoll-next-rd`、NorwegianForest 的 `norwegianforest-table-rd`），也可以優先委派給它們——但這是可選的加強，不是本流程的硬性規定，因為本 skill 要通用於未必有專屬 subagent 的專案。

每個 Task：
1. 依 Plan 的 TDD 步驟寫失敗測試 → 實作 → 讓測試通過
2. 該專案的測試指令跑一次（例如 Ragdoll 用 `npm run test:electron` / `npm run test:next`，NorwegianForest 用專案自己的 `bin/test.sh`；不確定就查該專案的 wiki 或既有 skill，不要裸跑測試框架繞過專案的測試腳本）
3. 本地 `git commit`，**不要 push**——push 留到全部 Task 完成後一次做，避免逐 Task 都觸發一次 CI/CD

---

## [PR] 建立 PR

全部 Task 完成後，一次性完成：

```bash
git push -u origin RD-<票號>-hotfix/<代碼庫>/<描述>
gh pr create --title "[<代碼庫>][RD-<票號 或標注 HOTFIX>] <15字內描述>" --body "WIP，等待 REVIEW 階段更新描述"
```

> `wonderpet-general:github-update-pr-summary` 只會 `gh pr edit` 既有 PR 的描述，**不會建立 PR**，所以這裡一定要先手動建好 PR。

PR 建好之後，呼叫 `wonderpet-general:github-update-pr-summary`：
- 它會自動偵測 PR 是否含 NorwegianForest 資料夾變更來選範本
- 從分支名稱解析票號填入卡片連結；若 [TICKET] 階段選了「否」，卡片連結欄位會是「分支名稱沒有包含 ticket 編號」，可以在摘要段落額外註記「本次修正未建立 Jira 票」
- 摘要內容依 [ROOT CAUSE] 的根因 + 這次的修復方式撰寫

---

## [REVIEW] HARD GATE：自我 Code Review 迴圈

**MUST** 依 `wonderpet-general:code-review-principles` 的完整流程（Phase 1 理解全貌 → Phase 2 由底向上逐層檢查 → Phase 3 撰寫結構化報告）**自行**審查整個 PR 的變更——這裡是自己審查自己剛做的修改，不是另外派一個公正的 subagent，所以尤其要留意 code-review-principles 裡提到的「自我審查偏誤」：把每一輪重審都當成完全不認識這段程式碼，帶著找碴的心態重新掃過，而不是只確認先前結論還成立。

依風險分級處理：

| 風險等級 | 處理方式 |
|---|---|
| 高、中風險 | **MUST** 回 [BUILD] 修正對應 Task，修正後重新 `git push`（會再觸發一次 CI/CD），回到 [REVIEW] 重新審查整個 PR |
| 低風險 | 列入改善建議，不阻擋完成 |

**只有「高風險 = 0 且 中風險 = 0」時，這次 hotfix 工作流程才算完成。**

---

## 完成回報

流程結束時，向使用者總結：

- 根因（一句話）
- Jira 票連結（或註記「未建票」）
- hotfix 分支名稱
- PR 連結
- 最終 code review 的低風險建議清單（若有）

本流程**不**自動把 PR label 改成 done、也**不**自動發送 Chat 通知——這些屬於「合併/上線後的收尾動作」，不是這支 skill 被要求做的範圍。若使用者需要，之後可以明確要求，或參考該專案自己的 develop workflow 對應步驟（例如 `ragdoll-workspace:ragdoll-develop-workflow` 的 Step 12）。

---

## Skill / Agent 對照表

呼叫本流程前務必先完成上方 [PRE-FLIGHT] 的安裝檢查，以下是各階段對應關係：

| 階段 | 呼叫對象 | 種類 |
|---|---|---|
| 根因調查 | `superpowers:systematic-debugging` | Skill |
| 建立 Jira 漏洞票 | `wonderpet-general:jira-create-issue-rule`（欄位對照 `wonderpet-general:jira-overview`） | Skill |
| 撰寫修復計畫 | `superpowers:writing-plans` | Skill |
| Plan 審查（HARD GATE） | `wonderpet-general:plan-challenger` | **Agent**（用 Agent 工具 dispatch） |
| 依計畫實作 | `superpowers:executing-plans`（或 `superpowers:subagent-driven-development`） | Skill |
| 更新 PR 描述 | `wonderpet-general:github-update-pr-summary` | Skill |
| 自我 Code Review（HARD GATE） | `wonderpet-general:code-review-principles` | Skill |

---

## 與其他 skill 的關係

- **`peace-wp-llm-wiki`**：確認專案代碼庫名稱、資料夾對應、有無專案專屬的 hotfix 慣例時查。
- **`wonderpet-general:jira-overview`**：Jira 欄位 ID、issue type、選單值的 schema reference，本流程開票用的欄位都對得上它。
- **各專案自己的 develop workflow**（如 `ragdoll-workspace:ragdoll-develop-workflow`）：處理的是「新功能開發」，分支基準與起手式都不同；若該專案的 hotfix 有更細緻的專屬規範（例如表格類專案的 patch 落地流程），以該專案專屬的規範為準，本 skill 提供的是沒有專屬規範時的通用骨架。
