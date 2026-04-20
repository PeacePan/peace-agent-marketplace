# 重要資料結構定義

---

## CheckoutDiscountSaleItem（商品計算項目）

定義於 `next/lib/stores/checkout/discount/type.ts`

```typescript
interface CheckoutDiscountSaleItem {
  name: string
  price: number              // 計算器處理後的當前售價
  memberPrice: number        // 原始會員價（不隨計算器變動）
  labelPrice: number         // 原始定價（不隨計算器變動）
  amount: number
  discountBase: 'MEMBER' | 'LABEL'  // 折扣計算基準
  saleItemType: SaleItemType        // 商品來源類型（見下方列舉）
  promotionName?: string            // 關聯的活動名稱
  pointsPromotionName?: string      // 點加金活動名稱（點數部分）
  adjustReason?: string             // 變價原因
  authorizer?: string               // 變價授權人員編
}

type SaleItemType =
  | 'NORMAL'           // 一般購物車商品
  | 'OPEN_PRICE'       // 時價商品（無固定定價，門市人員手動輸入售價）
  | 'CHANGE'           // 變價商品（主管授權調整價格）
  | 'FREEBIE_ADDON'    // 加購商品（有售價）
  | 'FREEBIE_GIVE'     // 贈品（price 固定為 0）
  | 'POINT_PLUS_MONEY' // 點加金商品（price = 金額部分）
  | 'PET_PARK_COUPON'  // 優惠券觸發的商品
```

---

## DiscountPromotion（促銷紀錄）

定義於 `next/lib/stores/checkout/discount/type.ts`

```typescript
interface DiscountPromotion {
  type: PromotionType       // 促銷來源類型
  name: string              // 活動名稱或描述
  amount: number            // 折抵金額（正數）
  items?: string[]          // 受此促銷影響的商品名稱清單
}

type PromotionType =
  | 'PROMOTION'                    // POS 商品促銷（計算器 6）
  | 'PET_PARK_COUPON_PROMOTION'    // 優惠券商品折扣（計算器 5）
  | 'PET_PARK_COUPON_DISCOUNT'     // 優惠券整單折扣（計算器 7）
  | 'ORDER_DISCOUNT'               // 整單滿額折扣（計算器 8）
  | 'COUPON_CODE'                  // 折扣碼（計算器 9）
  | 'DISCOUNT_BY_POINTS'           // 點數折抵（計算器 10）
```

---

## OfflineSaleLocalRecord（離線銷售單）

寫入 `offline_sale` SQLite 資料表

```typescript
interface OfflineSaleLocalRecord {
  body: {
    saleNo: string               // 銷售單號（門市代碼 + 流水號）
    total: number                // 應付總額（完整折扣後）
    discount: number             // 折扣總額（原始總額 - total）
    saleTotal: number            // 商品小計（商品促銷後，整單折扣前）
    storeName: string            // 門市名稱
    posConfigName: string        // POS 機台名稱
    salerName: string            // 銷售員姓名
    salerEmployeeId: string      // 銷售員員工編號
    memberName: string | null    // 會員姓名（無會員為 null）
    memberPhone: string | null   // 會員電話
    issueInvoiceName: string | null  // 電子發票號碼（createSale 後補填）
    uploadStatus: UploadStatus   // 同步狀態
    createdAt: string            // 建立時間
  }
  lines: {
    items: SaleLineItem[]
    payments: PaymentLine[]
  }
}

type UploadStatus = 'PENDING' | 'COMPLETED' | 'ERROR'
```

---

## SaleLineItem（銷售明細行）

```typescript
interface SaleLineItem {
  name: string         // 商品名稱（含發票前綴，見下方前綴規則）
  price: number        // 實際售價（含促銷折扣）
  labelPrice: number   // 標籤定價（未折扣）
  amount: number       // 數量
  promotionLabel?: string  // 促銷標籤文字
  adjustReason?: string    // 變價原因（僅 adjustPriceItems）
  authorizer?: string      // 變價授權人（僅 adjustPriceItems）
}
```

### 商品名稱發票前綴規則

| 前綴 | 觸發條件 | 說明 |
|------|----------|------|
| `[會]` | `discountBase === 'MEMBER'` | 以會員價銷售 |
| `[定]` | `discountBase === 'LABEL'` | 以定價銷售（非會員計算基準） |
| `[指]` | 有套用 `PROMOTION` 型促銷 | 指定商品促銷折扣 |
| `[加]` | `saleItemType === 'FREEBIE_ADDON'` | 加購商品 |
| `[贈]` | `saleItemType === 'FREEBIE_GIVE'` | 贈品（0 元） |

---

## PaymentLine（付款明細行）

```typescript
interface PaymentLine {
  method: PaymentMethod         // 付款方式
  amount: number                // 付款金額
  change: number                // 找零金額（現金時填入，信用卡為 0）
  creditCardResult?: {
    last4: string               // 卡號末四碼
    approvalCode: string        // 授權碼
    terminalId: string          // 終端機 ID
    cardType?: string           // 卡種（如 VISA、Mastercard）
  }
}

type PaymentMethod = 'CASH' | 'CREDIT_CARD'
```

---

## IssueInvoiceLocalRecord（電子發票開立記錄）

寫入 `issue_invoice` SQLite 資料表

```typescript
interface IssueInvoiceLocalRecord {
  eguiNo: string          // 電子發票號碼（2 英文 + 8 數字，如 AA12345678）
  randomCode: string      // 4 位隨機碼（用於對獎）
  carrierNo: string | null    // 手機條碼或自然人憑證號碼
  taxId: string | null        // 公司統一編號（三聯式發票）
  donateCode: string | null   // 捐贈碼（愛心碼）
  saleNo: string              // 對應的銷售單號
  issuedAt: string            // 開立時間（ISO 8601）
  syncedAt: string | null     // 同步至雲端的時間（null 表示尚未同步）
}
```

---

## 發票類型與列印行為矩陣

| `invoiceType` | 顯示名稱 | 取號 | 建立 `issue_invoice` | 列印發票聯 | 列印明細聯 |
|---------------|----------|------|---------------------|-----------|-----------|
| `print` | 一般紙本發票 | ✅ | ✅ | ✅ | ✅ |
| `taxId` | 公司統編（三聯式） | ✅ | ✅ | ✅ | ✅ |
| `carrier` | 手機條碼/自然人憑證 | ✅ | ✅ | ❌ | ✅ |
| `donate` | 捐贈碼 | ✅ | ✅ | ❌ | ✅ |
| 任何型別 (total=0) | 0 元交易 | ❌ | ❌ | ❌ | ✅ |

---

## CheckoutItem（購物車商品）

定義於 `next/lib/stores/checkout/items/type.ts`

```typescript
type CheckoutItem = {
  uuid: string              // 唯一識別碼（React key）
  saleItemType: 'NORMAL' | 'OPEN_PRICE' | 'CHANGE'  // 商品類型
  name: string              // 料件編號
  displayName: string       // 顯示名稱
  barcode?: string          // 國際條碼
  price: number             // 當前售價（一般商品隨會員狀態切換，時價/變價固定）
  memberPrice: number       // 會員價（時價商品 = 輸入的售價）
  labelPrice: number        // 定價（時價商品 = 輸入的售價）
  amount: number            // 數量
  changePriceReason?: string  // 變價原因（僅 CHANGE）
  authorizer?: string         // 授權主管員編（僅 CHANGE）
}
```

### PendingOpenPrice（時價商品暫存）

```typescript
type PendingOpenPrice = {
  name: string              // 料件編號
  displayName: string       // 顯示名稱
  barcode?: string          // 國際條碼
  openPriceMin: number      // 開放價格最低
  openPriceMax: number      // 開放價格最高
}
```

---

## PointDiscount（點數折現設定）

定義於 `next/lib/stores/checkout/discount/member-points/type.ts`

```typescript
interface PointDiscount {
  rate: number            // 換算匯率（例如 10 表示 10 點換 1 元）
  maxPercentage: number   // 單筆訂單最高折抵百分比（例如 0.2 表示最多折 20%）
  isEnabled: boolean      // 是否啟用點數折現功能
}
```
