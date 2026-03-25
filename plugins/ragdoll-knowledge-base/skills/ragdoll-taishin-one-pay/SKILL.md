---
name: ragdoll-taishin-one-pay
description: >
  Ragdoll 台新 ONE 碼支付（One Pay）完整知識庫。涵蓋付款流程、查詢驗證機制、
  錯誤處理、各錢包特殊規則（LINE Pay、悠遊付、橘子支），以及 Electron 主進程
  與 Next.js 渲染端的程式碼位置與資料流。

  以下情況必須參考此文件再動手：
  - 修改或擴充台新 ONE 碼付款流程（payment、query、refund）
  - 處理台新 API 回傳的錯誤代碼或異常狀態
  - 修改 orderitem 組合邏輯（不同錢包的字元限制與分隔符號）
  - 實作退款（refund）功能
  - 撰寫台新 ONE 碼相關的單元測試或整合測試
  - 理解 IPC 資料流（渲染端 store → Electron 主進程 → 台新 API）
---

# Ragdoll 台新 ONE 碼支付知識庫

## 架構概覽

台新 ONE 碼支付採用 **Electron 主進程集中管理** 的架構：
所有 API 呼叫（付款、查詢、退款）皆在 Electron 主進程執行，渲染端只負責條碼輸入與狀態顯示。

```
[渲染端 Next.js]                    [Electron 主進程]              [台新 API]
useTaishinPayPayment store
  processPayment(amount, saleName, items)
    → ragdollAPI.devices.taishinPay.payment(...)
                                  → taishinPayDevice.payment()
                                      → validateTaishinBarcode()
                                      → buildOrderItem()
                                      → generateSignature()
                                      → fetch(gwMerchantApiPay.ashx)
                                      ↓ 逾時或 RtnPOSActionCode=7/8
                                      → verifyPayment() [最多3次查詢]
                                          → queryInternal()
                                          → fetch(gwMerchantApiQuery.ashx)
  ← TaishinPayPaymentIpcResponse
```

---

## 程式碼位置對照表

### Electron 主進程

| 功能 | 檔案路徑 |
|---|---|
| 付款 / 查詢 / 退款裝置介面 | `electron/main/third-party/taishin-pay/index.ts` |
| API endpoints、MerchantID、TokenKey | `electron/main/third-party/taishin-pay/const.ts` |
| 簽章計算、XML 解析、參數串接 | `electron/main/third-party/taishin-pay/utils.ts` |
| IPC 型別定義 | `electron/main/types/ipc-devices.ts`（`TaishinPayPaymentIpcRequest`、`TaishinPayQueryIpcRequest`、`TaishinPayXMLData` 等） |

### Shared（Electron 與 Next.js 共用）

| 功能 | 檔案路徑 |
|---|---|
| 條碼前綴驗證（validateTaishinBarcode） | `shared/utils/taishin-pay.ts` |
| 特店訂單編號產生（generateMerchantTradeNo） | `shared/utils/taishin-pay.ts` |
| 支援的條碼前綴清單（cTaishinOneSupportedPrefixes） | `shared/utils/taishin-pay.ts` |

### Next.js 渲染端

| 功能 | 檔案路徑 |
|---|---|
| 付款 Store（processPayment action） | `next/lib/stores/checkout/payment/taishin-pay/use-taishin-pay-payment.ts` |
| Store 型別（TaishinPayState、TaishinPayActions） | `next/lib/stores/checkout/payment/taishin-pay/type.ts` |
| 條碼識別函式（getTaishinOneTypeFromBarcode） | `next/lib/stores/checkout/payment/taishin-pay/const.ts` |
| 常數（cSuccessRtnCode、cTaishinPayDisplayName） | `next/lib/stores/checkout/payment/taishin-pay/const.ts` |
| 付款頁面（呼叫 processPayment） | `next/app/summary/page.tsx` |
| 條碼輸入對話框 UI 元件 | `next/app/summary/components/payment-block/taishin-pay-input.tsx` |

---

## 付款流程詳細說明

### 1. 渲染端觸發

`next/app/summary/page.tsx` 的 `handleProcessTaishinPayment`：
```typescript
const items: string[] = (iteratedDiscount?.items ?? []).map((item) => item.displayName);
await taishinPayActions.processPayment(total, Date.now().toString(), items);
```

`processPayment` action 從 store state 取得 `barcode`（使用者透過 `setBarcode` 輸入），
連同 `amount`、`saleName`、`items` 透過 IPC 呼叫 Electron 端。

### 2. IPC 請求型別

```typescript
type TaishinPayPaymentIpcRequest = {
    barcode: string;   // ONE 碼序號
    amount: number;    // 付款金額（整數，新台幣）
    saleName: string;  // 銷售單編號（用於產生 merchanttradeno）
    items: string[];   // 商品顯示名稱列表（LINE Pay 等必填）
};
```

### 3. Electron 主進程付款流程

`electron/main/third-party/taishin-pay/index.ts` 的 `taishinPayDevice.payment()`：

**Step 1**：從 Electron Store 取得 `storeid`（`POS_STORE_NAME`）、`terminalid`（`POS_CONFIG_NAME`）

**Step 2**：從 SQLite DB 查 `pos_store` 取得門市 `displayName` 作為 `storename`

**Step 3**：`validateTaishinBarcode(request.barcode)` 驗證前綴

**Step 4**：組合請求參數，特別注意 `orderitem` 由 `buildOrderItem()` 依錢包類型計算

**Step 5**：`generateSignature(params)` 產生簽章（SHA-256，取前 64 字元），**簽章必須在 encodeURIComponent 之前計算**

**Step 6**：`encodeURIComponent` 處理 `barcode1`、`storename`、`orderitem`；發送帶 20 秒逾時的 GET 請求

**Step 7**：`parseTaishinXMLResponse(xml)` 解析回應；若 `RtnCode !== '000'` 回傳失敗

**Step 8**：若 `RtnPOSActionCode === '7' || '8'` → 觸發 `verifyPayment()`

---

## 查詢驗證機制（verifyPayment）

### 觸發條件

1. **付款逾時（AbortError）**：20 秒內無回應
2. **RtnPOSActionCode 為 7 或 8**：台新規格要求必須查詢確認

### 重試邏輯

```
verifyPayment() 最多執行 3 次（retry 0, 1, 2）
├── 呼叫 queryInternal() 查詢 gwMerchantApiQuery.ashx
├── 若查詢失敗（網路/API 非 000）→ 等 10 秒後重試
├── 若查詢成功但 TradeAmount 與預期不符 → 拋出 Error（也進入重試）
├── 若查詢成功但 RtnPOSActionCode 仍為 7/8 → 等 10 秒後重試
└── 若查詢成功且狀態正常 → 回傳 data（RtnCode='000' 保證）
達最大重試次數後仍失敗 → 拋出 Error → 上層回傳 { success: false }
```

### 查詢 API 請求參數

```typescript
{
    merchantid,
    barcode1,           // encodeURIComponent 處理
    storeid,
    terminalid,
    merchanttradedate,  // 原付款的交易日期 yyyyMMDD
    merchanttradetime,  // 原付款的交易時間 HHmmss
    tradetype,          // '110'（付款查詢）或 '210'（退款查詢）
    tradeno,            // 特店訂單編號（merchanttradeno）
    merchantquerydatetime, // 查詢當下時間 YYYYMMDDHHmmss
}
```

---

## 各錢包特殊規則

### orderitem 欄位規則

`buildOrderItem()` 依條碼前綴決定：

| 錢包 | 條碼前綴 | orderitem 最大字元 | 分隔符號 | 備註 |
|---|---|---|---|---|
| 悠遊付（EASY_PAY） | `99` | **100** 字元 | `;` | 超過截斷加 `etc.`，保留 5 字元 |
| 橘子支 PLUS PAY | `FP`、`FF` | 1024 字元 | **`,`** | 使用 `;` 會造成 ProductInfo 格式異常 |
| LINE Pay（LINEPAYM） | `31`-`39` | 1024 字元 | `;` | **必填**，空值會回傳 `32101 Parameter error` |
| 其他 | 其他前綴 | 1024 字元 | `;` | 選填 |

### LINE Pay 退款特殊規則

LINE Pay 退款時 `servicetradeno` 欄位應帶**原付款的 `merchanttradeno`**（非 `ServiceTradeNo`）。
其他錢包則需先查詢取得 `ServiceTradeNo`。

### Taiwan Pay / iCash Pay 退款特殊規則

退款時 `remark1` 需帶入 JSON：`{ "ORGMtradeno": "<原付款merchanttradeno>" }`

---

## 錯誤代碼對照

| RtnCode | 說明 | 處理方式 |
|---|---|---|
| `000` | 交易成功 | 繼續流程 |
| `32101` | Parameter error | 通常是 orderitem 為空（LINE Pay 必填） |
| `3916` / `32002` | 查無此訂單 / 訂單不存在 | 退款查詢時表示未退款過，可忽略 |
| `33010` / `31165` | 重複退款 | 比對 localStorage 的退款記錄確認是否已成功 |

| RtnPOSActionCode | 說明 | 處理方式 |
|---|---|---|
| `0` | 正常 | 無需額外處理 |
| `7` | 待確認交易（需查詢） | 觸發 verifyPayment |
| `8` | 待確認交易（需查詢） | 觸發 verifyPayment |

---

## Store 狀態機（渲染端）

`useTaishinPayPayment` store 的 `status` 欄位驅動 UI 顯示：

```
IDLE
  ↓ setBarcode() → 識別 taishinOneType，錯誤時記錄 error 但不中斷
IDLE（taishinOneType 已設定）
  ↓ processPayment()
PROCESSING
  ↓ 付款成功（RtnCode='000'）
SUCCESS
  ↓ processPayment()（RtnCode!='000'）
ERROR
  ↓ reset()
IDLE
```

`canCheckout(state)` 回傳 `true` 的條件：
- `status === 'SUCCESS'`
- `paymentResult?.RtnCode === '000'`

---

## IPC Channel 名稱

| 操作 | Channel | 定義位置 |
|---|---|---|
| 付款 | `TAISHIN_PAY_PAYMENT` | `electron/main/settings/ipc-main-setup.ts` |
| 查詢 | `TAISHIN_PAY_QUERY` | `electron/main/settings/ipc-main-setup.ts` |
| 退款 | `TAISHIN_PAY_REFUND` | `electron/main/settings/ipc-main-setup.ts` |

---

## 簽章計算規則

1. 將所有請求參數（**encodeURIComponent 之前**）依 ASCII 順序排序
2. 串接為 `key1=value1&key2=value2...` 格式
3. 末尾附加 `TokenKey`（token1 + token2 串接）
4. SHA-256 計算後取前 64 字元 hex 字串

```typescript
// generateSignature() 在 electron/main/third-party/taishin-pay/utils.ts
const raw = concatQueryValues(params) + cTaishinPayTokenKey;
return crypto.createHash('sha256').update(raw).digest('hex').substring(0, 64);
```

---

## 退款流程

`taishinPayDevice.refund()` 位於 `electron/main/third-party/taishin-pay/index.ts`。

### IPC 請求型別

```typescript
type TaishinPayRefundIpcRequest = {
    barcode: string;            // ONE 碼條碼
    refundAmount: number;       // 退款金額
    refundName: string;         // 退貨單編號（用於產生退款 merchanttradeno）
    refundDate: string;         // 退款日期 yyyyMMDD
    refundTime: string;         // 退款時間 HHmmss
    payMerchantTradeNo: string; // 原付款特店訂單編號
    payTradeDate: string;       // 原付款日期 yyyyMMDD
    payTradeTime: string;       // 原付款時間 HHmmss
};
```

### 退款流程步驟

1. 取得門市 `storeid`、`storename`、`terminalid`
2. 產生退款 `merchanttradeno` = `generateMerchantTradeNo(refundName, refundAt)`
3. 依條碼前綴判斷錢包類型（LINE Pay、JKOPAY、PI_PAY、TAIWAN_PAY、I_CASH_PAY）
4. **JKOPAY / PI_PAY**：先以 `tradeType='210'` 查詢是否已有退款記錄；若 `3916`/`32002` 則繼續，否則拋出 Error
5. 取得 `servicetradeno`：
   - **LINE Pay**：使用 `payMerchantTradeNo`
   - **其他**：以 `tradeType='110'` 查詢原付款取得 `ServiceTradeNo`
6. 組合 `remark1`：
   - **TAIWAN_PAY / I_CASH_PAY**：`JSON.stringify({ ORGMtradeno: payMerchantTradeNo })`
   - 其他：`''`
7. 組合請求參數（含 `servicetradeno`）、計算簽章、發送退款 GET 請求
8. 解析回應；`33010`/`31165`（重複退款）回傳失敗但記錄 log，其他非 000 回傳失敗
