# 中台（JavaCat）對照組查詢

目的：回答「**只有這一台壞，還是同店／多店都壞？**」。這是判定「程式 vs 線路」最便宜、也最有鑑別力的證據：
同一份軟體堆疊下，別的機台正常，就不像是共通的程式缺陷。

**只做唯讀查詢**（`javacat_find`／`javacat_count`／`javacat_summarize`）。不寫入、不更新。
工具用法與登入流程見 `anthropic-skills:mcp-wonderpet-table-usage`；先 `javacat_switch_environment` 設 `production`。
所有查詢都要帶日期範圍（`_createdAt`），否則會掃全表拖垮服務。`archived` 用預設 `NORMAL`。

## 1. 每台機台的「正常刷卡 vs 手 KEY」比例

付款資料在 `possale` 的表身 `payments`；欄位 `type`：`CREDIT`＝刷卡機正常刷卡、`CREDIT_OFFLINE`＝店員手 KEY 的離線信用卡。
門市欄位 `storeName`（3 碼）、機台欄位 `configName`（5 碼，門市＋2 碼）。

### 1.1 先列出該店有哪些機台（不含表身條件，最穩）

```
javacat_summarize
  table: possale
  filters: [{ bodyConditions: [
      { fieldName: "_createdAt", valueType: "DATE", operator: "gte", date: "2026-10-01T00:00:00+08:00" },
      { fieldName: "_createdAt", valueType: "DATE", operator: "lt",  date: "2026-10-07T00:00:00+08:00" },
      { fieldName: "storeName", valueType: "STRING", operator: "in", string: "098" } ] }]
  groupBy: ["body.configName"]
  aggregations: [{ fn: "count", alias: "sales" }, { fn: "sum", field: "body.total", alias: "total" }]
```

### 1.2 每機台的手 KEY 與正常刷卡筆數

**多間店一次查**：每間店一個 FilterGroup（頂層陣列＝OR），每組都帶表身條件：

```
javacat_summarize
  table: possale
  filters: [
    { bodyConditions: [ <日期 gte>, <日期 lt>, { fieldName: "storeName", ..., string: "207" } ],
      lineFilters: [{ lineName: "payments", lineConditions: [
        { fieldName: "type", valueType: "STRING", operator: "in", string: "CREDIT_OFFLINE" } ] }] },
    { bodyConditions: [ <日期 gte>, <日期 lt>, { fieldName: "storeName", ..., string: "192" } ],
      lineFilters: [ … 同上 … ] },
    …
  ]
  groupBy: ["body.storeName", "body.configName"]
  aggregations: [{ fn: "count", alias: "offline_sales" }, { fn: "sum", field: "body.total", alias: "offline_total" }]
```

把 `CREDIT_OFFLINE` 換成 `CREDIT` 再查一次；再把日期換成**發病前基準窗口**各查一次，共 4 組數字
（發病後／發病前 × 正常／手 KEY）。基準窗口取「發病前 9～14 天」（與發病後天數相近）；發病後取到查詢當下。

> **踩雷：`summarize` 帶 `lineFilters` 要「單發、依序」執行。** 同時並行多個會全部回 `fetch failed`
>（連線其實正常）。`javacat_count` 帶 `lineFilters` 則可以並行。

### 1.3 只有單一機台時用 count

```
javacat_count
  table: possale
  filters: [{ bodyConditions: [ <日期 gte>, <日期 lt>,
      { fieldName: "storeName",  valueType: "STRING", operator: "in", string: "090" },
      { fieldName: "configName", valueType: "STRING", operator: "in", string: "09011" } ],
    lineFilters: [{ lineName: "payments", lineConditions: [
      { fieldName: "type", valueType: "STRING", operator: "in", string: "CREDIT_OFFLINE" } ] }] }]
```

### 1.4 美容單在另一張表

本機 `offline_sale.sale_kind = 'SERVICE'` 的單（美容）上傳後在 **`posservicesale`**，不在 `possale`。
本機手 KEY 筆數對不上中台 `possale` 時，差額多半是這個；用同樣條件對 `posservicesale` 再 `count` 一次
（它的付款表身同樣叫 `payments`、欄位同名，條件寫法完全相同）。

## 2. 怎麼讀比例

| 發病後手 KEY 比例 | 解讀 |
|---|---|
| ≥ 50% 且正常刷卡幾乎歸零 | **崩潰式故障**（例：5 筆正常／58 筆手 KEY＝92%） |
| 5%～20%，且發病前就偏高或逐步上升 | 值得追：可能是同類故障的早期，向門市索取該機台的回報包比對 ECR log |
| 1%～5% | 多半背景雜訊或正當的離線使用（例如刷卡機不支援的銀聯卡），單看中台無法判斷 |
| < 1% 或 0 | 正常 |

- **背景雜訊**：正常機台每週也會有約 1 次零星通訊失敗（可用 ECR log 在發病前的失敗率驗證），所以個位數筆數不足以說「也有同樣問題」。
- **量太小不判斷**：總刷卡筆數 < 10 的機台，比例沒有意義（例如 1／3）。
- **手 KEY 筆數是代理指標，且是下限**：它漏掉「POS 失敗、店員重刷後成功」的案例，也包含正當的離線使用。
- 若 PM／門市說「多間店都有」，**逐機台算比例**再回覆，不要只回「有手 KEY」。

## 3. 這台機台走不走 POSAgentDotNet（`pospilot`）

回報包的 `offline-readonly.snapshot.db` 已有種子名單（`pos_pilot`、`pos_pilot_lines_features`、`pos_pilot_lines_stores`），
`triage.py` 會直接判斷。要以**正式站為準**時查中台 `pospilot`：

```
javacat_find
  table: pospilot
  filters: [{ bodyConditions: [{ fieldName: "_createdAt", valueType: "DATE", operator: "gte", date: "2026-08-01T00:00:00+08:00" }],
              lineFilters: [{ lineName: "stores", lineConditions: [
                { fieldName: "storeName",  valueType: "STRING", operator: "in", string: "090" },
                { fieldName: "configName", valueType: "STRING", operator: "in", string: "11" } ] }] }]
  selects: ["_id", "body.name", "body.startAt", "body.endAt", "body.version", "lines.features"]
```

- `stores` 行是「門市 3 碼」＋「機台 2 碼」**分開存**（`090`＋`11`＝`09011`）。
- 兩個條件在同一個 `lineConditions` 內是**逐行比對**；已用不存在的組合（如 `090`＋`55`）做陰性對照確認回 0 筆。
- 命中且 `features.keyword = POSAgentDotNet`、現在時間在 `startAt`～`endAt` 內、刷卡機類型不是 `TSB` → 走代理程式。
- 種子名單**生效日**要與發病日比：相差 3 天內，優先懷疑「切換代理程式」本身。

## 4. 結果怎麼記進報告

用一張表：機台｜發病前（正常／手 KEY）｜發病後（正常／手 KEY）｜手 KEY 比例｜判讀。
並註明**查詢時間**（中台資料會隨時間增加，數字會與回報包快照不同）。

## 5. 查不到的事（要明說「未查證」）

- **他機的 Ragdoll、代理程式、ECR 版本**：中台與回報包都沒有。可以說「同在種子名單」，**不能說「同版本」**。
- **他機那幾筆手 KEY 的原因**：要讀付款表身的 `reconcileInfo` 才看得到，但那是卡號欄位，不要為了好奇去讀；需要時請使用者決定。
- **發病當時 09011 的 Ragdoll 版本**：log 已輪替就無法證實，見 SKILL Step 3。
