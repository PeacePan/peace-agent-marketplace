---
name: jira-create-issue-rule
description: 把一個粗略需求、大型工作（Epic）或技術設計文件拆解成多張可獨立執行、相互正確銜接的 Jira task issue。涵蓋從脈絡收集 → 範圍 Brainstorm → 方案比較 → 票數切分 → 內容撰寫 → 相依關係建立的完整流程，含每張票的描述／規格／驗收條件／討論紀錄分層格式與 ADF 範本可直接套用。當使用者要規劃多張 ticket、把 spec 拆成 Jira 卡、把 RD-XXXX 大型工作展開為任務、規劃功能切分、設計 Epic 子任務、依設計文件開卡、為一個專案建立工作分解結構、或拿到一份 design doc / PR 要求把後續工作開成多張票時，都必須優先觸發此 skill。
---

# 以 SD 角度開立 Jira issue 的工作流程

把粗略需求或技術設計轉成「一組正確切分、彼此銜接、人人讀得懂、QA 可驗收」的 Jira task issue 是 SD 的核心責任之一。本 skill 規範這個流程的每個步驟與每張票的內容格式。

本 skill 與 [[wonderpet-general:jira-overview]] 互補：
- `jira-overview` 提供 **schema 知識**（哪些欄位、哪些必填、選單值）
- `jira-create-issue-rule`（本 skill）提供 **工作方法**（怎麼想、怎麼切、怎麼寫）

兩者應一起使用：先用 jira-overview 確認欄位 ID 與必填項，再用本 skill 規範實際撰寫的內容與切分邏輯。

---

## 觸發時機

任何時候使用者表達以下意圖之一，必須優先觸發本 skill：

- 「以 SD / 資深工程師角度規劃多張 ticket」
- 「把這個 spec / 大型工作 / Epic 拆成 Jira 卡」
- 「依設計文件開卡」
- 「為這個專案建立工作分解結構（WBS）」
- 拿到 design doc、PR、Confluence 後請求把後續工作開成多張票
- 已存在 `RD-XXXX` 大型工作（Epic），要展開底下的子任務

---

## SD 工作流程（5 階段）

每個階段都必須完成才能進入下一階段。不能跳階段——尤其不能跳過 Brainstorm 直接開卡。

### 階段 1：脈絡收集（Context Gathering）

開卡前必須完成的功課。讀到自己能跟 PM/PO 用業務語言對答的程度為止。

必讀清單（依現有資源逐項確認）：
1. **Parent Epic（大型工作）**：用 `getJiraIssue` 取 description、自訂欄位 `customfield_10057`（規格）、`customfield_10058`（參考資料）。
2. **相關 PR**：若 Epic 內有提到或附 link，用 GitHub MCP 讀 PR 內容、`get_files`、`get_diff`，理解既有實作或 infra 範圍。
3. **設計文件**：Epic 附件、Confluence、`docs/superpowers/specs/` 下的 spec 都要讀。
4. **相關卡片**：Epic 的 `issuelinks` 上下游、relates to 都要看。
5. **既有程式碼**：若涉及修改既有模組，用 Explore agent 或 Grep 確認現況。

收集完成的判斷依據：能用一句話講清楚「這個 Epic 要解決什麼問題、現況的痛點、技術上要往哪走」，而且能引用 Epic 與 PR 的具體內容支持這句話。

### 階段 2：範圍 Brainstorm（Scope Brainstorm）

用 [[superpowers:brainstorming]] 流程（如果工具可用）跟使用者一題一題釐清關鍵決策。**禁止一次丟多個問題；禁止跳過此階段直接提方案**。

常見必問的決策題（依專案性質取捨）：

1. **MVP 範圍**：要納入哪些功能 / 端點 / 模組？一次到位、還是分批？
2. **程式碼歸屬**：放在現有 monorepo 還是獨立 repo？放在哪個資料夾？
3. **API / 介面契約**：與既有系統 1:1 同型，還是趁機重新設計？
4. **設定 / 金鑰策略**：環境變數、Secrets Manager、Remote Config 怎麼選？
5. **可觀測性**：日誌格式、錯誤追蹤、Metrics 要做到什麼程度？
6. **Cutover / 灰度策略**：一次切換、按使用者灰度、按店家灰度？fallback 機制？

每個問題用 `AskUserQuestion` 給出 2-3 個選項並標註推薦，附取捨說明。**不要 yes/no 問題**。

### 階段 3：方案比較與切分（Decompose）

收集完決策後，提出 **2-3 種票切分方案**，附取捨與推薦。常見的切分維度：

| 切法 | 優點 | 缺點 | 適用場景 |
|---|---|---|---|
| **依層次切**（推薦）| 邊界清楚、可平行、單張票可獨立 review | 票多，PM 觀感繁瑣 | 多個獨立業務端點 + 共用基礎 |
| 依端點 / 功能切 | 票少、結構直覺 | 第一張票必然臃腫、其他票無法平行 | 端點高度相似、共用程式碼少 |
| 依里程碑切 | 適合敏捷迭代 | 票粒度太大、看不出進度 | 純研究 / Spike，無法事先精確切分 |

**默認推薦「依層次切」**：把共用基礎（骨架、CI/CD、Logger、Auth middleware）獨立成前置票，業務端點作為平行票，最後是整合 / cutover 票。理由是這樣每張票邊界最清楚、可平行給多人、單張票失敗不阻塞其他票。

### 階段 4：內容撰寫（Write Content）

每張票按下方「Issue 內容分層原則」撰寫，**禁止把工程細節寫進描述/規格**、**禁止把驗收條件寫成狀態描述**、**禁止包工時估算**。

### 階段 5：建立 Issue 與相依連結（Create & Link）

依下方「建立 issue 的技術細節」段落，用 Jira MCP 批次建立、設定 parent epic、用 `createIssueLink` 設定 Blocks / Relates 關係。

---

## Issue 內容分層原則

**核心理念**：Jira issue 是工程師與非工程師（PM、QA、客服、PO、老闆）的共同溝通介面。如果描述欄塞滿技術細節，非工程師看不懂；如果驗收條件寫成抽象狀態描述，QA 無從驗收。**把不同讀者的內容放到不同欄位**。

每張票分四層內容：

### 描述（description）

- **讀者**：所有 stakeholder
- **格式**：自然語言段落（markdown 即可）
- **內容**：這張票要解決什麼問題、對誰有什麼影響、做完之後系統會怎樣
- **禁止**：路徑名、函式名、framework 名、檔案結構、command、SDK 名稱

**範例（好）**：
> 讓 van 上線後遇到問題時可以被工程師快速看見並追查；同時建立第三方 API 金鑰的集中保管機制，不再讓金鑰散落或寫死在原始碼裡（這也是這次改建的主要痛點之一）。

**範例（壞）**：
> 在 Van/ 目錄新增 pino logger 與 @sentry/node，並用 aws-sdk 從 Secrets Manager `van/<env>/app` 讀取金鑰、in-memory cache。

### 規格（customfield_10057）

- **讀者**：所有 stakeholder
- **格式**：ADF `orderedList`（數字編號條列）
- **內容**：把這張票要交付的事情按「獨立規格要點」逐項列出
- **目的**：讓讀者一眼看到「這張票總共要做幾件事」、便於逐項討論
- **每項**：仍以業務語言陳述，不夾雜技術細節

**範例**：
1. 建立結構化 JSON 日誌機制，讓所有對外請求都能在 CloudWatch 中按 request id 查詢
2. 接入 Sentry 錯誤追蹤，未捕捉的錯誤會自動回報含完整堆疊
3. 建立 Secrets Manager 金鑰載入機制：服務啟動時一次拉取所有第三方金鑰、放入記憶體
4. 啟動時若金鑰讀取失敗，服務直接拒絕啟動（避免帶著錯誤設定上線）
5. 移除 Maltese 端原 proxy 中所有寫死的金鑰參考來源

### 驗收條件（customfield_10030）

- **讀者**：QA / 驗收者
- **格式**：ADF `taskList` / `taskItem`（checkbox 可勾選）
- **內容**：每一條是「操作 → 預期結果」，驗收者可以照著做、做完打勾
- **禁止**：狀態描述（「服務跑起來」、「健康檢查通過」是錯的）
- **可寫**：具體工具名稱（curl、AWS Console、Sentry）因為那是驗收者實際會用的

**範例（好）**：
- ☐ 在終端機執行 `curl https://pos-proxy-development.wonderpet.asia/health`，看到 HTTP 200 與正常回應
- ☐ 在 AWS console 確認 van-dev ECS service 的 task 狀態為 RUNNING、target group 健康檢查為 healthy
- ☐ 暫時把 secret 中任一欄位設成空值並重新部署，確認服務啟動失敗、ECS task 進入 STOPPED 狀態

**範例（壞）**：
- ☐ van 健康檢查通過 ← QA 不知道怎麼「驗收」這件事
- ☐ Secrets Manager 整合完成 ← 沒有可觀測的具體結果
- ☐ 程式碼合併後部署成功 ← 應拆解為「開 PR → 合併 → 在 GitHub Actions 看到 deploy job 成功」

### 討論紀錄（customfield_10266）

- **讀者**：工程師
- **格式**：ADF `bulletList`（一般項目符號）
- **內容**：路徑命名、技術選型、middleware 結構、第三方串接演算法、相依套件、SDK 版本、測試策略、需與其他角色對齊的細節
- **目的**：工程師動手前的技術備忘錄，PM/QA 看不懂沒關係

**範例**：
- Logger：pino JSON 格式、加 request-id middleware
- Sentry：`@sentry/node`，接入既有 pos / maltese org，需 Peter 提供 DSN 在 secret 中
- Secrets：AWS Secrets Manager `van/<env>/app`，啟動時 SDK 一次拉、in-memory cache、fail-fast
- payload schema 草案需與 Peter 同步，由 Terraform 端建好 secret 後服務才能跑

---

## 建立 issue 的技術細節

### 必填欄位（任務 issuetype 10007）

| 欄位 | Field ID | 內容 | 格式 |
|---|---|---|---|
| Summary | `summary` | 短標題 | 純文字，前綴 `[模組名]`（如 `[Van]`、`[Ragdoll]`） |
| 描述 | `description` | 給所有人的目的說明 | markdown 或 ADF |
| 規格 | `customfield_10057` | 數字編號條列 | **必須 ADF**，用 orderedList |
| 驗收條件 | `customfield_10030` | checkbox 步驟 | **必須 ADF**，用 taskList |
| 討論紀錄 | `customfield_10266` | 工程細節 | **必須 ADF**，用 bulletList |
| Parent | `parent` | 所屬 Epic key | 字串如 `RD-7600` |

**關鍵踩雷**：customfield 欄位拒收 markdown 字串，**必須是 ADF 物件**（`{type: 'doc', version: 1, content: [...]}`）。description 欄則接受 markdown（透過 `contentFormat: 'markdown'`）。

### ADF 範本（直接複製即用）

#### 規格欄（orderedList）

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "orderedList",
      "content": [
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "規格項目 1"}]}]},
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "規格項目 2"}]}]}
      ]
    }
  ]
}
```

#### 驗收條件欄（taskList / checkbox）

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "taskList",
      "attrs": {"localId": "ac-<issue-key-or-slug>"},
      "content": [
        {
          "type": "taskItem",
          "attrs": {"localId": "ac-<issue-key-or-slug>-1", "state": "TODO"},
          "content": [{"type": "text", "text": "驗收步驟 1：操作 → 預期結果"}]
        },
        {
          "type": "taskItem",
          "attrs": {"localId": "ac-<issue-key-or-slug>-2", "state": "TODO"},
          "content": [{"type": "text", "text": "驗收步驟 2：操作 → 預期結果"}]
        }
      ]
    }
  ]
}
```

**注意**：`localId` 必須唯一，建議用 `ac-<票號>-<序號>` 命名規則避免衝突。`state` 一律是 `"TODO"`，由 QA 在 Jira UI 上勾選改為 `"DONE"`。

#### 討論紀錄欄（bulletList）

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "bulletList",
      "content": [
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "技術細節 1"}]}]},
        {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "技術細節 2"}]}]}
      ]
    }
  ]
}
```

### 建立流程

1. **平行建立**：用單一訊息批次呼叫多次 `createJiraIssue`（不要一次一次序列建）
2. **回收 issue key**：每次回傳的 `webUrl` 與 `key`（如 `RD-7689`）要記下來，建立 link 時用
3. **設定 link**：用 `createIssueLink` 平行建立所有 Blocks / Relates link

### Issue Link 方向

`createIssueLink` 的方向常見搞錯，記清楚：

> **「A blocks B」** = A 必須先完成 B 才能開始
> → `inwardIssue: A`（blocker）、`outwardIssue: B`（blocked）

> **「A is blocked by B」** = A 等 B 完成
> → `inwardIssue: B`、`outwardIssue: A`

**「Relates」** 無方向，但慣例上 inward 是「主動關聯方」、outward 是「被關聯的參考」。

範例：
```
#1 完成才能做 #2 → inwardIssue: #1, outwardIssue: #2, type: "Blocks"
#1 參考 RD-7624 → inwardIssue: #1, outwardIssue: RD-7624, type: "Relates"
```

---

## 切票方法論

### 切票檢查清單

每張票必須通過以下檢查：

- [ ] **單一目的**：這張票只解決一件事
- [ ] **可獨立驗收**：完成條件不依賴其他票的部分結果
- [ ] **粒度合理**：直觀上 1-3 天可完成（不需寫進票，但 SD 自己要心裡有數）
- [ ] **相依清晰**：能說清楚被哪些票 block、會 block 哪些票
- [ ] **業務語言可表達**：能用一句話跟非工程師解釋「這張票做完會怎樣」

### 共用基礎 vs 業務端點

切大型工作時，把「基礎建設」與「業務功能」拆開：

**前置基礎（順序執行）**
- 程式碼骨架 + CI/CD pipeline
- 日誌 / 錯誤追蹤 / 金鑰管理
- 共用 middleware（認證、錯誤處理、輸入驗證）

**業務端點（可平行）**
- 端點 A
- 端點 B
- 端點 C

**整合 / cutover（順序執行）**
- 跨系統整合、灰度導入、文件化

這樣切的好處：基礎做完後 3 個端點可分給 3 個人平行做，最後再順序整合。

### 不要切的票

以下情況不該獨立成票：

- **單純的文件 / Playbook**：寫在父票的 PR description 或 ADR，不要佔一張票位置
- **單純的 follow-up 清理**：列在父票的「未來工作」段落，等實作完再決定要不要開
- **重構為重構而重構**：除非有明確的業務動機（效能、安全、可維護性數據）

---

## Design Doc

開卡前，先把整套設計寫成一份 design doc 放在 `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`，內容至少包含：

1. **背景**：parent epic、相關 PR、痛點
2. **範圍決策**：Brainstorm 階段每個關鍵問題的決定
3. **Ticket 列表**：summary 一覽 + 相依矩陣
4. **相依圖**：ASCII / mermaid 圖標示 Blocks 鏈
5. **規劃假設**：未來工作、需與其他角色對齊的事項

Design doc 不需 commit 到 main（依個別 repo 的 superpowers/specs 規範），但要在開卡訊息中提供路徑給使用者參考。

---

## 範例

完整的應用範例見 RD-7600 大型工作下的 RD-7689 ~ RD-7695 七張票（Van POS Proxy Server 規劃）：

- **Brainstorm 決策**：六個關鍵問題（MVP 範圍、repo 位置、API 契約、Secrets 策略、可觀測性、cutover 策略）
- **切票結果**：依層次切 — 3 張基礎（骨架/部署、Logger+Sentry+Secrets、共用 middleware）+ 3 張端點（可平行）+ 1 張 cutover
- **相依鏈**：`#1 → #2 → #3 → {#4, #5, #6} → #7`，外加 #1 relates to RD-7624（infra 票）
- **內容分層**：每張票都有業務語言描述 + orderedList 規格 + taskList 驗收 checkbox + bulletList 工程紀錄
- **Design doc**：`docs/superpowers/specs/2026-06-29-van-proxy-server-design.md`

---

## 反模式對照

| 反模式 | 為什麼錯 | 正確做法 |
|---|---|---|
| 描述欄寫「實作 `POST /api/foo` 端點，回應 JSON `{...}`」 | 路徑與 JSON 結構是工程細節，PM 看不懂 | 描述寫「讓 X 可以查詢 Y」，路徑放討論紀錄 |
| 驗收條件寫「程式碼合併到 main」 | 那是工程動作，不是業務可驗收的結果 | 拆成「PR 合併後 GitHub Actions 部署 job 成功 + dev 環境健康檢查回 200」 |
| 規格寫成一大段散文 | 讀者無法計數有幾項要做、無法逐項對焦 | 拆成數字編號列表，每項一個獨立要點 |
| 把 RD-XXXX 寫進程式碼註解 | 違反 [[feedback_no_ticket_in_comments]] | ticket 編號只在 commit message、PR description、ADR 出現 |
| 一張票塞 5 個業務端點 + 部署 + 監控 | 一張票失敗會阻塞全部、無法平行給多人 | 依層次拆，業務端點各自獨立票 |
| 工時估算寫進 description | 工時是規劃工具不是交付承諾、會綁架票的彈性 | 工時放 Sprint planning 紀錄，不入 ticket 本文 |
| 跳過 Brainstorm 直接開卡 | 範圍未對齊，開出來的票無法閉合 | 先用 AskUserQuestion 把關鍵決策一題一題定下來 |

---

## 與其他 skill 的關係

- **[[wonderpet-general:jira-overview]]**：欄位 ID、issue type、選單值的 schema reference。本 skill 用到的欄位都對得上 jira-overview。
- **[[superpowers:brainstorming]]**：階段 2 Brainstorm 的具體執行方法。
- **[[wonderpet-general:github-update-pr-summary]]**：開完票實作完成、要回填 PR description 時觸發。
- **[[wonderpet-general:code-review-principles]]**：開卡後的 PR review 階段使用。

---

## 維護注意

- 自訂欄位 ID（`customfield_10030`、`customfield_10057`、`customfield_10266`）一旦發布後極少變動，若 jira-overview 更新，本 skill 對照同步。
- ADF 結構若有變更（taskList 改名、新增欄位），先用 RD-7624 等既有票驗證後再更新範本。
- 「依層次切」的方法論可能因新類型專案（純研究、純 infra、純 spike）需要調整，遇到不適用情境時，先在使用者面前提出替代方案再執行。
