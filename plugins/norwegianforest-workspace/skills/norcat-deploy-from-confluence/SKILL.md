---
name: norcat-deploy-from-confluence
description: >
  依 Confluence「Sprint 部署」頁面（如 wonderpet.atlassian.net/wiki/spaces/RD/pages/.../Sprint+...+Production）
  自動將表格清單批次 patch / insert 至 staging 或 production 環境的協調流程。
  使用者訊息出現以下任一關鍵字 → 必載入並依本 skill 執行：
  部署 production、部署 staging、依 sprint 頁面 patch、Sprint XXX Production、
  Sprint XXX Staging、批次 patch、批次 insert、本次上線、本次部署、上線清單、發布表格。
  本 skill 規範：如何從頁面解析「hotfix-staging / master / hotfix」三段、
  如何依部署目標篩選段落、如何排除「本次不上線」、執行順序（insert 先 patch 後）、
  以及如何向使用者回報結果。底層工具 norcat_patch / norcat_insert 的細節見
  norwegianforest-workspace:mcp-wonderpet-table-usage 第 7 章。
---

# norcat-deploy-from-confluence

從 Confluence「Sprint 部署」頁面自動批次部署 NorcaT 表格到 staging / production 的標準流程。

## 適用情境

使用者說：
- 「依 Sprint 120 頁面部署 production」
- 「把這個 sprint 上 staging」
- 「下載 Confluence 上的部署清單跑 patch」
- 「Sprint XXX 上線」

→ 走本 skill 的步驟，**不要自己寫 Python 解析 / 不要逐表問使用者**。

## 前置條件檢查

執行前先確認三件事，缺一即提示使用者補齊：

1. **Atlassian MCP 可用**：能呼叫 `mcp__atlassian__getConfluencePage` 等工具讀頁面
2. **mcp-wonderpet-table 環境就緒**：`NORWEGIANFOREST_DIR` 已設定（執行 `norcat_patch` 失敗會明示）
3. **Branch 正確**：
   - 部署 `production` → 當前 git branch 必須是 `release/*` 或 `*hotfix/*`
   - 部署 `staging` → 當前 git branch 必須是 `staging/*` 或 `*hotfix-staging/*`
   - 不對 → bin/table.sh 內建 branch gate 會直接 exit 1；要主動先用 Bash `git rev-parse --abbrev-ref HEAD` 預先檢查並提示使用者

## Confluence 頁面結構（標準假設）

頁面通常含三個一級段落：

```
hotfix-staging         ← 緊急 staging 修補
  新增
    <table>
      <說明文字 / 連結>
    ...
  更新
    <table> [本次不上線]      ← 必須排除！
    ...
  刪除                       ← 本流程不處理
master                 ← 本 sprint 主要變更
  新增 / 更新 / 刪除（同上）
hotfix                 ← 已上 production 的 hotfix（只追記、不部署）
  新增 / 更新 / 刪除
```

每個表名後可能跟一行或多行 PR 連結 / Jira 連結 / 說明，這些**不影響表名**——表名永遠是該段第一行第一個 token。

## 部署規則（核心）

| 部署目標 | 取的段落 | 不取 |
|---------|---------|------|
| `production` | `hotfix-staging` + `master` | `hotfix` |
| `staging`    | `master` 一段 | `hotfix-staging` / `hotfix` |

`hotfix` 段是「已上 prod 的 hotfix 紀錄」，**任何自動部署流程都不取**。

## 執行步驟

### Step 1：抓 Confluence 頁面

```
mcp__atlassian__getConfluencePage(pageId 或 URL)
```

若使用者只給「Sprint 120」這類 keyword：用 `mcp__atlassian__searchConfluenceUsingCql` 搜尋頁面標題。

### Step 2：解析三個段落

把 markdown / ADF 內容分成 `hotfix-staging` / `master` / `hotfix` 三段。每段下找 `新增` / `更新` 兩個子段（`刪除`忽略）。

### Step 3：依部署目標篩段落

```
if env === 'production' → 取 hotfix-staging + master
if env === 'staging'    → 取 master
```

### Step 4：解析表名清單（每段的「新增」「更新」分別處理）

對每個子段：
- 行格式類似 `<tablename>` 或 `<tablename> 本次不上線`
- 若該行（或表名 inline 標記）含「本次不上線」字樣 → **排除**
- 大小寫敏感、保留底線

### Step 5：去重與分組

合併多段的表名清單時要去重（同表名出現在 hotfix-staging「新增」與 master「更新」時各保留一份）。最終得到：

```
{
  "insert": ["新增表 1", "新增表 2", ...],   // 去重後
  "patch":  ["更新表 1", "更新表 2", ...]    // 去重後
}
```

> ⚠️ 若同一表名同時出現在 insert 與 patch（理論上不該，但雙保險）：**只放 insert**（首次建表優先；patch 的 schema 變更會在 insert 內完成）。

### Step 6：向使用者展示分組、徵求確認

不要直接執行，先給使用者看一眼：

```
即將部署到 production，依 Sprint 120 頁面解析結果：

【insert】(來自 hotfix-staging 新增 + master 新增，已去重排「本次不上線」)
  - metasaletask
  - balancearchive

【patch】(來自 hotfix-staging 更新 + master 更新，已去重排「本次不上線」)
  - transferorder
  - wdshqtransit
  - ... 共 N 張

預計順序：先 insert N 張、再 patch M 張。整批失敗會自動 retry（預設 5 次、間隔 10s）。
production 操作每步都會跳人工 confirm 對話。

請確認：(1) 解析結果正確 (2) 同意執行
```

得到使用者確認後才進 Step 7。

### Step 7：依序執行

**順序：先 insert、再 patch**（patch 假設表已存在）。

```js
// (1) 新建表
const insertResult = await norcat_insert({
  env: <target>,
  tables: insertList,
  maxRetries: 5,
  retryDelaySeconds: 10
});

// 若 production 會跳出 confirm 對話、需使用者按下「確認」

// (2) 更新表
const patchResult = await norcat_patch({
  env: <target>,
  tables: patchList,
  maxRetries: 5,
  retryDelaySeconds: 10
});
```

每步檢查 `succeeded` 欄位，失敗時 stop 並彙整 stderr 給使用者，不要自動跳到下一步。

### Step 8：彙整回報

執行完畢後給使用者：
- 各步驟 attempts / 耗時
- 成功表名清單
- 失敗表名（若有）+ stderr 截尾
- 提示下一步（重跑失敗段、檢查 branch / 衝突）

## ⚠️ 嚴禁事項

1. **不要繞過 confirm 對話**：production 對話無法以環境變數跳過、agent 也不應嘗試「自答 confirmed=true」
2. **不要自己寫 Python / Bash 解析 Confluence**：用 Atlassian MCP，內建解析能力 + 自動處理權限
3. **不要把 hotfix 段加進部署**：那是已 prod 的紀錄、再 patch 一次無意義
4. **不要忽略「本次不上線」標記**：標記者刻意排除、強行加入會讓 sprint 提前曝光未完成功能
5. **不要把 insert 與 patch 合併呼叫**：底層是兩個獨立 npm script，分開呼叫才能個別處理失敗

## 與其他 skill 分工

| 想做的事 | 載入哪本 |
|---------|---------|
| 完整 sprint 自動部署流程（本指南） | `norwegianforest-workspace:norcat-deploy-from-confluence` |
| 單一 patch / insert 工具用法、`NORWEGIANFOREST_DIR` 設定、衝突重試、branch gate | `norwegianforest-workspace:mcp-wonderpet-table-usage` 第 7 章 |
| 用 MCP 工具查中台資料（與部署無關的查詢） | `norwegianforest-workspace:mcp-wonderpet-table-usage` 第 1-6 章 |
| 撰寫或修改 table schema 定義 | `norwegianforest-workspace:javacat-table-architecture` |
