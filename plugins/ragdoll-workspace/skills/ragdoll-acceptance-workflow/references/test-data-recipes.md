# 測試資料食譜

Step 5.1「盤點測試資料」用。原則：**先找現成資料，找不到就用模擬資料法（`memory-fixture.md`），不要為了造情境去寫共用的 dev 中台或本機 DB。**

## 盤點流程

1. 逐條驗收條件寫下需要的資料：哪種會員／寵物／月卡／單據、哪個門市、什麼狀態（已付款／未付款、已使用…）。
2. 查 dev 中台（見下）與本機 DB 找現成資料；把「資料 → 要驗的條件」對應起來，一筆資料往往能同時驗好幾條。
3. 找不到的邊界資料（空值、缺欄位、查無對應）→ 模擬資料法。
4. **留意門市維度**：機台的門市決定哪些資料算「本店／他店」。例如「帶入未付款銷售」清單只列本店單據；本機 `pos_store` 只保留目前門市一列，查不到他店名稱，他店名稱得靠中台回填的 `*_displayName` 欄位。

## 查 dev 中台（`mcp-wonderpet-table-local` / javacat）

- **先** `javacat_switch_environment(env: "dev")`（對應 `RAGDOLL_TARGET_ENV=development`）。唯讀查詢；`javacat_insert`／`javacat_update` 不要用來造驗收資料（寫共用 dev 中台，刪不掉，而且背景 session 的寫入會被互動式確認擋下）。
- 查詢要帶 `selects` 縮小欄位，必要時 `skipLines`。中台會回 join 出來的 `*_displayName`（如月卡的 `allowStore_displayName`、`petName_displayName`），可直接用來核對畫面。
- 已實測的查詢陷阱（遇到 500 先縮窗口／換寫法，不要直接判「無法驗證」）：
  - 用 join 出來的欄位（如 `couponEventName_type`）當篩選條件時，不要同時疊加日期範圍，容易觸發後端 500；改成先撈較大 `limit` 再本地過濾。
  - 對表身欄位用 `in` 比對**空字串**會 500。
  - `javacat_summarize` **不支援依表身欄位分組**（`groupBy` 一個表身欄位會得到空 `keys`）。
  - 對表身欄位用 `nin` 會把「根本沒有該表身」的單也撈進來。
  - 想找「某欄位為空／特殊值」的資料，常常 dev 根本沒有；與其繼續試，直接轉模擬資料法。
- dev 中台會有別人留下的殘留資料（例如舊的未付款單），其中可能有破壞性操作入口（「取消銷售」）——不要碰。

## 本機 DB 現成資料

- **商品的會員價／定價**：唯讀 DB 的 `item` 表，`price`＝會員價、`label_price`＝定價，兩者不同的商品才適合測「會員價 vs 定價」。條碼欄位是 `bar_code`（不是 `barcode`）。
- **本機歷史單**：`offline_sale`（`sale_kind = 'SERVICE'` 為美容單）可撈 `member_name`，join `offline_sale_lines_service_items` 取 `pet_name`，常常就有現成的測試會員與寵物。
- 本地唯讀 DB **沒有會員資料**：會員查詢一律打遠端 GraphQL，不是「沒同步」，是設計上不落地。要找真實會員／優惠券用 javacat。

## 紙本發票條碼（換購／退貨驗證）

UI 會要求刷入 19 碼一維條碼，格式 `{民國年3碼}{結束月份2碼}{發票號碼10碼}{來源末4碼}`（結束月份是雙月配號期別的月份，公式見 `next/lib/utils/invoice/egui-period.ts` 的 `getEGUIPeriod` 與 `invoice-verify-panel.tsx`），不是把發票號碼原文送出就能過。本地 `issue_invoice` 表可查到 `egui_no`。

**「來源末 4 碼」不是固定抓本地 `offline_sale.name`**：它是 UI 元件當下渲染這筆單據的 `sale.body.name`。透過「商品／銷售查詢(退換貨)」或「美容銷售查詢」對話框查到的單子，來源是**遠端 GraphQL**（`PosSaleRecord`），`body.name` 是**中台編號**（畫面上「銷售編號」欄位，如 `0032609100003`），和本地 `offline_sale.name`（`S260910174454643` 格式）是兩組字串，末 4 碼不同。已實測：用本地單號末 4 碼失敗，改用畫面上的「銷售編號」末 4 碼才成功。**組碼前先用截圖或 `electron_get_page_structure` 確認畫面上實際顯示的銷售編號**，不要憑 SQL 結果推算。

## 跨發票配號週期的情境

**不要竄改系統時間**，改查本地 DB 找現成的舊期別資料：

```sql
SELECT name, issue_invoice_name, paid_at, total FROM offline_sale
WHERE invoice_type = 'EGUI' AND issue_invoice_name IS NOT NULL
ORDER BY paid_at ASC LIMIT 10
```

找一筆 `paid_at` 落在兩個雙月期別之前的已完成單，直接對它操作退貨，就會自然觸發跨週期折讓邏輯，不必動時鐘或資料。

## 商品與美容的退換貨是兩套獨立入口

- 商品側：功能選單「商品」頁籤的「銷售查詢(退換貨)」（`useReturnExchangeStore`）。
- 美容側：要先切到功能選單「美容」頁籤，才有獨立的「銷售查詢(退換貨)」（`useSalonReturnExchangeStore`）。
- 兩者**不會依原始單的 `sale_kind` 自動分派**：在商品入口對 `sale_kind = 'SERVICE'` 的美容單退貨，若退的剛好是搭賣的實體商品行，寫入的 `offline_return.sale_kind` 會是 `'ITEM'`，不會走到美容側的 `resolveOfflineReturnName`（已實測踩過）。
- 要驗美容側邏輯，先確認要退的是**純服務單**（`SELECT COUNT(*) FROM offline_sale_lines_items WHERE offline_sale_name = s.name` 為 0），並從「美容」頁籤入口進入。

## 要不要完成結帳

完成結帳／付款會建立 dev 銷售單、開錢櫃，Mac 開發環境還可能真的送列印，需使用者明確允許（通常只允許一筆現金結帳；刷卡機、One 碼、宜睿不要真的送出）。條件不是非要看到落地資料時，優先用論證或模擬資料法。真的完成結帳後，用本機 `offline_sale*` 與中台 `posservicesale` 等核對落地，並在報告的「環境副作用」列出建立的單號。
