---
name: abyssinian-acceptance-workflow
description: >
  Abyssinian（POS Server，Next.js 全端：後台頁面＋機台端 API＋Worker；Jira Epic RD-8489 POS-S）
  單一 ticket 的實機驗收標準作業流程。因為前後端一體、沒有 Electron 視窗也沒有純靜態前端，
  utonagan／ragdoll 的驗收 SOP 都不適用，所以這份 SOP 把驗收拆成三個面向：後台畫面（Playwright）、
  機台視角（模擬機台與 device-peek）、背景流程（Worker 日誌與版本變化），並附一套本機一鍵環境
  （內嵌資料庫＋Server＋Worker＋假中台，不碰共用 dev）。涵蓋範圍界定（父系 Epic 必須是 RD-8489）、
  驗收條件解析、diff-first（含「功能是否真的已實作」的檢查）、起環境、造異動、三態判定與證據等級、
  「預設不留言 Jira」規則與清理。當使用者要求驗收 Abyssinian 的某張卡（B4 門市專屬檔、T1 離線交易閘道等）、
  或要確認 POS Server 的後台與機台 API 是否符合驗收條件時使用。
---

# Abyssinian 實機驗收 SOP

## 適用範圍

- 只適用於父系 Epic 是 **RD-8489（POS-S）** 且卡名以 `[Abyssinian]` 開頭的 Jira ticket。驗收的是「使用者明確指定的單一 ticket」，不是「給 Epic 就自動驗收所有子卡」。
- **`[Ragdoll]` 開頭的卡（E1～E3，機台端改接）不適用**：它們雖然掛在同一個 Epic，驗收面是 Ragdoll 的 Electron 視窗，而 `ragdoll-acceptance-workflow` 又只認父系 RD-7600，需要先請使用者決定怎麼驗。
- 這是「像 QA 一樣操作一次正在跑的系統」，不是寫自動化測試。發現缺陷只回報，不修正原始碼。

**為什麼不能套用其他 SOP**：Utonagan 是純靜態前端（驗收就是用瀏覽器點畫面）、Ragdoll 是 Electron 加本機 SQLite（驗收靠 Electron MCP 與 SQLite MCP）。Abyssinian 同一個專案裡有後台頁面、機台用的 HTTP API、以及獨立的 Worker 背景程序，而且驗收條件大半在描述「機台拿到什麼版本的資料」這種沒有畫面的事。所以需要三種視角一起用，並自己準備資料來源。

## 驗收的三個面向

| 面向 | 驗什麼 | 工具 | 證據 |
|---|---|---|---|
| 後台畫面 `/admin/*` | 條件裡「在後台看到…」的部分 | Playwright MCP | `browser_snapshot` 文字、截圖 |
| 機台視角 `/api/v1/device/*` | 專屬檔內容、版本、續傳、守門（403／401／410） | `npm run machine:sim`、`scripts/device-peek.mts` | 指令輸出（版本、sha256、回應碼） |
| 背景流程（Worker） | 來源讀取、編譯、發佈、推播何時發生、發給誰 | Worker 日誌＋manifest 版本變化 | 日誌事件行、版本前後比對 |

另有第四種證據：PR 自己的自動化測試（單元＋整合），作為獨立旁證，不能取代實機。

## 速覽

| Step | 做什麼 |
|---|---|
| 0a | 工具依賴檢查；確認驗收的程式碼版本（PR head），建獨立 worktree |
| 0b | 決定資料來源與環境（預設：本機＋假中台），起環境並留下就緒證據 |
| 1–2 | 範圍界定（父系 Epic ＝ RD-8489）、解析驗收條件、完整讀規格與討論紀錄 |
| 3 | diff-first，並**逐條確認條件對應的功能在這個 PR 是否已實作**；跑 PR 自己的測試 |
| 4 | 找操作依據（`DEPLOY.md` 驗收方式表、`docs/dataset-device-api.md`、wiki） |
| 5 | 實機操作：造異動、機台視角、後台畫面、背景日誌 |
| 6 | 三態判定＋證據等級，回報；預設不留言 Jira |
| 7 | 使用者表示驗收完成後清理環境 |

**授權分界**：

| 可自行做（不必問） | 須使用者明確同意 | 一律不做 |
|---|---|---|
| 自建 detach worktree、複製 `node_modules`、起本機環境（假中台、內嵌資料庫、Server、Worker）；對假中台寫入任何資料（它只存在於自己的行程）；本機模擬機台與壓測探針（小規模）；唯讀查 Jira、GitHub | Jira 留言與上傳附件；commit／push／開 PR；**對共用 dev 中台寫入**（建測試機台、改活動、新增員工）；連 dev／staging 環境操作（需真實令牌，見 Step 0b）；停掉**非自己**啟動的行程 | 對 production 查詢或寫入；在遠端環境簽發令牌（腳本也拒絕）；改使用者自己的 worktree 或分支；為了讓條件「過」而修改原始碼 |

---

## Step 0a：工具依賴檢查（缺任何一項就停止）

| 檢查項 | 方法 | 缺失時的訊息 |
|---|---|---|
| `wonderpet-general:jira-overview` skill | 用 `Skill` 載入 | 「缺少 wonderpet-general plugin，請先安裝」 |
| Playwright MCP | `ToolSearch` 查 `playwright`，用 `select:` 載入 `browser_navigate` 等工具 | 「缺少 Playwright MCP：由 wonderpet-general plugin 提供（`playwright`），請確認已啟用，並用 `/mcp` 檢查」 |
| Node | `node --version`，必須落在 `>=22 <=24`（`package.json` 的 `engines`） | 回報版本不符 |
| `python3`、`lsof`、`curl`、`patch`、`gh` | `command -v` | 缺哪個就回報哪個 |

Playwright 工具在工具清單裡可能是 deferred，沒載入就呼叫會失敗，在判斷「沒有 Playwright」之前一定要先 `ToolSearch`。**這台機器沒有 `jq` 與 `timeout`**：JSON 用 `device-peek.mts` 或 `node -e`，限時用 `scripts/run-with-timeout.py`。

### Step 0a-2：確認驗收的程式碼版本，備好 worktree

**不論有沒有環境已在跑都要做。** 驗收的是 PR 已推送的 head，不是本機分支：本機分支常領先遠端（有尚未推送的 commit），驗那個等於驗一份沒人 review 過的程式碼。

1. **找分支與 PR**：Jira `customfield_10033`（分支名稱）常是空的 → `git branch -r --list '*RD-xxxx*'`，再 `gh pr view <分支> --json state,isDraft,baseRefName,headRefOid,mergeable`。記下 `state`、`base`、head sha、是否 draft。
   - **疊式 PR**：Abyssinian 常把 PR-1 的 base 設成 PR-0 的分支。PR-1 的 head 已包含 PR-0 的 commit，驗 head 即可；`mergeable` 為 `CONFLICTING` 時照實寫進報告（不影響在 head 上驗收）。
   - PR 已 merge → 驗含該 commit 的 checkout（`git merge-base --is-ancestor <PR head> <HEAD>` 確認）；仍 open → 只能驗 PR 分支。
2. **建 worktree（`--detach`）**：開發 session 通常已占用同一分支，也不該動使用者的開發 worktree：
   ```bash
   git fetch origin <分支>
   git worktree add --detach .claude/worktrees/<卡號>-accept <PR head sha>
   ```
   再用 `EnterWorktree({path: "<絕對路徑>"})` 隔離（若回「已是目前工作目錄」表示已在其中，繼續即可）。**MUST NOT** 用 `EnterWorktree({name})`，它只會從 HEAD 新建分支。**MUST NOT** 動使用者既有的 worktree（先 `git -C <它> status` 看是否有未提交修改，有就更要避開）。
3. **`node_modules`**（約 1.2 GB）：優先 APFS clone，12 秒：
   ```bash
   cp -cR <別的 worktree>/Abyssinian/node_modules <新>/Abyssinian/node_modules
   ```
   前提：`git diff <來源 HEAD> <目標 HEAD> -- Abyssinian/package-lock.json` 為空。否則 `npm ci`（用 `run_in_background` 並看 log，不要 `sleep` 卡住）。
4. **只用 `npm run <script>`，不寫死副檔名**：同一個專案在不同提交裡 `dev`、`fault-proxy` 等腳本可能是 `.mjs` 或 `.ts`（本機未推送的提交與 PR head 就不同）。

---

## Step 0b：資料來源與環境

Abyssinian 的資料來自中台（JavaCat）。驗收要能「新增員工看版本變化」「故意讓一筆不同」，所以資料來源要可控。三種環境：

| 環境 | 何時用 | 寫入限制 | 備註 |
|---|---|---|---|
| **本機＋假中台（預設）** | 絕大多數條件 | 假中台隨便寫（只存在於自己的行程） | `scripts/harness.sh`，35 秒起好；細節見 `references/local-harness.md` |
| dev（`pos-center-development.wonderpet.asia`） | 條件明確要求真環境（真實推播、真實 S3、真實機台名稱） | 寫 dev 中台**須同意** | 週一至週五 09:00–19:00 才開機；**後台只允許總部與 IT 的出口 IP**，驗收者的出口（含 VPN）要先請 IT 填入；機台端點需要**真實令牌**，由使用者提供，只用環境變數 `DEVICE_TOKEN`，腳本不簽發 |
| staging | 1000 台壓測 | 同 dev | 取決於 S2 是否已部署 |

**進入 Step 4 前，逐條判斷這條條件需要什麼環境**，在報告裡寫出來。能在本機驗的就在本機驗；只有真環境才能驗的（FCM 真實推播、S3 的 Range 行為、真實機台名稱對照），且尚未取得授權或令牌時，標 ⚠️ 並說明卡在哪裡。

### 起本機環境

```bash
cd <worktree>/Abyssinian
H=<本 skill 路徑>/scripts/harness.sh
bash "$H" up        # 約 30 秒；失敗會明確指出卡在哪一步（結束碼對照見 references/local-harness.md）
bash "$H" status    # 各行程、各埠、Server 就緒檢查
```

- 埠預設：資料庫 54391、Server 3191、假中台 3192、控制 3193（`ABY_*_PORT` 可改）。**埠被占用時腳本停下並列出占用者（pid、指令、cwd、已執行時間）**：不要結束它、不要自行換埠，確認它不屬於本次驗收後再決定。
- 已有**不是本腳本產生的** `.env` 時拒絕覆蓋（要覆蓋用 `ABY_FORCE_ENV=1`）。
- **重開環境必須先 `clean`**：`down` 只停行程不清資料，殘留的資料庫與假中台的新種子不一致，驗收結果會悄悄失真，所以 `up` 看到殘留資料會拒絕（結束碼 8）。細節見 `references/local-harness.md`。
- 就緒證據：`status` 的輸出、`/api/v1/health/ready` 回 `{"status":"ok","database":"ok"}`、Worker 日誌出現 `dataset_compile_round_published`，且各行程的 cwd 都是這個 worktree。

---

## Step 1：驗收範圍界定（RD-8489 校驗）

1. 使用者給卡號。若就是 `RD-8489`：停止並回報「RD-8489（POS-S）本身是 Epic，請指定其底下的具體 ticket」。
2. 用 Atlassian MCP 的 `getJiraIssue`（`mcp__plugin_atlassian_atlassian__getJiraIssue` 或 `mcp__claude_ai_Atlassian__getJiraIssue`，擇一），cloudId `f338306a-4b54-421e-9209-2e9f451c67f7`，**用 `view: "evidence"`**：預設的 compact 檢視不回 `parent`，會被誤判成「沒有父系」。一次抓齊 `description`、`customfield_10030`（驗收條件）、`customfield_10057`（規格）、`customfield_10266`（討論紀錄）、`customfield_10058`（參考資料）。呼叫失敗 → 停止並回報「查無 `<卡號>` 或沒有讀取權限」。
3. **沒有 `parent`**（evidence 檢視也沒有）→ 停止並回報「⚠️ 無法確認範圍」，不可當拒絕。
4. `parent.key === "RD-8489"` 且卡名以 `[Abyssinian]` 開頭 → 繼續。卡名是 `[Ragdoll]` → 回報「屬於 Ragdoll 機台端，本 SOP 不適用」。
5. 其他父系：若這張卡本身是子任務，對 `parent.key` 再查一次（只遞迴一次）；否則明確拒絕：「此卡的父系 Epic 是 `<key>`（`<summary>`），不是 POS-S（RD-8489），本 skill 無法驗收」。

**已實測**（2026-11-23）：RD-8484 的 `parent.key` 為 `RD-8489`（`POS-S`），卡片類型「任務」。RD-8489 底下共 20 張卡：`[Abyssinian]` 開頭 16 張（含導覽卡 RD-8479、A1、B1～B4、T1～T3、H1、F1、F2、S1、S2 與兩張未編號卡），`[Ragdoll]` 開頭 4 張（E1～E3 與 E3 前置）。查詢用 `parent = RD-8489`。

---

## Step 2：解析驗收條件（`customfield_10030`）

Jira MCP 依檢視回不同格式，**兩種都要能解析**：compact 檢視是 markdown（`- [ ] …`），evidence 檢視是 HTML（`<li data-type="task-item"><input type="checkbox"> …</li>`）。

- 每個清單項目（`- [ ]`／`<li>`）是一條獨立條件，**忽略勾選狀態**；`#` 標題是分組不是條件；縮排延續行屬同一條；沒有清單時每個空行分隔的段落是一條。
- 一條條件用「；」串了多項檢查時仍算一條，但**逐項判定、逐項寫依據**。
- 去除前後空白與零寬字元。解析出 0 條 → **停止並回報**，不可從規格或討論紀錄發明條件編號。

**MUST 完整讀其他欄位**：`description`、`customfield_10057`（規格）、`customfield_10266`（討論紀錄，含設計決定與「待確認」）、`customfield_10058`（參考資料）。它們常提到驗收條件沒單獨列出的行為（例如「機台個別資料不放在資料集裡」「過渡期不開放客制」）。這類不佔正式條件編號，在報告以「補充查核」列出並同樣判定。

**Abyssinian 驗收條件的三種寫法**，判定方式不同：

| 寫法 | 例 | 怎麼驗 |
|---|---|---|
| 「在後台…看到…」 | 後台比對頁選一間門市看差異 | Playwright 操作並截圖 |
| 「工程團隊回報：…附紀錄，**由 PM 認可**」 | 模擬機台下載、舊版本內容、續傳 | **獨立重現它所說的事實並留紀錄**。「由 PM 認可」是人的步驟：報告標「待 PM 認可」，驗收者不替 PM 認可 |
| 規模或環境條件 | 1000 台壓測、staging | 本機只能驗腳本可用；真正判定要在該環境，沒有就 ⚠️ |

---

## Step 3：diff-first，並確認功能已實作

1. **取得變動**：`gh pr view <編號> --json files` 或 `git diff <merge-base>..<head> --stat`（疊式 PR 以 PR 的 base 為準）。對照 PR 描述的調整內容。
2. **找核心模組**：`src/lib/dataset/`（登記表、編譯、manifest、device-api）、`src/worker/dataset/`（編譯迴圈、發佈、推播）、`src/app/api/v1/device/`（機台端點）、`src/app/admin/`（後台頁面）、`src/lib/source/` 與 `src/worker/`（B1 來源讀取）。
3. **逐條確認條件對應的功能在這個 PR 是否真的存在** —— 這是 Abyssinian 驗收最容易漏的一步，因為卡片常分多個 PR 交付。做法：
   - 後台功能：看選單（`src/app/admin/_lib/menu.ts`）、頁面（`src/app/admin/**/page.tsx`）、API（`src/app/api/v1/admin/`）；
   - 資料表：`src/database/prisma/schema/*.prisma`；
   - 旗標：`GET /api/v1/admin/settings` 列出的 key。
   找不到的，**不要硬試**，記下證據（grep 結果、選單截圖、API 清單），Step 6 標 ⚠️（見判定規則）。
4. **跑 PR 自己的測試**作為獨立證據（CI 只跑 `typecheck`、`lint`、`test:unit`，**不跑整合測試**，所以整合測試要在本機跑，`DEPLOY.md`「合併前的自動化缺口」列了至少要涵蓋的目錄）：
   ```bash
   R=<本 skill 路徑>/scripts/run-with-timeout.py
   python3 -I "$R" 900 300 <log 檔> -- npm run test:unit          # 約 8 秒
   python3 -I "$R" 900 300 <log 檔> -- npm run test:integration   # 約 2.5 分鐘；內嵌資料庫自己找空埠，不會與驗收環境衝突
   ```
   以 `run_in_background` 執行。**判定一律看 log 的 `Test Files … passed` 與最後一行 `EXIT=… REASON=finished`**，不看結束碼（npm 與 vitest 串起來後不可靠）。
5. 讀 PR 新增測試的 `describe`／`it` 標題，常是最準確的行為說明。

---

## Step 4：找操作依據

依序嘗試，找到能回答「怎麼驗」的來源就停：

1. 專案內 `DEPLOY.md` 的「**驗收方式（dev）**」表：逐條列出做法與狀態，是這個專案自己維護的操作依據；另有「已知與規格不同」與「待實測」。
2. `docs/dataset-device-api.md`：機台端點契約（回應碼、標頭、Range、manifest 結構）。
3. `references/admin-pages-and-playwright.md`：後台各頁與驗收條件的對照、Playwright 操作要點。
4. `petpetgo-llm-wiki`（先讀 `wiki/index.md` 找 Abyssinian 區塊）。
5. 規格與討論紀錄、PR 新增的測試標題。

都查過仍找不到 → ⚠️ 無法驗證（找不到操作依據），不憑空猜。

---

## Step 5：實機操作

### 5.1 造異動（對假中台）

```bash
bash "$H" upsert <表名> '<表頭 JSON>' ['<表身 JSON>']
# 例：改名一筆活動、新增一位員工
bash "$H" upsert pospromotion '{"name":"P-NORTH-01","displayName":"北區限定買二送一（驗收改名）"}'
bash "$H" upsert __user__ '{"name":"U004","displayName":"驗收新增員工","level":"STAFF","disabled":false}'
```

- Worker 靠 `_updatedAt` 偵測異動（`upsert` 預設會刷新）。異動到新版本發佈，本機設定下實測 **10～35 秒**（讀取間隔 30 秒＋緩衝 10 秒＋編譯 5 秒）。**用輪詢 manifest 的版本等，不要固定 `sleep`**。
- **要驗「舊版本不受影響」之類的條件，必須在造異動前先記下當時的版本與 sha256**，異動後才有東西比。
- 要驗「故意讓一筆不同會被比對報告列出」：造異動後**立刻**觸發比對（趕在 Worker 讀到並重編之前），否則專屬檔會追上來、差異消失。

### 5.2 機台視角

在 `Abyssinian/` 目錄執行，**目標一律用 `http://localhost:<埠>`**。zsh 不會對未引號的變數斷詞，要重複使用的指令寫成函式：

```bash
peek() { node_modules/.bin/tsx .local-data/accept/device-peek.mts --base-url http://localhost:3191 "$@"; }
peek --store 001 manifest                      # 25 個資料集的版本、筆數、大小、sha256
peek --store 001 dataset pospromotion          # 下載、驗 sha256、列出每筆活動的 name
peek --store 001 dataset pospromotion --version 1   # 舊版本
peek shared-diff 001,002,003                   # 各門市共用條目是否逐字相同、各門市專屬版本
peek --store 001 --device POS00101 get /api/v1/device/stores/002/manifest   # 守門：預期 403
npm run machine:sim --silent -- --base-url http://localhost:3191 --store 001 --sign-local-device POS00101
npm run machine:sim --silent -- --base-url http://localhost:3191 --store 002 --sign-local-device POS00201 --interrupt-after 50000   # 續傳
```

模擬機台會同步、校驗、回報（寫入「機台回報」，後台同步狀態頁據此顯示），並印出「全程是否出現任何儲存空間網址」。`device-peek` 只印名稱、版本、筆數、大小與 sha256 前 8 碼，不印令牌與機密欄位；專屬資料集含門市密鑰欄位，**任何報告與畫面都不得出現它的值**。

### 5.3 後台畫面（Playwright）

操作鐵則（每一條都是實測踩過的）：

- **瀏覽器一律用 `http://localhost:<埠>`，不用 `127.0.0.1`**：Next 開發模式擋掉跨來源的 dev 資源請求，用 `127.0.0.1` 開頁面會永遠停在「載入中…」（Server 日誌會有 `Blocked cross-origin request`）。`DEPLOY.md` 也有同樣記載。
- **每次輸入或點擊後，舊的 `ref` 會失效**（按鈕狀態變了就換快照），用 `browser_find` 重新取 ref，不要重複用舊的。
- `browser_wait_for` 只給 `text`；同時給 `time` 會先睡滿時間再檢查。
- **截圖檔名要在 Playwright 的允許範圍內**：只能寫進 `<petpetgo 主 checkout>/.playwright-mcp/` 之下（相對路徑如 `.playwright-mcp/RD-xxxx-c2-xxx.png`）；指到暫存目錄的絕對路徑會被拒絕。檔名帶卡號與條件編號。**每張截圖都要用 `Read` 親自看過**才算證據。
- 這個目錄由所有 session 共用且不在 git 追蹤範圍：收尾時只刪**自己這次產生**的檔案（檔名帶卡號、或時間戳在起環境之後的 `page-*.yml`、`console-*.log`），不要清整個目錄。
- Console 出現 `favicon.ico` 404 是雜訊（用 `localhost` 時只有這一個）；HMR 的 WebSocket 錯誤代表你用了 `127.0.0.1`。
- 「門市比對」頁按下開始後，Worker 約 2 秒就完成，**畫面要約 15 秒才更新**（前端輪詢）。先用 `GET /api/v1/admin/store-compare/latest?storeNo=<門市>` 確認報告已產生，再等畫面或重新載入頁面、輸入門市編號即可立刻看到最近一份報告。
- 「資料集同步」頁會定時輪詢（2026-11-19 的記錄約每 30 秒）；操作後要看最新狀態就重新載入頁面，不要等它自己更新。

### 5.4 背景日誌（推播、編譯）

Worker 日誌在 `.local-data/accept/run/worker.log`，一行一筆 JSON。常用事件：

| 事件 | 代表 |
|---|---|
| `dataset_compile_round_published` | 這一輪發佈了新版本：`publishedSharedCount`、`changedStoreCount` |
| `dataset_push_log_only`（`topic` 是門市編號、`data.manifestEtag`） | 沒有 FCM 金鑰時，推播只寫日誌；`manifestEtag` 應等於同時間 manifest 的 ETag |
| `dataset_notify_summary` | `audience` 是 `all_stores`（共用資料集變動）或 `changed_stores`（只有專屬資料集變動） |

本機沒有 FCM 金鑰，所以**「機台收到推播」只能驗到日誌層**；真實推播要在 dev 且金鑰到位後驗（`DEPLOY.md` 有「金鑰到位後必驗清單」）。

### 5.5 壓測探針

`npm run probe:dataset -- --base-url http://localhost:3191 --stores 001,002 --sign-local --machines 4 --max-seconds 60`。本機只能確認腳本可用：它在規模不足時**正確回報「總判定：無法判定」、結束碼 3**。1000 台的真正判定只能在 staging，且還要 `--offline-url` 量離線交易收件延遲（取決於 T1 是否完成）。

---

## Step 6：判定與回報（預設不留言 Jira）

每條條件**只能**標三態之一，不發明第四態：

- ✅ **通過** — 實際結果與條件一致。
- ❌ **不通過** — 實際結果與條件不符（功能存在但行為不對）。
- ⚠️ **無法驗證** — 找不到操作依據；需要的環境或令牌或授權拿不到；**條件對應的功能在這個 PR 尚未實作**；規模或環境條件本機驗不了。

**多項條件與部分驗證**：一條條件含多項檢查時逐項判定。任一項 ❌ → 整條 ❌；沒有 ❌ 但有項目無法驗證 → 整條 ⚠️，並在判定依據逐項寫出哪些 ✅、哪些 ⚠️ 與原因（例如「後台顯示 ✅；『收到推播』只驗到日誌層」）。

**功能尚未實作的條件**：預設標 ⚠️（尚未實作），附證據（選單、API、資料表、旗標的檢查結果），並在報告開頭「待確認」寫明：「這些條件對應的功能不在本 PR 範圍時，屬預期；若屬於本次驗收範圍，則實質上不通過」，由使用者判斷。**不替使用者決定範圍，也不為了湊 ✅ 而用別的功能替代**；用別的觸發方式驗到相同的架構性質時，作為補充證據寫出來，但不改變該條的判定。

**證據等級**（與三態並列，每條在「驗證方式」欄標明）：

| 等級 | 說明 |
|---|---|
| 實機·本機假中台 | 真實 Server、Worker、資料庫與資料集編譯，來源資料是假中台的種子資料；報告 MUST 寫出種子與異動內容 |
| 實機·dev／staging | 真環境（需授權） |
| 自動化測試 | PR 的單元或整合測試，附 `Test Files`／`Tests` 摘要 |
| 論證 | 程式碼追蹤，無實機畫面 |

### 回報骨架

```markdown
## RD-XXXX 驗收結果（PR #N，head <sha 前 10 碼>，<驗收日期>）

### 環境
本機＋假中台（worktree、埠、起環境耗時）；種子資料；未使用 dev／staging 的原因

### 待確認
- <使用者要拍板的事：例如某些條件是否在本 PR 範圍、PR 狀態（draft、mergeable）>

| # | 驗收條件 | 結果 | 驗證方式（證據等級） | 判定依據 |
|---|---|---|---|---|
| 1 | <條件文字> | ✅ 通過（待 PM 認可） | 機台視角＋後台畫面（實機·本機假中台） | <版本、sha256、截圖檔名、日誌事件> |

### 補充查核
| 路徑 | 結果 | 判定依據 |

### 自動化測試
單元：N 個檔案、M 個測試通過（log 路徑）；整合：…

### 環境副作用
建立的 worktree、`.env`、`.dev-db`、`.local-data`、埠；對共用資料的寫入（本機假中台為「無」）

### 其他觀察（不影響判定）
<Info 等級：UI 更新延遲、文件與實作不符…>

### 建議留言草稿
<給使用者決定是否留言；寫給 PM 看得懂的業務語言，不放程式碼與函式名>
```

**預設 MUST NOT 呼叫任何 Jira 寫入工具**（留言、編輯、轉換狀態、附件）。把表格與草稿回報給使用者，等使用者明確要求才留言。

---

## Step 7：驗收結束後清理環境

只在使用者明確表示「驗收完成」或要求清理時才做，不要在 Step 6 回報完就自動清掉。

1. 關閉瀏覽器：`browser_close`。
2. **只用 PID 檔停止自己起的行程**：`bash "$H" down`（SIGTERM；只處理 cwd 在本專案目錄底下的殘留，並確認四個埠都釋放）。**MUST NOT** 用 `pkill`／名稱樣式找行程：使用者常在別的 worktree 跑自己的 `npm run dev`。
3. `bash "$H" clean` 移除 `.env`、`.dev-db`、`.local-data`（worktree 之後要整個移除時可省略）。
4. 刪除自己產生的 `.playwright-mcp/` 檔案（見 5.3）。
5. 確認 worktree 沒有自己的內容：`git status --short` 為空 → 在**主 checkout** 用絕對路徑 `git worktree remove <路徑>`（`node_modules` 與建置產物是 ignore 檔，不需要 `--force`；git 拒絕時先看原因）。`--detach` 建的沒有本機分支要刪。
6. 核對：`git worktree list` 不再有該 worktree；**使用者既有 worktree 的 `git status` 與動手前一致**；`lsof` 確認埠都釋放。

---

## 檔案索引

| 檔案 | 何時讀 |
|---|---|
| `references/local-harness.md` | Step 0b 起環境、種子資料與預期結果、時序參數、出錯時的排除 |
| `references/admin-pages-and-playwright.md` | Step 5.3 操作後台前：各頁、對應 API、與驗收條件的關係 |
| `references/rd-8484-playbook.md` | 驗收 RD-8484（B4 門市客制與專屬檔發佈）時：逐條做法、預期與實跑結果 |
| `scripts/harness.sh` | 啟停本機環境（`prepare`、`up`、`status`、`upsert`、`down`、`clean`） |
| `scripts/fake-world.mts`、`scripts/fake-javacat-multi.patch` | 假中台與種子資料（由 `harness.sh` 複製使用） |
| `scripts/device-peek.mts` | 以本機令牌檢視機台端點 |
| `scripts/run-with-timeout.py` | 限時執行 `npm run test:*` |
