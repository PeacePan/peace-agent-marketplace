---
name: ragdoll-printable-coupon
description: >
  Ragdoll 小白單（紙本優惠券）列印功能完整知識庫。涵蓋結帳後的資格篩選邏輯、
  活動型小白單的 petParkCoupon 記錄建立與券號回填、pos_printable_coupon 資料表結構、
  sync 同步機制、IPC 列印呼叫，以及 Next.js 層的 filterAndBuildPrintableCoupons
  工具函式與 useSale action。

  以下情況必須參考此文件再動手：
  - 修改或擴充小白單優惠券的篩選條件（滿額/門市群組/目標消費者/料件篩選）
  - 修改活動型小白單的 petParkCoupon 建立或券號回填邏輯
  - 修改小白單的列印格式（topText、barcodeContent、titles、memo）
  - 修改 pos_printable_coupon SQLite schema 或 sync config
  - 在結帳流程中調整小白單列印的觸發時機
  - 修改 offline_sale_lines_printable_coupons 寫入時機或邏輯（列印後/補印後）
  - 撰寫小白單相關的單元測試或整合測試
  - 理解 IPC 資料流（Next.js store → Electron 主進程 → 發票機）
---

# Ragdoll 小白單（紙本優惠券）列印知識庫

## 業務概覽

小白單（紙本優惠券）是結帳完成後由發票機自動列印的紙本優惠券，用於吸引顧客下次回購。

**觸發時機**：結帳流程完成發票列印後，自動依消費資格篩選並列印（最多 3 張）。

**列印條件**：
- 消費滿額（saleTotal）：銷售總額必須達到設定門檻
- 門市群組（storeGroups）：目前門市必須在允許群組內
- 目標消費者（targetConsumer）：MEMBER / NON_MEMBER / ALL
- 料件篩選器（filters）：購買商品須符合設定的料件條件
- 有效期（startAt / endAt）：由 sync config 在查詢時過濾，確保只同步當日有效資料

**兩種小白單類型**：
- **一般小白單**：無 `couponEventName`，直接從本地資料組裝列印
- **活動型小白單**：有 `couponEventName`，需在線建立 petParkCoupon 記錄取得券號後列印；建立失敗時略過，由後續優惠券遞補至 3 張

**不支援的情境（此版本）**：
- 首次消費（onlyFirstConsumption）、累積消費（accumulationSaleTotal）、列印上限（printLimit）的會員歷史查詢

---

## 架構概覽

```
[結帳完成]
  ↓
[checkout-button.tsx]
  print-invoice 步驟完成後
  → saleActions.printPrintableCouponsForSale()
      ↓
  [use-sale.ts: printPrintableCouponsForSale action]
    1. getPosConfig() → 取得門市名稱
    2. filterAndBuildPrintableCoupons() → 篩選 + 活動券建立 + 組裝
       ├─ 一般小白單：直接組裝 PrintableCouponInput
       └─ 活動型小白單（有 couponEventName）：
          ├─ fetchCouponEvents() → 批次查詢 petparkcouponevent
          ├─ preparePrintableCouponInput() → 建立 petParkCoupon + 取得 code
          ├─ 成功：以 code 回填 barcodeContent + 活動標題
          └─ 失敗：略過該張，由後續優惠券遞補至 3 張
    3. printInvoice({ mode: '優惠券', coupons: [...] }) → IPC
        ↓
    [ragdollAPI.devices.invoice.print]
    → Electron 主進程 → 發票機 HTTP POST /print
    4. ragdollAPI.db.update('offline_sale', { lines: { printableCoupons: [...] } })
        → 寫入 offline_sale_lines_printable_coupons
        → 失敗時 throw（提示作廢再補印）
```

**銷售單 printableCoupons 表身更新**：
列印成功後，由 `printPrintableCouponsForSale`（Step 4）立即寫入本地 `offline_sale_lines_printable_coupons`。上傳離線銷售單時（`upload-offline-sales.ts`），`convertOfflineSalePrintableCoupons` 將此表身資料帶入 GraphQL payload，由 `insertPosSale` 一併傳給中台。補印時（`useReprintCoupon`）亦會在列印後嘗試補寫此表身，確保紀錄完整。

**資料同步流程（背景排程）**：
```
GraphQL posprintablecoupon → sync config → pos_printable_coupon（本地 SQLite）
```

---

## 關鍵檔案路徑

| 功能 | 路徑 |
|---|---|
| **SQLite 主表 Schema** | `electron/main/database/tables/readonly/pos_printable_coupon/pos_printable_coupon.sql` |
| **SQLite 門市群組表身** | `electron/main/database/tables/readonly/pos_printable_coupon/pos_printable_coupon_lines_store_groups.sql` |
| **SQLite 料件篩選器表身** | `electron/main/database/tables/readonly/pos_printable_coupon/pos_printable_coupon_lines_filters.sql` |
| **SQLite 列印備註表身** | `electron/main/database/tables/readonly/pos_printable_coupon/pos_printable_coupon_lines_coupon_print_memo.sql` |
| **TypeScript 型別定義** | `electron/main/database/tables/readonly/pos_printable_coupon/index.ts` |
| **同步設定** | `electron/main/jobs/sync-data/configs/posprintablecoupon.ts` |
| **IPC 型別（PrintableCouponInput）** | `electron/main/types/ipc-devices.ts` |
| **篩選與組裝** | `next/lib/utils/printable-coupon/filter.ts` |
| **活動券建立（petParkCoupon）** | `next/lib/utils/printable-coupon/create.ts` |
| **補印** | `next/lib/utils/printable-coupon/reprint.ts` |
| **useSale action** | `next/lib/stores/checkout/sale/use-sale.ts`（`printPrintableCouponsForSale`） |
| **結帳按鈕整合** | `next/app/summary/components/checkout-button.tsx` |
| **整合測試** | `test/next/integration/utils/printable-coupon/filter.test.ts` |

---

## 資料庫 Schema（`pos_printable_coupon`）

### 主表欄位

| 欄位 | 型別 | 說明 |
|---|---|---|
| `name` | TEXT PK | 優惠券編號 |
| `print_channel` | TEXT | 列印適用渠道 |
| `display_name` | TEXT | 活動名稱 |
| `cooperation_partner` | TEXT | 配合廠商 |
| `priority` | TEXT | 優先級（用於排序，升冪） |
| `start_at` | INTEGER | 起始日期（Unix timestamp） |
| `end_at` | INTEGER | 結束日期（Unix timestamp） |
| `sale_total` | REAL | 消費滿額門檻（0 表示無限制） |
| `only_first_consumption` | INTEGER | 限定首次消費（0/1） |
| `accumulation_start_at` | INTEGER | 期間累積消費開始日期 |
| `accumulation_end_at` | INTEGER | 期間累積消費結束日期 |
| `accumulation_sale_total` | REAL | 期間累積消費金額門檻 |
| `target_consumer` | TEXT | 目標消費者（MEMBER/NON_MEMBER/ALL） |
| `coupon_event_name` | TEXT | 優惠券活動編號（有值時為活動型小白單） |
| `print_limit` | INTEGER | 列印上限（此版本略過） |
| `need_collect` | INTEGER | 是否回收（0/1） |
| `coupon_top` | TEXT | 優惠券頂部文字 |
| `barcode_content` | TEXT | 條碼內容 |
| `barcode_type` | TEXT | 條碼樣式（enum） |
| `title1/2/3` | TEXT | 標題文字（各三組） |
| `title1/2/3_bold` | INTEGER | 粗體（0/1） |
| `title1/2/3_font_size` | TEXT | 字體大小（SMALL/MEDIUM/LARGE） |
| `title1/2/3_align` | TEXT | 對齊方式（LEFT/CENTER/RIGHT） |
| `expiration_start_at` | INTEGER | 有效期限開始日期（Unix timestamp） |
| `expiration_end_at` | INTEGER | 有效期限結束日期（Unix timestamp） |

### 表身

- `pos_printable_coupon_lines_store_groups`：門市群組（groupName、effect）
- `pos_printable_coupon_lines_filters`：料件篩選器（filterName、name、brand、category 等）
- `pos_printable_coupon_lines_coupon_print_memo`：列印備註（text）

---

## Sync Config（`posprintablecoupon.ts`）

```typescript
{
  localTable: 'pos_printable_coupon',
  remoteTable: 'posprintablecoupon',
  getFindParams: async () => ({
    filters: [{ body: { startAt: { $lte: today }, endAt: { $gt: today } } }],
    selects: ['body', 'lines.storeGroups', 'lines.filters', 'lines.couponPrintMemo'],
  }),
  recordsFilter: 依門市群組篩選,
  recordMapper: 遠端 Date → 本地 Unix timestamp、boolean → 0/1,
  recordCleaner: 清除不適用當前門市的資料,
}
```

---

## 篩選與組裝邏輯（`filter.ts`）

`filterAndBuildPrintableCoupons()` 回傳 `FilteredPrintableCoupon[]`（含 `input`、`couponName`、`couponEventName`）。

執行步驟：

1. **查詢**：`ragdollAPI.db.list('pos_printable_coupon')` + `ragdollAPI.db.list('pos_store_group')`
2. **取得料件資訊**：`fetchItemsInformation(itemNames)`
3. **篩選**（每張優惠券依序檢查）：
   - `printChannel` 非空且不是 `STORE` → **排除**
   - 不在 `startAt` ~ `endAt` 時間範圍 → **排除**
   - `saleTotal > total` → **排除**
   - `filterByStoreGroups()` 回傳 false → **排除**
   - 有會員 + `targetConsumer === 'NON_MEMBER'` → **排除**
   - 無會員 + `targetConsumer === 'MEMBER'` → **排除**
   - `filters` 有值但無商品命中 `isItemInFilterCondition` → **排除**
4. **排序**：依 `priority` 升冪 → `startAt` 降冪 → `_createdAt` 降冪
5. **依序組裝（最多 3 筆，活動券失敗時遞補）**：
   - **一般小白單**：直接組裝 `PrintableCouponInput`
   - **活動型小白單**（有 `couponEventName`）：
     - 需要會員且在線才處理，否則略過
     - 呼叫 `preparePrintableCouponInput()` 建立 petParkCoupon 記錄並取得券號
     - 成功：以券號回填 `barcodeContent`，加入活動標題（券號、手機末三碼、折扣文字）
     - 失敗：`console.error` 後 `continue`，由後續優惠券遞補

---

## 活動型小白單建立邏輯（`create.ts`）

`preparePrintableCouponInput()` 為活動型小白單建立 petParkCoupon 記錄並回傳含券號的列印資料。

執行步驟：

1. 根據活動設定計算有效期（`resolveExpirationRange`）與折扣金額
2. `ragdollAPI.graphql.insert({ table: 'petparkcoupon', data: [...] })` 建立記錄
3. `ragdollAPI.graphql.find({ table: 'petparkcoupon', filters: [...] })` 查詢生成的 `code`（券號）
4. 以 `code` 組裝活動型標題並合併原始列印資料回傳

活動型標題格式（prepend 在小白單自定義 title 之前）：
```
[券號]       — SMALL, CENTER, bold
[手機末三碼] — SMALL, CENTER, bold
[折扣文字]   — MEDIUM, CENTER, bold
```

**前置條件**：由 `filter.ts` 的 `fetchCouponEvents()` 預先批次查詢 `petparkcouponevent`，以 Map 傳入。

---

## 補印邏輯（`reprint.ts`）

補印與首次列印的關鍵差異：使用既有券號，不重新產生。

`fetchCouponReprintData()` → `buildCouponPrintItems()` → `buildCouponPrintRequest()`

1. 查詢 `petparkcoupon`（依 memberName + saleName + type=PAPER）
2. 查詢 `petparkcouponevent`（依 couponEventName + issueType=PRINTABLE_COUPON）
3. 查詢 `posprintablecoupon`（依 couponEventName）
4. 以既有 `code` 組裝列印資料（不建立新記錄）

---

## 列印 IPC 格式

```typescript
// InvoicePrintRequest（mode='優惠券' 時）
{
  mode: '優惠券',
  coupons: PrintableCouponInput[],
  // 以下欄位對優惠券模式無作用，但 type 要求必須傳
  total: 0, tax: 0, items: [], payments: [],
  storeName: 'PRINT_COUPON', configNo: 'PRINT_COUPON',
  invoiceNo: '', randomCode: '', buyerTaxCode: '', sellerTaxCode: '',
  createdAt: new Date().toISOString(),
  shouldOpenCashDrawer: false,
}

// PrintableCouponInput 結構
{
  topText: string,          // couponTop
  barcodeType: string,      // enum
  barcodeContent: string,   // 一般券：來自 DB；活動券：petParkCoupon.code
  titles: PrintableCouponTitle[],  // 活動券會 prepend 券號/手機/折扣文字
  expirationStartAt: Date,  // Unix timestamp 轉換
  expirationEndAt: Date,
  memo: string[],           // couponPrintMemo.text 陣列
}
```

---

## 結帳流程整合

`checkout-button.tsx` 的步驟順序：

```
1. create-sale    建立銷售紀錄
2. print-invoice  列印發票
2.5. print-coupon 列印小白單（發票機在線才執行，失敗不阻斷後續）
3. open-drawer    開啟錢櫃
4. clear-cart     清除購物車
```

**設計原則**：
- 小白單列印失敗只更新步驟狀態為 `error`，不 `return` 或 `throw`
- 發票機離線時與 print-invoice 同樣設為 `skipped`
- `couponsPrinted: boolean` 記錄於 `SaleData`（`use-sale.ts`）
- 列印成功後立即寫入 `offline_sale_lines_printable_coupons`（Step 4），失敗時步驟顯示 error

---

## 移植來源

此功能移植自 Maltese 的 `createPrintableCouponProcessor`：
- `src/utils/contexts/printableCoupon.ts`
- `src/contexts/posPrintableCoupon.ts`
- `src/models/posPrintableCoupon.ts`

**與 Maltese 的差異**：
- 活動型小白單已支援（建立 petParkCoupon 記錄取得券號）
- 不需由前端建立 TodoJob 更新 possale（後端 upload 後自動處理）
- 略過 `onlyFirstConsumption`、`accumulationSaleTotal`、`printLimit`（需會員歷史銷售記錄，Ragdoll 本地無此資料）
- 略過員購通路排除邏輯（Ragdoll 目前只有門市通路）
