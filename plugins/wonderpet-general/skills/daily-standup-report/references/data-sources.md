# 資料來源查法與踩雷

五個來源彼此互補：git 與 PR 只看得到「有提交、有開 PR」的工作；Jira 補卡片名稱與狀態；行事曆補會議；Claude 對話紀錄補「沒留下 commit 的工作」（查問題、驗收、除錯、審查）。

**分兩輪發出**：第一輪平行跑三支腳本（git、GitHub、對話紀錄）加行事曆、Jira 的「新開票」與「自己動過」查詢，這些彼此不依賴；第二輪才查 Jira 的卡片名稱與狀態，因為卡號要從第一輪腳本的輸出收集。

MCP 工具要先用 ToolSearch 載入 schema，一次載入：

```
select:mcp__claude_ai_Google_Drive__search_files,mcp__claude_ai_Google_Drive__create_file,mcp__claude_ai_Google_Drive__read_file_content,mcp__claude_ai_Google_Calendar__list_events,mcp__plugin_atlassian_atlassian__getAccessibleAtlassianResources,mcp__plugin_atlassian_atlassian__searchJiraIssuesUsingJql
```

GitHub 走腳本（`gh` CLI）時不需要 GitHub MCP。以下範例中的日期欄位都來自 `scripts/resolve_dates.py` 的輸出。

## 1. git（含所有分支）

```bash
python3 <skill 目錄>/scripts/git_in_range.py --start <workStart> --end <workEnd>
```

在程式庫內或隔離 worktree 內執行都可以（預設讀目前目錄，`--repo` 可指定路徑；worktree 與主 checkout 共用 refs，所以其他分支上的 commit 也看得到）。輸出已分成四類：

- **當天新提交**：以作者時間（author date）判斷，依卡號歸併，附時間區間。
- **搬動的舊提交**：commit 時間在範圍內、作者時間更早，是 rebase 或 cherry-pick 造成的，**不算當天新作**。`git log --since` 比的是 commit 時間，肉眼讀 log 很容易把它們當成當天寫的；實測一天就有 26 個，是新提交的兩倍。
- **自己按下的合併**：`Merge pull request #… from …` 代表自己按下了合併。分支名為 `update-release/…`、`update-staging/…` 的是自動版更 PR（cascade），`release/…` 是各子專案的 release PR，這兩類只給數量與編號，不逐筆列；班車 PR（`train/…`）會加註。「分支合併」是解衝突或直接併入分支。
- **卡號清單**：最後一行，第二輪查 Jira 用。

注意：

- 隔離 worktree 的 session 會拒絕含 `$(...)` 的 git 指令（例如 `--author="$(git config user.name)"`），也不准 `git -C` 指向同一專案的主 checkout。腳本自己讀 `user.name`、在 worktree 內直接讀 refs，不會踩到。
- 標題沒帶卡號的 commit，腳本只附一則標題當線索，卡號要從分支名或對話紀錄補。
- 腳本不能用時才手動查：`git log --all --author=<名字> --since=… --until=… --pretty=format:'%h|%ad|%cd|%s'`，**輸出不要用 `head` 截斷**（會漏 commit），並自己用 `%ad` 與 `%cd` 區分新作與搬動。

## 2. GitHub PR

```bash
python3 <skill 目錄>/scripts/github_in_range.py --start <workStart> --end <workEnd> [--repo owner/repo]
```

用 gh CLI 的一次 GraphQL 查詢取代逐筆查 MCP（需已登入 gh）。輸出兩段：

- **自己的 PR**：只列範圍內建立、合併、關閉未合併或有更新的；每筆附狀態、合併者、base 分支、審查結果。
- **審查他人 PR**：只列自己的審查 `submittedAt` 落在範圍內的，機器人作者略過；時間已轉成範圍的時區（GitHub 原始時間是 UTC，晚上 8 點以後的動作 UTC 日期會與台北日期差一天）。

判讀要點，都是實際踩過的：

- **看 base 分支才知道合併進了哪裡**：疊在功能分支上的 PR，合併後變更只進了那條功能分支，沒有進班車或 release。只看「已合併」會把它誤報成「進班車」。
- **合併者欄位可以確認是不是自己按的**。git 上找不到自己的合併 commit 時，多半是合進了功能分支，不是別人合的，別因此寫「合併者未查證」。
- **班車發車 PR、別人的版更 PR 只要自己送出核准就算審查**，腳本會列出；不要因為標題像雜務就漏掉。
- **以 GitHub 欄位為準**：對話紀錄說「draft」而 API 的 `isDraft` 是 false 時，以 API 為準。
- **`closed` 不等於 `merged`**：腳本分開標示「已合併」與「已關閉」；不確定就寫「已關閉」。
- 超過 100 筆時腳本會印警告，縮小範圍再跑。
- gh 不可用時改用 GitHub MCP：`search_pull_requests`（query 用 `repo:<owner>/<repo> is:pr author:@me updated:>=<githubUpdatedFrom>`，審查用 `reviewed-by:@me -author:@me`，`fields` 只要 `number, title, state, html_url, created_at, updated_at, closed_at`），審查再對每個非機器人 PR 呼叫 `pull_request_read`（`method: get_reviews`），**只算 `submitted_at` 在範圍內、審查者是自己的**；合併狀態用 `method: get` 看 `merged`。`get_reviews` 會連審查本文整份回傳，很吃 context，所以不是首選。

## 3. Jira（`mcp__plugin_atlassian_atlassian__*`）

- 先用 `getAccessibleAtlassianResources` 取得 cloudId，之後每次呼叫都帶上。
- **第一輪就能發的（不需要卡號）**：
  - 新開的票：`project = RD AND created >= "<工作日起>" AND created < "<晨會日>" AND reporter = currentUser()`。**新開票數只看這條**，結果為空就是 0 張。
  - 自己動過的票：`project = RD AND updated >= "<工作日起>" AND updated < "<晨會日>" AND (assignee = currentUser() OR reporter = currentUser()) ORDER BY updated ASC`。注意它抓的是「這段時間被動過」的票，不等於自己動手：自己開的票被別人改優先序也會出現，要靠其他來源佐證才能寫成自己的工作。其中無負責人的待辦票，可列入待確認事項。
- **第二輪：卡片名稱與狀態**：`searchJiraIssuesUsingJql`，`jql: issue in (<git 與對話紀錄腳本收集到的卡號>)`，`fields: ["summary","status","issuetype","assignee"]`。審查別人 PR 時，PR 標題裡的卡號也要一併帶進去。
- Jira 的狀態是「查詢當下」的，不是昨天當下的。報告裡一律標註「目前狀態」。
- **只讀**：不留言、不開票、不改欄位、不轉狀態。要寫入 Jira 需要使用者明確指示。
- 連線失敗（憑證讀取失敗、未授權）：請使用者在 Claude Code 輸入 `/mcp` 重新連線 Atlassian；使用者暫時不處理就跳過 Jira，卡片名稱改從 PR 標題與分支名推，狀態欄寫「未查證」，並在「資料來源與限制」交代。

## 4. 行事曆（`mcp__claude_ai_Google_Calendar__list_events`）

- `startTime`／`endTime` 用不帶時區偏移的本地時間（例如 `2026-10-12T00:00:00`），`orderBy: startTime`。
- 只列自己有出席（回覆 accepted）的會議；沒有會議就省略「會議」那一行。回覆 accepted 只代表接受邀請，是否真的出席查不到，限制欄要寫明。

## 5. Claude 對話紀錄（`scripts/sessions_in_range.py`）

```bash
python3 <skill 目錄>/scripts/sessions_in_range.py \
  --start <workStart> --end <workEnd> --projects-dir <對話紀錄目錄>
```

預設讀 `$CLAUDE_CONFIG_DIR/projects`，沒設就讀 `~/.claude/projects`；使用者若用不同的設定目錄，用 `--projects-dir` 指定。

- **只看有訊息時間戳落在範圍內的 session**，不看檔案修改時間。同步、續接、批次觸碰都會改 mtime，實測有一批 session 的 mtime 全部落在同一分鐘，但那天沒有任何互動。
- **不要排除目前的 session**（`--exclude-session` 只用在確定要略過的特定 session）：今天下指令的訊息不在範圍內，不會誤列；但 `/clear` 之後 session 編號不變，昨天的工作可能就在同一個 session 裡，排除會漏報。
- 每個 session 印出：提及最多的卡號（用來對應工作項目，專案名稱常看不出是哪張卡）、範圍內的使用者提問、`result:` **結論行**（取最後幾行）與最後一則回覆。**結論要看 `result:` 行**：驗收結果、根因、PR 狀態多半寫在這裡，最後一則回覆常只剩環境清理。要看更完整的內容，讀該 session 的 jsonl 尾端，或用 `--result-lines`、`--reply-chars` 調大。
- **這些是 Claude 自己的回報，不是證據**：結論要和 PR、Jira、commit 對照；對不起來或無法對照的，在報告中標明「取自當天對話紀錄回報，未重跑」。
- 不是每個 session 都該進報告：純粹確認工具能力、查 MCP 版本、閒聊的 session 略過；整理 worktree、清分支這類雜務併成一行。
- 對話內容可能含客人資料或驗收用的會員資料，寫進報告前依 `report-format.md` 的「不可放進報告的內容」去識別化。

## 整合時的對照

| 想說的事 | 需要的證據 |
|---|---|
| 某功能完成開發 | 有 commit 且有 PR（或對話紀錄明確說明已完成且測試通過） |
| 當天新寫的 commit | 作者時間在範圍內；只有 commit 時間在範圍內的是搬動 |
| 已合併 | PR 的 `merged` 為 true（腳本標「已合併」），或 git 有 merge commit |
| 合併進班車 | PR 的 base 是班車分支；base 是功能分支就只是合進那條分支 |
| 自己按下的合併 | PR 的合併者欄位是自己 |
| 驗收通過、N 條通過／M 條無法驗證 | 對話紀錄的 `result:` 結論行；有留言 Jira 的話以 Jira 留言為準 |
| 審查了某 PR | 審查紀錄的 `submittedAt` 在範圍內且審查者是自己 |
| 開了新票 | Jira 查得到 `created` 在範圍內且 reporter 是自己 |
| 目前狀態 | Jira 現況 |
