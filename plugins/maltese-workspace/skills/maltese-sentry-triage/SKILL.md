---
name: maltese-sentry-triage
description: 把 WonderPet POS（Sentry 專案 pos / Maltese）的 Sentry 錯誤分流成可行動結果——從一堆噪音中辨識出真正該修的程式 bug、開成 RD Jira 漏洞卡、其餘封存降噪。內含 org/project/cloudId/Epic/必填自訂欄位等專案常數與踩雷細節，少了會卡關或重工。調查 Sentry、查 POS/Maltese 某版本錯誤、把 Sentry issue 開成 Jira 卡、或批次封存 Sentry 噪音時觸發。
---

# WonderPet Sentry 調查 → Jira 開卡 → 封存 工作流程

這份 skill 把「Sentry 撈錯誤 → 分流出真正的程式 bug → 比對既有 Jira → 開卡 → 封存噪音」整條管線變成可重複執行的流程。價值在於：(1) 一堆專案專屬常數（org / project / cloudId / Epic / 自訂欄位 ID）；(2) 幾個不知道就會卡住或產生大量浪費的細節（自訂欄位要 ADF、查詢 100 筆上限、Jira 查詢輸出爆量）。

五個階段可整條跑，也可單獨用其中一段。**Phase 5b（開 Jira 卡）與 Phase 5c（批次封存）都會對外部系統造成不可逆/外顯的變更，動手前一定要先讓使用者確認**（見「安全規範」）。

---

## 環境常數（WonderPet 專屬，先記住）

| 項目 | 值 |
|------|-----|
| Sentry org slug | `wonderpet-dy` |
| Sentry region URL | `https://us.sentry.io` |
| Sentry 專案（POS / Maltese） | `pos`（另有 `ragdoll-local-pos`） |
| Jira 站台 / cloudId | `wonderpet.atlassian.net` / `f338306a-4b54-421e-9209-2e9f451c67f7` |
| Jira 專案 key | `RD` |
| Sentry 票掛靠的 Epic | `RD-6`（所有 `[Sentry]` 系列票都掛這個 Epic） |
| 每版區間的母票命名 | `Sentry Maltese <版本區間>`（例：`Sentry Maltese 1.5.10 ~ latest`） |
| Bug issue type 名稱 | `漏洞`（untranslatedName = Bug，id 10008） |
| 必填自訂欄位：正確行為 | `customfield_10059`（建立漏洞時必填，**值要 ADF**） |
| 必填自訂欄位：驗收條件 | `customfield_10030`（建立漏洞時必填，**值要 ADF**） |

工具來自兩個 MCP：Sentry（`mcp__...sentry__*`）與 Atlassian（`mcp__...Atlassian__*`）。多數要先用 `ToolSearch` 載入 schema 再呼叫。

---

## Phase 1 — 確認身份與鎖定範圍

1. **（選用）確認 Sentry 身份**：`execute_sentry_tool(name="whoami", arguments={})`。團隊共用帳號常見是 `rd_fe@wonderpet.asia`，不是個人帳號 — 使用者問「我是什麼身份」時用這個。
2. **找出版本範圍**：使用者常說「1.5.10 ~ latest」。用 `find_releases(organizationSlug="wonderpet-dy", projectSlug="pos")` 取得版本清單與最新版（清單依建立時間排序，最上面那個就是 latest）。把「X ~ latest」展開成實際版本陣列，例如 latest 是 1.5.13 → `["1.5.10","1.5.11","1.5.12","1.5.13"]`。
3. 每個 release 物件的 `New Issues` 數量可先讓使用者對影響規模有概念。

---

## Phase 2 — 撈 issue 並去重

Sentry 的 issue 本身已是分組（同類事件聚合成一個 group），所以「列出不重複的 issue」就是列出這些 group，不需要再自己去重。

**多版本聯集查詢**用 Sentry 的陣列語法：
```
search_issues(
  organizationSlug="wonderpet-dy",
  projectSlugOrId="pos",
  query='release:["1.5.10","1.5.11","1.5.12","1.5.13"] is:unresolved',
  limit=100, sort="freq")
```
- `sort="freq"`：依事件頻率排序，先看到影響最大的。
- 視需要加 `is:unresolved` 過濾掉已 ignored 的長期噪音。

### 100 筆上限是硬限制 —— 用「迴圈」而非分頁

`search_issues` 最多回 100 筆且**沒有 cursor 可翻頁**。當總數逼近/等於 100，代表還有更多被蓋住。處理大批時用這個模式：先對手上這批做動作（例如封存），被處理掉的 issue 會跌出 unresolved 清單，於是**重新查詢就會浮現下一批**。重複「查 100 → 處理 → 再查」直到剩下的就是要保留的那幾筆為止。每輪都 `log` 一下還剩幾筆，避免讓使用者以為一次就掃完。

---

## Phase 3 — 過濾：分出「真正的程式 bug」

核心判讀原則：**光看錯誤訊息語意就能判定是人為操作、資料/設定、或基礎設施造成的，就過濾掉；只留下指向 Maltese 前端程式邏輯本身的。** 這一步是這份 skill 最有價值的人類判斷，務必逐筆讀訊息。

**留下（疑似/確定程式 bug）：**
- 內部未預期例外被吞掉：訊息像「執行過程發生錯誤，原因：」後面**空白** → 程式丟出未捕捉的例外。
- JS runtime 例外：`Cannot read properties of undefined (reading 'xxx')`、`TypeError: ... is not a function`。
- GraphQL 欄位拼錯：`Cannot query field "tokenReNew" ... Did you mean "tokenRenew"`。
- payload 組裝缺值：`lineFields[N].string should be defined`（前端組 batchUpdate 時 STRING 欄位無值卻沒轉成 NULL）。

**過濾掉：**
- **業務規則驗證**（系統正確擋下不合法操作）：已付款不能改回已取消、已退款不得再退款、此銷售單已有客訂單、缺必填欄位、折扣碼已使用/無效、料件不存在或數量大於客訂數量、金額對不上、會員 XXXX 不開放客訂。
- **資料 / 設定問題**：「請找商品部」、未設定篩選器、設定檔缺、唯一值重複、清帳紀錄不存在。
- **基礎設施 / 外部 API**（非前端程式碼，也非操作）：`Failed to fetch (localhost:900x)`（門市端發票機/錢櫃/列印外掛）、`http status 500/503`、伺服器忙碌、`operation was interrupted`、`jwt expired` / 「授權代碼不存在」（token 失效連鎖）、`Failed to call Magento API`（兌換）、Mongo `Write Conflict`（後端並發）。

輸出時建議分三層呈現：
① 真正/疑似程式 bug（要追的）
② 後端/基礎設施（非前端碼、也非操作，需要時另查）
③ 已過濾（操作/資料/業務驗證）。讓使用者一眼看出該丟給工程的是哪幾筆。

> 註：團隊長期方向是「人為輸入錯誤的訊息應降級為 warning、不送 Sentry」（見 RD-7376 / RD-3300 類票），所以這類過濾與 PM 的分類思路一致。

---

## Phase 4 — 比對 RD Jira 既有票

開卡前**一定**先查 RD 上是否已有對應票，避免重複開卡。RD 已有系統化的 Sentry 分流：每版區間一張母票（`Sentry Maltese X ~ latest`），底下/同 Epic（RD-6）拆出 `[Sentry] …（POS-XXX）` 子票。

```
searchJiraIssuesUsingJql(
  cloudId="f338306a-4b54-421e-9209-2e9f451c67f7",
  jql='project = RD AND (parent = RD-6 OR text ~ "Sentry") ORDER BY updated DESC',
  fields=["summary","status","issuetype","updated","parent"],
  maxResults=60, responseContentFormat="markdown")
```

### 避免輸出爆量（重要踩雷）

`searchJiraIssuesUsingJql` 預設會把每張票的 `description` 全帶回來，幾十張票就會超過工具輸出上限被存成檔案。對策：
1. **限制 `fields`** 只取 `summary/status/issuetype/updated/parent`，通常就夠對照。
2. 若仍超量被存成檔案，**用 python 解析**那個 JSON 檔（schema 是 `{issues:{nodes:[{key, fields:{...}}]}}`）抽出 key/summary/status —— 環境通常**沒有 `jq`**，不要用 jq。

把每筆 Sentry issue 對到既有票，標出狀態（待辦/進行中/完成/已取消），找出真正還沒開卡的缺口。

---

## Phase 5a — 根因確認與「回歸 vs 兄弟 bug」判定

開卡前若要確認根因（尤其要判斷是不是某張已修票的回歸），抓單一 issue 細節：
```
get_sentry_resource(url="https://wonderpet-dy.sentry.io/issues/POS-XXX")
```
重點看 **`network traffic history`**：裡面的 `failMessage` 常會揭露「後端其實回了一句業務訊息，但前端把它吞掉並崩在 `.body`/`.lines`」這種真實因果。再用 `Read`/`grep` 對照 Maltese 原始碼確認該程式路徑。

**回歸判定準則**（不要只看「訊息一樣」就說是回歸）：
- **路徑是否相同**：同樣是 `reading 'body'`，但「取消客訂單」與「提領」是不同 effect/檔案，修了前者不等於修了後者。
- **時間線**：若該 issue 的 `first seen` 早於那張已修票的建立/完成日，它就是**先前就存在的兄弟 bug**，不是回歸（回歸 = 已修好的東西又壞）。

---

## Phase 5b — 為真正的 bug 開立 RD Jira 漏洞卡

**動手前先把草稿（標題＋內文）給使用者確認**（見安全規範）。確認後：

```
createJiraIssue(
  cloudId="f338306a-4b54-421e-9209-2e9f451c67f7",
  projectKey="RD",
  issueTypeName="漏洞",
  parent="RD-6",
  summary="[Sentry] <一句話描述>（POS-XXX）",
  contentFormat="markdown",
  description="<見下方建議結構>",
  additional_fields={
    "customfield_10059": { "type":"doc","version":1,"content":[
      {"type":"paragraph","content":[{"type":"text","text":"<正確行為：修好後應有的行為>"}]}]},
    "customfield_10030": { "type":"doc","version":1,"content":[
      {"type":"paragraph","content":[{"type":"text","text":"<驗收條件：在 X 情境下操作 → 1) ... 2) ... 3) Sentry POS-XXX 不再新增事件>"}]}]}
  })
```

**必踩的兩個雷：**
1. `漏洞` 類型**必填**「正確行為」(`customfield_10059`) 與「驗收條件」(`customfield_10030`)，少了會回 `400 ... 是必要項目`。
2. 這兩個欄位**只吃 ADF**（Atlassian Document Format）。傳純字串會回 `欄位值不是有效的 ADF 內容`。一定要用上面那種 `{type:"doc",version:1,content:[{type:"paragraph",content:[{type:"text",text:"..."}]}]}` 物件。

**建議的 description 結構**（markdown）：
```
## Sentry
- Issue：[POS-XXX](https://wonderpet-dy.sentry.io/issues/POS-XXX)
- 影響：N users / M events，first/last seen，release 區間
- 路徑：/checkout 或 /salon 等

## 現象
（操作員看到什麼）

## 根因（已對照原始碼/payload 確認）
（file:line + network history 佐證）

## 建議修法方向
（最小修正方向）
```

**慣例與禁忌：**
- 標題一律 `[Sentry] <描述>（POS-XXX）`，與既有票一致。
- 程式碼註解裡**不要**寫 ticket 編號（RD-XXXX）；ticket 屬於 PR/commit/卡片層級。
- 已在程式碼修好的 issue，語意上應該 resolve 而非開新卡（除非要追蹤）。

---

## Phase 5c — 批次封存噪音（archive until escalating）

詢問使用者是否要「只留某幾筆、其餘封存到下次再出現」：封存 = Sentry 的 `ignored`。

```
update_issue(
  organizationSlug="wonderpet-dy",
  issueId="POS-XXX",
  status="ignored",
  ignoreMode="untilEscalating",   # 升級才浮現；最常用、最佳降噪
  reason="<一句封存原因，會貼到該 issue 的 activity feed 供追溯>")
```

**封存模式選擇**（先跟使用者確認語意）：
- `untilEscalating`（建議）：發生頻率落在預測範圍內就持續隱藏，出現異常爆量才重新浮現。長期降噪最佳。
- `untilOccurrenceCount` + `ignoreCount=1`：下次任一事件就立刻浮現。最貼近字面「下次再出現」，但同一筆被再碰一次就跳回來。

**執行要點：**
- 一次只能封存一筆（工具是 per-issue）。大批時在同一輪發多個平行呼叫，但留意 Sentry 偶發 `504`，逐筆檢查回應、失敗的重試。
- 搭配 Phase 2 的「100 筆迴圈」：封存一批 → 重查 → 再封存，直到 `is:unresolved` 只剩要保留的那幾筆，最後再查一次確認。
- `reason` 會在每筆 issue 留一則 comment；批次時用同一句精簡原因即可（兼顧可追溯與不過度洗版）。

---

## 安全規範

- **Phase 5b 開卡、Phase 5c 封存都是外顯/不可逆操作**：動手前要嘛使用者已明確下令（「開卡」「封存」），要嘛先把「要對哪些、用什麼模式/欄位」攤給使用者確認。範圍或模式有歧義時用提問釐清（例：封存模式要 untilEscalating 還是 untilOccurrenceCount？有對應 Jira 票的要不要一起封存？）。
- 不要主動 `git push`；本流程不涉及 commit/push。
- 比對與調查（Phase 1–4、5a）是唯讀的，可放心執行。

---

## 踩雷筆記（速查）

- `search_issues` 上限 100 且無分頁 → 用「處理→重查」迴圈，別以為一次掃完。
- `searchJiraIssuesUsingJql` 預設帶回完整 description → 輸出爆量；限制 `fields`，必要時 python 解析存檔（無 `jq`）。
- 建 `漏洞` 必填 `customfield_10059`（正確行為）＋ `customfield_10030`（驗收條件），且**只吃 ADF**。
- `release:["a","b"]` 陣列語法可一次查多版本聯集。
- 「回歸」要看路徑是否相同 + first-seen 是否早於已修票，別只憑訊息相同。
- Sentry `update_issue` 偶發 504，逐筆確認、失敗重試。
- 共用 Sentry 帳號是 `rd_fe@wonderpet.asia`，非個人帳號。
