# 資料來源查法與踩雷

五個來源彼此互補：git 與 PR 只看得到「有提交、有開 PR」的工作；Jira 補卡片名稱與狀態；行事曆補會議；Claude 對話紀錄補「沒留下 commit 的工作」（查問題、驗收、除錯、審查）。五個來源彼此獨立，同一輪平行發出。

下面的工具若尚未載入，先用 ToolSearch 的 `select:` 載入該工具的 schema 再呼叫。以下範例中的日期欄位都來自 `scripts/resolve_dates.py` 的輸出。

## 1. git（含所有分支）

```bash
git -C <程式庫路徑> log --all --author="$(git -C <程式庫路徑> config user.name)" \
  --since="<gitSince>" --until="<gitUntil>" \
  --date=format:'%m/%d %H:%M' --pretty=format:'%h|%ad|%D|%s'
```

- 一定要 `--all`：工作常在 worktree 的分支上，沒掛在目前分支。
- **輸出不要用 `head` 截斷**：截斷會漏掉 commit，導致少報工作。
- 作者是自己的 merge commit（`Merge pull request #… from …`）代表「自己按下了合併」。分支名為 `update-release/…`、`update-staging/…` 的是自動版更 PR（cascade），歸納成一行雜務即可，不逐筆列。
- 分支名通常含卡號（`RD-1234-…`），commit 標題也常帶卡號，用正則 `RD-\d+` 收集所有出現過的卡號，下一步查 Jira 用。

## 2. GitHub PR（`mcp__plugin_github_github__*`）

- **自己的 PR**：`search_pull_requests`，query 用 `repo:<owner>/<repo> is:pr author:@me updated:>=<githubUpdatedFrom>`，`fields` 只要 `number, title, state, html_url, created_at, updated_at, closed_at`，`sort: updated`。
- **審查別人的 PR**：query 用 `... is:pr reviewed-by:@me -author:@me updated:>=<githubUpdatedFrom>`，再對每個非機器人的 PR 呼叫 `pull_request_read`（`method: get_reviews`），**只算 `submitted_at` 落在範圍內、審查者是自己的**。`reviewed-by` 只代表「曾經審查過」，不代表是當天審的，不逐筆確認會把上週的審查誤報成昨天。
- GitHub 的時間都是 UTC，要轉成台北時間（+8）再判斷是否落在範圍內；晚上 8 點以後的動作 UTC 日期會與台北日期差一天。
- **`closed` 不等於 `merged`**：PR 狀態是 closed 時，用 git log 的 merge commit 或 `pull_request_read`（`method: get`）確認是否真的合併，不確定就寫「已關閉」，不要寫「已合併」。
- GitHub MCP 不可用時，改用 `gh pr list --author @me --search "updated:>=<日期>" --json number,title,state,createdAt,closedAt,mergedAt`。

## 3. Jira（`mcp__plugin_atlassian_atlassian__*`）

- 先用 `getAccessibleAtlassianResources` 取得 cloudId，之後每次呼叫都帶上。
- **卡片名稱與狀態**：`searchJiraIssuesUsingJql`，`jql: issue in (<第 1 步收集到的卡號>)`，`fields: ["summary","status","issuetype","assignee"]`。
- **自己動過但沒留下 commit 的卡**：`project = RD AND updated >= "<工作日起>" AND updated < "<晨會日>" AND (assignee = currentUser() OR reporter = currentUser()) ORDER BY updated ASC`。這能抓到新開的票、改過狀態的票。
- Jira 的狀態是「查詢當下」的，不是昨天當下的。報告裡一律標註「目前狀態」。
- **只讀**：不留言、不開票、不改欄位、不轉狀態。要寫入 Jira 需要使用者明確指示。
- 連線失敗（憑證讀取失敗、未授權）：請使用者在 Claude Code 輸入 `/mcp` 重新連線 Atlassian；使用者暫時不處理就跳過 Jira，卡片名稱改從 PR 標題與分支名推，狀態欄寫「未查證」，並在「資料來源與限制」交代。

## 4. 行事曆（`mcp__claude_ai_Google_Calendar__list_events`）

- `startTime`／`endTime` 用不帶時區偏移的本地時間（例如 `2026-10-12T00:00:00`），`orderBy: startTime`。
- 只列自己有出席（回覆 accepted）的會議；沒有會議就省略「會議」那一行。

## 5. Claude 對話紀錄（`scripts/sessions_in_range.py`）

```bash
python3 <skill 目錄>/scripts/sessions_in_range.py \
  --start <workStart> --end <workEnd> [--exclude-session <目前 session id 前綴>]
```

預設讀 `$CLAUDE_CONFIG_DIR/projects`，沒設就讀 `~/.claude/projects`；使用者若用不同的設定目錄，用 `--projects-dir` 指定。

- **只看有訊息時間戳落在範圍內的 session**，不看檔案修改時間。同步、續接、批次觸碰都會改 mtime，實測有一批 session 的 mtime 全部落在同一分鐘，但那天沒有任何互動。
- 腳本每個 session 印出範圍內的使用者提問與最後一則回覆。最後一則回覆通常含該 session 的結論（驗收結果、根因、PR 狀態），是整理「協助他人」「問題診斷」的主要材料。需要更多細節時，讀該 session 的 jsonl 尾端。
- **這些是 Claude 自己的回報，不是證據**：結論要和 PR、Jira、commit 對照；對不起來或無法對照的，在報告中標明「取自當天對話紀錄回報，未重跑」。
- 不是每個 session 都該進報告：純粹確認工具能力、查 MCP 版本、閒聊的 session 略過；整理 worktree、清分支這類雜務併成一行。
- 對話內容可能含客人資料或驗收用的會員資料，寫進報告前依 `report-format.md` 的「不可放進報告的內容」去識別化。

## 整合時的對照

| 想說的事 | 需要的證據 |
|---|---|
| 某功能完成開發 | 有 commit 且有 PR（或對話紀錄明確說明已完成且測試通過） |
| 已合併 | git 有 merge commit，或 PR 的 `merged_at` 有值 |
| 驗收通過 | 對話紀錄有逐條驗收結果；有留言 Jira 的話以 Jira 留言為準 |
| 審查了某 PR | 審查紀錄的 `submitted_at` 在範圍內 |
| 開了新票 | Jira 查得到 `created` 在範圍內且 reporter 是自己 |
| 目前狀態 | Jira 現況 |
