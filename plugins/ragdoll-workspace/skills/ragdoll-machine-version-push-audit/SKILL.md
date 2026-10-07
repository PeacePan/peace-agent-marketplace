---
name: ragdoll-machine-version-push-audit
description: >
  稽核 Ragdoll POS-R 現役機台（`posconfig` 機台編號 1X 開頭，如 11／12／13，即機1／機2／機3）的兩件事：
  ① 每台目前安裝的 Ragdoll 版本（`posversionhash` 最新上報）② 有沒有確實登入裝置推播 ID（`posinventorydevice.fcmPushID`）。
  內含萬達中台 MCP 的查詢範本（`posversionhash` 全表 20 萬列以上，不照範本查會逾時或被截斷）、
  一支逐台合併三份清單的腳本，以及固定的報告格式。
  只要使用者問到：Ragdoll 版本分佈、哪些機台還沒升到最新版、機台目前跑哪一版、1X 機台、機台有沒有登入推播、
  fcmPushID／裝置推播 ID、強制更新推播前想先知道哪些機台收得到、推播收不到的機台名單，
  或提到 posversionhash／posinventorydevice／posconfig 的版本或推播檢查，即使沒有說「稽核」也要使用本 skill。
---

# Ragdoll 機台版本與推播 ID 稽核

## 要回答的問題與判定口徑

| 用語 | 本 skill 的判定 | 為什麼這樣判 |
|---|---|---|
| 1X 開頭的機台 | `posconfig.body.no`（2 碼機台編號）以 `1` 開頭，常見 11～14 | Ragdoll 機台編號慣例是機1＝11、機2＝12…；0X 開頭是 Maltese 機台 |
| 目前有設定 | `posconfig` 未封存且 `status = ACTIVE` | INACTIVE 是已停用機台，列入分母會把正常停用誤報成異常；停用台數另外附註 |
| 機型 | `CASH_REGISTER`（收銀機）與 `SALON_WORKBENCH`（美容工作台）**都納入**，報告標示組成 | 兩者都跑 Ragdoll、都會登錄推播；使用者只要收銀機時，Step 1 加 `mode in CASH_REGISTER` 即可 |
| 最新 Ragdoll 版本 | `posversionhash` 中 `platform = RAGDOLL`，該機台 `lastEnterAt` 最大的那一列的 `posVersion`（附 `commitHash`） | Ragdoll 每換一個版本就**新增一列**（一台機台約 10 列），升版後舊版本的列不再更新，所以 `lastEnterAt` 最大者才是現在跑的版本；Maltese 的列必須排除 |
| 確實登入推播 ID | `posinventorydevice` 有 `mode = POS`、未禁用、`fcmPushID` 非空的紀錄，且 `posConfigName` 對得上該機台 | 只有「有紀錄且有 token」才推得到；盤點機（`INVENTORY`）不對應機台 |

使用者若給了不同口徑（例如連 INACTIVE 也要、別的機台前綴），照使用者的做，並在報告開頭寫明實際採用的口徑。

## 三張表如何對應

串接鍵是**收銀機編號** `posconfig.body.name`（5 碼＝門市 3 碼＋機台 2 碼，例如 `21112`＝211 門市 12 號機）。

| 表 | 用到的欄位 | 串到 posconfig 的方式 |
|---|---|---|
| `posconfig` 門市機台檔 | `name`（5 碼）、`no`（2 碼）、`status`、`mode` | — |
| `posversionhash` 機台版本資訊 | `configName`、`platform`、`posVersion`、`commitHash`、`lastEnterAt` | `configName` ＝ `posconfig.name` |
| `posinventorydevice` 裝置推播管理檔 | `posConfigName`、`mode`、`disabled`、`fcmPushID` | `posConfigName` ＝ `posconfig.name` |

注意 `posconfig.no` 只有 2 碼；另外兩張表存的是 5 碼 `name`，所以篩 1X 時要換成正規式 `^[0-9]{3}1[0-9]$`。

## 前置

1. 本流程只讀。只用 `javacat_find`／`javacat_count`（補查時加 `javacat_summarize`），不呼叫 insert／update。
2. `javacat_*` 若是延遲載入的工具，先用 ToolSearch 載入 schema；再 `javacat_switch_environment({ env: 'production' })`（使用者指定其他環境就照辦）。不熟中台 MCP 的 filter 語法時，先載入 `mcp-wonderpet-table-usage` skill。
3. 建一個專屬暫存資料夾（例如 `W=$(mktemp -d)`），三份清單與報告都放這裡。
4. 取時間（`find` 的 `date` 要 ISO 字串；裸 `date -u` 在中文系統會輸出非 ISO 的文字，一定要帶格式）：
   - 現在：`date -u +%Y-%m-%dT%H:%M:%SZ`（之後給腳本的 `--now`）
   - **`T3`＝3 天前當天 00:00 UTC**：macOS `date -u -v-3d +%Y-%m-%dT00:00:00.000Z`；Linux `date -u -d '3 days ago' +%Y-%m-%dT00:00:00.000Z`
   - 90 天前同理（`-v-90d`／`'90 days ago'`），補查時用。

下面所有查詢的 `filters` 都帶一個極早的 `_createdAt gte 2015-01-01` 或 `lastEnterAt` 時間窗，因為中台守則要求每次 find／count 都要有日期條件。

這份稽核需要把約 1,200 列從查詢結果抄成清單檔（機台 ~370、版本 ~430、裝置 ~370）。抄寫是最大的出錯來源，所以請**每頁抄完就立刻用 heredoc 附加寫入**（`cat >> "$W/xxx.txt" <<'EOF'`），逐列忠實照抄，不要省略、不要重排，抄完靠 Step 4 核對。

## 流程

### Step 1：機台清單（posconfig）

共用條件（記為 `C1`）：`archived: 'NORMAL'`，且
```json
{ "filters": [{ "bodyConditions": [
  { "fieldName": "_createdAt", "valueType": "DATE",   "operator": "gte",  "date": "2015-01-01T00:00:00.000Z" },
  { "fieldName": "no",         "valueType": "STRING", "operator": "like", "string": "^1" },
  { "fieldName": "status",     "valueType": "STRING", "operator": "in",   "string": "ACTIVE" }
]}] }
```

1. `javacat_count`（`C1`）→ 記下總數 `N_cfg`（2026-10-07 為 374）。再把 `status` 換成 `INACTIVE` 數一次，只用來在報告附註停用台數。
2. `javacat_find`（`C1`）分頁抓清單：
   `multiSort: [{ field: 'body.name', direction: 1 }]`、`selects: ['body.name', 'body.mode']`、`skipLines: true`、`limit: 190`，`offset` 依序 0、190、380…直到 `hasMore` 為 false。
3. 每頁抄成一行一台，附加到 `$W/configs.txt`：`<name> <mode>`（例如 `21112 CASH_REGISTER`）。

### Step 2：每台的最新 Ragdoll 版本（posversionhash）

共用條件（記為 `C2`）：`archived: 'NORMAL'`，且
```json
{ "filters": [{ "bodyConditions": [
  { "fieldName": "lastEnterAt", "valueType": "DATE",   "operator": "gte",  "date": "<T3>" },
  { "fieldName": "platform",    "valueType": "STRING", "operator": "in",   "string": "RAGDOLL" },
  { "fieldName": "configName",  "valueType": "STRING", "operator": "like", "string": "^[0-9]{3}1[0-9]$" }
]}] }
```

1. `javacat_count`（`C2`）→ 記下 `N_ver`（約 370）。
2. `javacat_find`（`C2`）分頁：
   `multiSort: [{ field: '_id', direction: 1 }]`、`selects: ['body.configName', 'body.posVersion', 'body.commitHash', 'body.lastEnterAt']`、`skipLines: true`、`limit: 120`，`offset` 0、120、240…。
   用 `_id` 排序是為了分頁穩定：機台上報會不斷更新 `lastEnterAt`，若依它排序，翻頁途中列會移位而漏列或重複。「最新」交給腳本取最大值，不靠查詢排序。
3. 每頁抄成 `$W/versions.txt`，每列一行：`<configName> <posVersion> <commitHash> <lastEnterAt>`。

### Step 3：推播 ID（posinventorydevice）

共用條件（記為 `C3`）：`archived: 'NORMAL'`，且
```json
{ "filters": [{ "bodyConditions": [
  { "fieldName": "_createdAt",    "valueType": "DATE",   "operator": "gte",  "date": "2015-01-01T00:00:00.000Z" },
  { "fieldName": "posConfigName", "valueType": "STRING", "operator": "like", "string": "^[0-9]{3}1[0-9]$" },
  { "fieldName": "mode",          "valueType": "STRING", "operator": "in",   "string": "POS" }
]}] }
```

1. 三個 `javacat_count`：
   - `C3` → `N_dev`（全部 POS 裝置列）
   - `C3` ＋ `{ fieldName: 'fcmPushID', valueType: 'STRING', operator: 'like', string: '.' }` → `N_fcm`（有推播 ID 的列）
   - `C3` ＋ `{ fieldName: 'disabled', valueType: 'BOOLEAN', operator: 'in', boolean: true }` → `N_dis`（禁用的列）
2. `javacat_find`（`C3`）：`multiSort: [{ field: '_id', direction: 1 }]`、`selects: ['body.posConfigName']`、`skipLines: true`（表身 `topics` 很大，一定要跳過）、`limit: 250`。抄成 `$W/devices.txt`，每列一行：`<posConfigName>`。
3. 若 `N_dev > N_fcm`：有些裝置列沒有推播 ID，需要知道是哪幾台。再用 `C3` ＋ `fcmPushID like '.'` 查一次（同樣的 selects／limit），抄成 `$W/devices-fcm.txt`；腳本會把「在 devices 內、卻不在 devices-fcm 內」的機台標成「有裝置但無推播ID」。若 `N_dev = N_fcm`，不需要這個檔。
4. 若 `N_dis > 0`：用 `C3` ＋ `disabled in true` 查出禁用的機台，在 `devices.txt` 對應列後面加一個空白和 `D`（例如 `21113 D`）。

### Step 4：核對抄寫結果（合併前）

腳本是在對**抄寫下來的資料**做判斷，抄漏或抄錯一列就會變成假的異常，所以先核對再合併：

1. **行數**：`configs.txt` ＝ `N_cfg`；`versions.txt` ＝ `N_ver`；`devices.txt` ＝ `N_dev`。數法：`grep -vc '^#' 檔案`。
2. **資料漂移**：機台每小時都在上報，抄寫期間資料會變（升版會多一列）。把 `C2` 重 count 一次；若比 `N_ver` 大，用 `offset` 抓尾頁的新列，在 `versions.txt` 另起一行 `# 漂移新增` 註解後附加，並把 `N_ver` 更新為新的 count，最後在報告附註「查詢期間有 N 台機台升版／上報」。
3. **內容**（行數只能抓漏列，抓不到抄錯版本或時間）：對前兩三個版本各做一次 `javacat_count`（`C2` ＋ `posVersion in <版本>`），再用
   `awk '!/^#/ && NF{c[$2]++} END{for(v in c) print v, c[v]}' "$W/versions.txt"` 統計抄寫檔，兩邊一致才算抄對。

### Step 5：合併成報告（腳本）

```bash
python3 -I <本 skill 目錄>/scripts/join_report.py \
  --configs "$W/configs.txt" --versions "$W/versions.txt" --devices "$W/devices.txt" \
  [--devices-fcm "$W/devices-fcm.txt"] --now "<現在 ISO 時間>" --csv "$W/ragdoll-machines.csv"
```

腳本逐台檢查 `configs.txt` 內的每一台，輸出：總覽（含機型組成）、版本分佈、以及這些需要關注的機台——
3.1 無版本紀錄、3.2 落後最高版（依版本分組）、3.3 未上報、3.4 未登入推播、3.5 疑似降版、3.6 裝置紀錄重複、
3.7 不在機台清單內卻仍有資料（常見於 INACTIVE 卻仍在上報，值得提醒維運確認狀態是否設錯）。
報告最上面若出現「輸入檔有格式問題」的警告，代表抄寫有漏欄或機台編號不是 5 碼，先修正再往下。
「未上報」的切點是「`--stale-days`（預設 3）天前當天 00:00 UTC」，與 Step 2 的 `T3` 同一條線，所以窗內的機台不會被誤標。
若最高版只有 1～2 台，腳本會提醒那可能是測試機或預先發佈版（例如測試門市機台），此時要向使用者確認真正的正式最新版，再重新判讀「落後」。

### Step 6：補查沒有版本紀錄的機台

報告的 3.1 若有機台，用報告最後（第 4 節）給的正規式補查：把 Step 2 的 `T3` 換成 90 天前、`configName like` 換成 `^(a|b|c)$`，其餘同 `C2`，先 count 再分頁（`limit: 120`），把結果在 `versions.txt` 另起一行 `# 補查` 註解後**附加**，再重跑 Step 5。補查後仍沒有的機台，就是 90 天內沒上報過 Ragdoll 版本（尚未安裝、長期關機，或還在跑 Maltese）。

要分辨它們是不是還在跑 Maltese，可對這批機台做一次 `javacat_summarize`：`table: 'posversionhash'`、`groupBy: ['body.configName']`、`aggregations: [{ fn: 'count', alias: 'rows' }]`，filters 為 `lastEnterAt gte <14 天前>`、`platform in MALTESE`、`configName like ^(a|b|c)$`；有出現的機台代表還在用 Maltese，沒出現的代表兩個平台都沒有近期上報。這只是判斷有無，不需要抄寫。

### Step 7：抽查後回報

挑 2～3 台（至少含一台異常機台）直接查證報告內容：

- 版本：`javacat_find`，`table: 'posversionhash'`，filters 為 `lastEnterAt gte 2015-01-01`、`platform in RAGDOLL`、`configName in <機台>`，`multiSort: [{ field: 'body.lastEnterAt', direction: -1 }]`、`selects: ['body.posVersion', 'body.commitHash', 'body.lastEnterAt']`、`skipLines: true`、`limit: 3`；第一列應與報告一致。
- 推播：`javacat_find`，`table: 'posinventorydevice'`，filters 為 `_createdAt gte 2015-01-01`、`posConfigName in <機台>`，`selects: ['body.posConfigName', 'body.mode']`、`skipLines: true`；筆數應與報告（無／有／重複）一致。
- 補查附加的列數應等於補查 count。

核對都過了再依下方「回報格式」寫給使用者。

## 查詢陷阱（上面的寫法就是為了避開這些）

- **`like` 是正規式比對，沒加 `^` 就是「包含」**：`no like '1'` 會把 01～05 也撈進來（633 台 vs 正確的 467 台），所以前綴一律用 `^`。
- **`posversionhash` 全表超過 20 萬列**（Maltese 每 30 分鐘輪詢累積而成），而且每台機台每個版本一列（近 30 天 1X 機台就有 3,789 列）。不加 `platform` ＋ `lastEnterAt` 時間窗，`summarize` 掃到 5 萬列就截斷、`find` 容易逾時；也不能隨便取一列當版本。
- **`summarize` 的 `max` 對日期欄位回傳 null**，無法拿來求最新時間；要靠 `find` 抓列、由腳本取最大值。
- **`nin` 與 `like` 都不會匹配欄位為空（null）的列**：因此無法用過濾直接撈出「沒有推播 ID」的列，只能用 `N_dev` 對 `N_fcm` 比對、或用 devices 與 devices-fcm 兩份清單相減。`disabled nin true` 更是陷阱，POS 裝置的 `disabled` 幾乎都是空值，會被整批排除；要找禁用就用 `disabled in true`。
- **一台機台可能有多筆裝置紀錄**（換機後舊紀錄未清），報告的「裝置紀錄重複」就是在抓這個；它不影響「有沒有登入」的判定，但會讓推播重複送到舊裝置。
- **`limit` 的取值**：190／120／250 是依單列大小選的，實測整頁（最大約 27k 字元）都完整回傳。若回應出現「已截斷」字樣就把 `limit` 調小；不要自行往上調，並在每頁確認回傳列數與 `offset` 累加吻合。`responseFormat: 'markdown'` 對 `find` 沒有縮小效果。
- **`fcmPushID` 是裝置憑證**：只用 `like '.'` 判斷有無，不要 select 出來、不要貼進對話或報告。
- 「有登入推播 ID」只代表登錄過 token，不保證現在送得到（token 可能已失效）。要驗證送達需實際發送，例如中台 `posinventorydevice` 的強制更新推播，不在本 skill 範圍。

## 回報格式

用繁體中文，依序給出，數字全部來自腳本報告：

1. **口徑與資料時間**：環境、採用的判定口徑（含機型組成）、查詢時間（UTC 或台北時間擇一並標明）。
2. **結論**：3～4 句話，例如「ACTIVE 1X 機台 N 台，其中 X 台在近 3 天有上報，目前最高版 1.2.1 佔 Y%；Z 台尚未登入推播 ID」。
3. **版本分佈表**：版本／commit／台數／占比，標出最高版。
4. **需處理的機台**：依腳本 3.1～3.6 分組，每台寫明機台編號與原因。「落後最高版」用依版本分組、一行列出該版全部機台的形式，**一律全列**（這最貼近「各台裝哪一版」的問題）；其他表格超過 20 台時只列前 20 台，其餘指向 CSV 路徑。3.1 與 3.4 常是同一批機台，合併說明即可，不要重複列兩次。
5. **附註**：INACTIVE 台數、時間窗、補查結果（含 Maltese 判斷）、資料漂移、核對時發現的出入。

完整的逐台明細放在 `$W/ragdoll-machines.csv`（含 BOM，Excel 可直接開），回報時告知路徑。
