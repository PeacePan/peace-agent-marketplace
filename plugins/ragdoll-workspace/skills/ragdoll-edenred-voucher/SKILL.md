---
name: ragdoll-edenred-voucher
description: >
  Ragdoll 宜睿禮券（Edenred Voucher）完整知識庫。涵蓋票券查詢、授權核銷、
  金額換算規則、product_code 解析、錯誤代碼處理、付款紀錄組裝，以及 Electron 主進程
  與 Next.js 渲染端的程式碼位置與資料流。

  以下情況必須參考此文件再動手：
  - 修改或擴充宜睿禮券付款流程（查詢、核銷、折抵）
  - 處理宜睿 API 回傳的錯誤代碼或異常狀態
  - 修改 product_code 解析邏輯或 remaining_value 金額換算
  - 修改宜睿禮券與其他付款方式（現金/信用卡）並行付款的紀錄組裝邏輯
  - 修改 createSale 中 voucherTotal / totalWithoutVoucher 的計算
  - 修改 Summary 頁面中宜睿禮券的顯示邏輯（已付合計、找零）
  - 撰寫宜睿禮券相關的單元測試或整合測試
  - 理解 IPC 資料流（渲染端 store → Electron 主進程 → 宜睿 API）
---

# Ragdoll 宜睿禮券知識庫

## 架構概覽

宜睿禮券採用 **「查詢再核銷」** 的兩階段流程，每次授權核銷都是不可逆的真實金融交易。
宜睿禮券為 **獨立折抵機制**，不佔用 `payment.selectedMethod`，可與現金/信用卡/台新 ONE 碼並行使用。

```
[渲染端 Next.js]                       [Electron 主進程]              [宜睿 API]
useEdenredPayment store
  queryVoucher(voucherNumber)
    → ragdollAPI.devices.edenred.getVoucher(...)
                                     → edenredDevice.getVoucher()
                                         → readEdenredCredentials()
                                         → fetch(GET /api/vouchers/ETX_001-{ref})
                                         → parseProductCode()
                                         → 換算 remaining_value
  ← EdenredGetVoucherIpcResponse

  authorizeVoucher(acceptancePointRef, value)
    → ragdollAPI.devices.edenred.authorization(...)
                                     → edenredDevice.authorization()
                                         → readEdenredCredentials()
                                         → fetch(POST /api/transactions)
  ← EdenredAuthorizationIpcResponse
     (authorization_id, authorized_amount)

  [累計 authorizedVouchers / totalAuthorizedAmount]
  [收銀員可繼續加入下一張或結帳]
```

---

## 程式碼位置對照表

### Electron 主進程

| 功能 | 檔案路徑 |
|---|---|
| 票券查詢 / 授權核銷裝置介面 | `electron/main/third-party/edenred/index.ts` |
| API endpoints、Base URL | `electron/main/third-party/edenred/const.ts` |
| IPC 型別定義 | `electron/main/types/ipc-devices.ts`（`EdenredVoucher`、`EdenredGetVoucherIpcRequest`、`EdenredAuthorizationIpcRequest` 等） |
| IPC handler 註冊 | `electron/main/settings/ipc-main-setup.ts` |
| IPC preload 橋接 | `electron/main/settings/ipc-renderer-preload.ts` |

### Shared（Electron 與 Next.js 共用）

| 功能 | 檔案路徑 |
|---|---|
| product_code 解析（parseProductCode） | `shared/utils/edenred.ts` |
| 錯誤代碼對照表（EdenredResponseCode） | `shared/utils/edenred.ts` |
| 收銀員可識別錯誤碼子集（EdenredSaleIdentifiedResponseCode） | `shared/utils/edenred.ts` |
| ProductCodeInfo 型別 | `shared/utils/edenred.ts` |

### Next.js 渲染端

| 功能 | 檔案路徑 |
|---|---|
| 付款 Store（queryVoucher、authorizeVoucher actions） | `next/lib/stores/checkout/payment/edenred/use-edenred-payment.ts` |
| Store 型別（EdenredPaymentData、EdenredPaymentActions） | `next/lib/stores/checkout/payment/edenred/type.ts` |
| 付款頁面（Summary page，宜睿付款顯示與找零計算） | `next/app/summary/page.tsx` |
| 票券核銷對話框 UI 元件（EdenredVoucherPanel） | `next/app/summary/components/payment-block/edenred-voucher-panel.tsx` |
| 付款方式選擇區塊（含宜睿按鈕與折抵摘要） | `next/app/summary/components/payment-block/index.tsx` |
| 結帳按鈕（canCheckout 判斷含宜睿折抵） | `next/app/summary/components/checkout-button.tsx` |
| 銷售紀錄組裝（createSale 中的付款紀錄與 voucherTotal） | `next/lib/stores/checkout/sale/use-sale.ts` |
| 付款方式顯示名稱（EDENRED: '宜睿禮券'） | `next/lib/stores/checkout/sale/const.ts` |

### 測試檔案

| 功能 | 檔案路徑 |
|---|---|
| E2E 測試（票券核銷流程） | `test/e2e/1-checkout-flow/edenred-voucher.spec.ts` |
| Electron 單元測試（edenredDevice） | `test/electron/unit/third-party/edenred.test.ts` |
| Store 整合測試（useEdenredPayment） | `test/next/integration/stores/payment/edenred.test.ts` |
| 工具函式測試（parseProductCode） | `test/next/integration/utils/edenred.test.ts` |

---

## 票券查詢流程

### 1. 渲染端觸發

`next/app/summary/page.tsx` 的 `handleQueryEdenredVoucher`：
```typescript
const handleQueryEdenredVoucher = async (voucherNumber: string): Promise<void> => {
    await edenredActions.queryVoucher(voucherNumber);
};
```

### 2. Store action 處理

`useEdenredPayment` store 的 `queryVoucher` action：
- 檢查票券是否已在 `authorizedVouchers` 中（防止重複核銷）
- 設定 `status: 'QUERYING'` 作為防重入鎖
- 透過 IPC 呼叫 Electron 主進程查詢

### 3. IPC 請求型別

```typescript
type EdenredGetVoucherIpcRequest = {
    voucherNumber: string;  // 票券編號
};
```

### 4. Electron 主進程查詢流程

`electron/main/third-party/edenred/index.ts` 的 `edenredDevice.getVoucher()`：

**Step 1**：從 pos_store 資料表讀取門市的 `edenredClientId` 與 `edenredClientSecret`

**Step 2**：發送 GET 請求至 `/api/vouchers/ETX_001-{voucherNumber}`，Header 包含：
- `X-Client-id`：門市 clientId
- `X-Client-secret`：門市 clientSecret
- `X-Correlation-Id`：隨機 UUID

**Step 3**：驗證回應 `meta.status === 'succeeded'`，失敗時從 `meta.messages[0].code` 取得錯誤代碼

**Step 4**：解析 `product_code` 並換算 `remaining_value`（詳見下方金額換算規則）

### 5. 查詢回應型別

```typescript
type EdenredGetVoucherIpcResponse = {
    success: boolean;
    data?: EdenredVoucher;
    error?: string;
};

type EdenredVoucher = {
    product_code: string;      // 產品代碼（8 碼以上）
    product_label: string;     // 產品名稱
    remaining_value: number;   // 已換算的剩餘價值
    expiration_date: string;   // 到期日
    ref: string;               // 票券編號
};
```

---

## 授權核銷流程

### 1. 渲染端觸發

收銀員在 `EdenredVoucherPanel` 的 `VoucherInfoScene` 確認折抵金額後觸發：
```typescript
const handleAuthorizeEdenredVoucher = async (value: number): Promise<void> => {
    await edenredActions.authorizeVoucher(`EDENRED_${Date.now()}`, value);
};
```

### 2. Store action 處理

`useEdenredPayment` store 的 `authorizeVoucher` action：
- 設定 `status: 'AUTHORIZING'` 防重入
- `acceptancePointRef` 加上 `authorizedVouchers.length` 後綴確保唯一
- 成功後將票券移入 `authorizedVouchers`，累加 `totalAuthorizedAmount`
- 清除 `queriedVoucher` 讓收銀員可繼續加入下一張

### 3. IPC 請求型別

```typescript
type EdenredAuthorizationIpcRequest = {
    acceptancePointRef: string;  // 交易碼（唯一值）
    voucherRef: string;          // 票券編號
    value: number;               // 折抵金額
};
```

### 4. Electron 主進程授權流程

`edenredDevice.authorization()`：

**Step 1**：從 pos_store 讀取門市憑證

**Step 2**：發送 POST 請求至 `/api/transactions?return_vouchers_info=true`
```json
{
    "acceptance_point_ref": "EDENRED_1711012345_0",
    "capture_mode": "auto",
    "vouchers": [{
        "value": 500,
        "product_class": "ETX_001",
        "ref": "ABC123456"
    }]
}
```

**Step 3**：驗證回應 `meta.status === 'succeeded'`

**Step 4**：回傳 `authorization_id` 與 `authorized_amount`

### 5. 授權回應型別

```typescript
type EdenredAuthorizationIpcResponse = {
    success: boolean;
    data?: EdenredAuthorizationData;
    error?: string;
};

type EdenredAuthorizationData = {
    authorization_id: string;    // 宜睿授權交易碼
    authorized_amount: number;   // 實際核銷金額
};
```

---

## product_code 解析與金額換算

### product_code 格式

8 碼以上字串，前 2 碼為分類資訊，第 3-8 碼為面額：

| 位置 | 代碼 | 意義 |
|---|---|---|
| 第 1 碼 | `S` | 單次使用 |
| 第 1 碼 | `M` | 多次使用 |
| 第 2 碼 | `V` | 面額券 |
| 第 2 碼 | `P` | 商品券 |
| 第 3-8 碼 | 6 位數字 | 面額值（`000000` 或 `999999` 視為 null） |

```typescript
parseProductCode('SV010000') // => { category: '單次使用', type: '面額券', value: 10000 }
parseProductCode('MP000000') // => { category: '多次使用', type: '商品券', value: null }
parseProductCode('SV999999') // => { category: '單次使用', type: '面額券', value: null }
```

### remaining_value 金額換算規則

API 回傳的 `remaining_value` 原始值需依據券種換算為新台幣金額：

| 條件 | 換算公式 | 範例 |
|---|---|---|
| 多次使用（M） | `rawValue / 100` | API 回傳 5000 → 實際 50 元 |
| 單次使用（S）+ 面額券（V）+ value 不為 null | `rawValue × value` | API 回傳 1，value=500 → 實際 500 元 |
| 其他（商品券等） | 直接使用 | API 回傳 1 → 實際 1 |

### 折抵金額限制

在 `EdenredVoucherPanel` 的 UI 中：
- 單次使用面額券：金額固定，不可調整（鎖定 Input）
- 多次使用券或餘額型券：可在 `1 ~ Math.min(remainingValue, remainingTotal)` 之間調整
- 折抵金額超過剩餘應付金額時，UI 顯示溢付警示

---

## 宜睿禮券與其他付款方式的並行邏輯

### 核心設計

宜睿禮券 **不佔用** `payment.selectedMethod`，而是獨立累計折抵：
- `edenredState.totalAuthorizedAmount`：累計已核銷金額
- `totalWithoutVoucher = total - edenredVoucherTotal`：扣除禮券後的實際待付金額
- 現金/信用卡/台新 ONE 碼只需支付 `totalWithoutVoucher`

### canCheckout 判斷邏輯

`next/lib/stores/checkout/payment/use-payment.ts` 的 `canCheckout()`：

```typescript
// 無 selectedMethod 時，若宜睿核銷金額已足夠 → 可結帳
if (!payment.selectedMethod) {
    if (edenredData) return canCheckoutEdenred(edenredData, subtotal);
    return false;
}

// 現金付款：收款金額 >= 應付金額 - 宜睿折抵
if (payment.selectedMethod === 'CASH') {
    const edenredDiscount = edenredData?.totalAuthorizedAmount ?? 0;
    return payment.cashReceived >= subtotal - edenredDiscount;
}
```

### 找零計算

Summary 頁面的找零金額需扣除宜睿折抵：
```typescript
const edenredTotal: number = edenredState.totalAuthorizedAmount;
const changeAmount = getChangeAmount(payment, Math.max(0, total - edenredTotal));
// getChangeAmount: cashReceived - subtotal（subtotal 已扣除宜睿折抵）
```

### Summary 頁面 UI 顯示

當宜睿禮券與其他付款方式並用時，顯示結構為：

```
付款方式
  ⊙ 現金          $1,000
  ⊙ 宜睿票券        $20
已付合計           $1,020
找零                $787
```

---

## createSale 付款紀錄組裝

`next/lib/stores/checkout/sale/use-sale.ts` 的 `createSale` action 中，
宜睿禮券紀錄與主要付款方式紀錄分開組裝後合併：

### 付款紀錄組裝

```typescript
// 宜睿紀錄：從 authorizedVouchers 逐張組裝
const edenredRecords = edenred.authorizedVouchers.map((voucher) => ({
    type: 'EDENRED' as const,
    amount: voucher.authorizedAmount,
    edenredVoucherNumber: voucher.voucherRef,
    edenredAuthorizationId: voucher.authorizationId,
}));

// 主要付款方式紀錄：金額為 totalWithoutVoucher（扣除宜睿折抵後）
const primaryPaymentRecords = (() => {
    if (payment.selectedMethod === 'CASH' || payment.selectedMethod === 'CREDIT') {
        return [{ type: payment.selectedMethod, amount: totalWithoutVoucher, ... }];
    }
    // ...其他付款方式
})();

// 合併
const paymentRecords = [...edenredRecords, ...primaryPaymentRecords];
```

### dbRecord body 欄位

```typescript
const dbRecord: OfflineSaleLocalRecord = {
    body: {
        total,                    // 應付總額（不含宜睿折抵）
        voucherTotal,             // 宜睿禮券折抵總額（有使用時才寫入）
        totalWithoutVoucher,      // 扣除禮券後的實付金額（有使用時才寫入）
        // ...其他欄位
    },
    lines: {
        payments: paymentRecords, // 宜睿紀錄 + 主要付款紀錄
    },
};
```

### 發票列印中的宜睿禮券

`convertSaleToInvoiceItems()` 會在品項列表末尾加入宜睿禮券負項：
```typescript
// 若 voucherTotal > 0，將禮券折抵作為負項加入品項明細
// 因為地端程式會檢查 items 總計是否等於 total
...((sale.body.voucherTotal || 0) > 0
    ? [{ name: '宜睿禮券', amount: 1, price: -(total - totalWithoutVoucher) }]
    : []),
```

---

## Store 狀態機（渲染端）

`useEdenredPayment` store 的 `status` 欄位驅動 UI 顯示與防重入：

```
IDLE
  ↓ queryVoucher()
QUERYING ──────（查詢成功）──→ IDLE（queriedVoucher 已設定）
  │                                    ↓ authorizeVoucher()
  │                              AUTHORIZING
  │                                    │
  │               ┌────────────────────┼────────────────────┐
  │               ↓                    ↓                    ↓
  │            SUCCESS              ERROR                 ERROR
  │    (voucher 移入              (授權失敗)            (查詢失敗)
  │     authorizedVouchers)
  │               ↓
  │            IDLE（可繼續查詢下一張）
  ↓
ERROR（查詢失敗）
  ↓ 重新查詢
IDLE
```

`canCheckout(data, subtotal)` 回傳 `true` 的條件：
- `authorizedVouchers.length > 0`（至少有一張已核銷）
- `status` 不在 `QUERYING` 或 `AUTHORIZING`
- `totalAuthorizedAmount >= subtotal`

---

## API 環境設定

| 環境 | Base URL |
|---|---|
| production / edge | `https://voucher.ap.edenred.io/v1` |
| 其他（staging/dev） | `https://xp-voucher-stg-sg-v1.sg-s1.cloudhub.io` |

API endpoints：
- 查詢票券：`GET {base}/api/vouchers/ETX_001-{voucherNumber}`
- 授權核銷：`POST {base}/api/transactions?return_vouchers_info=true`

---

## IPC Channel 名稱

| 操作 | Channel | 定義位置 |
|---|---|---|
| 查詢票券 | `devices:edenred:getVoucher` | `electron/main/settings/ipc-main-setup.ts` |
| 授權核銷 | `devices:edenred:authorization` | `electron/main/settings/ipc-main-setup.ts` |

---

## 錯誤代碼對照

### 收銀員可識別的常見錯誤

| 代碼 | 說明 | 處理方式 |
|---|---|---|
| `ERV0001` | 序號不存在 | 請顧客確認票券編號 |
| `ERV0004` | 序號已過期 | 無法使用，請顧客更換 |
| `ERV0006` | 序號已作廢 | 無法使用，請顧客聯繫宜睿 |
| `ERV0010` | 數量不足 | 餘額不足，調整折抵金額或更換票券 |
| `ERV0033` | 序號已經使用 | 單次使用券已核銷過 |
| `ERV0077` | 預先交易完成 | 票券已被使用 |

### 其他錯誤代碼

完整錯誤代碼對照表定義於 `shared/utils/edenred.ts` 的 `EdenredResponseCode`，
涵蓋 `ERV0000` 至 `ERV9999` 共 80+ 筆錯誤碼。非收銀員可識別的錯誤應由系統管理員介入。

---

## 憑證管理

宜睿 API 憑證（`edenredClientId`、`edenredClientSecret`）儲存於各門市的 `pos_store` 資料表中，
由 `readEdenredCredentials()` 依當前門市名稱動態讀取。

若憑證缺失，系統會提前拋出 `{storeName} 門市缺少宜睿 API 憑證，請聯絡系統發展部` 錯誤，
避免延遲至 API 呼叫時才失敗。
