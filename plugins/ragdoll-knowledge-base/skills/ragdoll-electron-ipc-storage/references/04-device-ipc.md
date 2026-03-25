# 硬體裝置 IPC 介面

型別定義：`electron/main/types/ipc-devices.ts`
統一裝置入口：`ragdollAPI.devices`

---

## 發票機 (InvoiceDeviceIPC)

存取路徑：`ragdollAPI.devices.invoice`

| 方法 | 簽名 | IPC Channel | 說明 |
|------|------|-------------|------|
| `ping` | `() => Promise<InvoicePingResult>` | `devices:invoice:ping` | 檢查發票機連線，回傳 `{ connected, error? }` |
| `print` | `(request: InvoicePrintRequest) => Promise<InvoicePrintResult>` | `devices:invoice:print` | 列印發票 / 明細 / 專櫃等模式 |
| `open` | `() => Promise<void>` | `devices:invoice:open` | **打開錢櫃**（獨立操作，不需伴隨列印） |

### 開錢櫃使用方式

```typescript
// 獨立開錢櫃（不伴隨列印）
try {
  await ragdollAPI.devices.invoice.open();
  toast({ description: '已開啟錢櫃', variant: 'success' });
} catch {
  toast({ description: '錢櫃開啟失敗', variant: 'error' });
}

// 伴隨列印開錢櫃（透過 print request 的 shouldOpenCashDrawer 旗標）
await ragdollAPI.devices.invoice.print({
  ...printRequest,
  shouldOpenCashDrawer: true,
});
```

### InvoicePrintRequest 關鍵欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `mode` | `'發票' \| '明細' \| '專櫃' \| '大潤發' \| '汐止遠雄' \| '優惠券'` | 列印模式 |
| `total` | `number` | 總計（含稅） |
| `tax` | `number` | 稅額 |
| `items` | `InvoicePrintItem[]` | 商品明細（name, amount, price） |
| `payments` | `{ name: string; amount: number }[]` | 付款細項 |
| `invoiceNo` | `string` | 發票號碼（空字串表示無） |
| `shouldOpenCashDrawer` | `boolean?` | 是否同時開錢櫃 |

---

## 刷卡機 (CreditCardDeviceIPC)

存取路徑：`ragdollAPI.devices.creditCard`

| 方法 | 簽名 | IPC Channel | 說明 |
|------|------|-------------|------|
| `ping` | `() => Promise<CreditCardPingResult>` | `devices:creditCard:ping` | 檢查刷卡機連線 |
| `sale` | `(req: CreditCardSaleRequest) => Promise<CreditCardSaleResult>` | `devices:creditCard:sale` | 執行刷卡交易 |
| `void` | `(req: CreditCardVoidRequest) => Promise<CreditCardVoidResult>` | `devices:creditCard:void` | 當日取消 |
| `refund` | `(req: CreditCardRefundRequest) => Promise<CreditCardRefundResult>` | `devices:creditCard:refund` | 跨日刷退 |
| `isBusy` | `() => Promise<boolean>` | `devices:creditCard:isBusy` | 檢查是否忙碌中 |
| `cancel` | `() => Promise<boolean>` | `devices:creditCard:cancel` | 取消進行中的交易 |

### 刷卡機類型

```typescript
type CreditCardReaderType = 'TSB' | 'SKB';
```

儲存在 electron-store 的 `CREDIT_CARD_READER_TYPE` 欄位。

### CreditCardSaleRequest

| 欄位 | 型別 | 說明 |
|------|------|------|
| `storeId` | `string` | 18 碼交易序號，格式：`${configName(5碼)}${saleName(13碼)}` |
| `paymentPrice` | `number` | 刷卡金額 |

### CreditCardSaleResult 重要欄位

| 欄位 | 說明 |
|------|------|
| `success` | 交易是否成功 |
| `receiptNo` | 端末機簽單序號（取消交易時需用） |
| `cardNumber` | 卡號（前6後4遮蔽） |
| `approvalCode` | 授權碼 |
| `hostId` | 銀行別（取消交易時需用） |

---

## 台新 ONE 碼支付 (TaishinPayDeviceIPC)

存取路徑：`ragdollAPI.devices.taishinPay`

| 方法 | 簽名 | IPC Channel | 說明 |
|------|------|-------------|------|
| `payment` | `(req: TaishinPayPaymentIpcRequest) => Promise<TaishinPayPaymentIpcResponse>` | `devices:taishinPay:payment` | 執行付款 |
| `refund` | `(req: TaishinPayRefundIpcRequest) => Promise<TaishinPayPaymentIpcResponse>` | `devices:taishinPay:refund` | 執行退款 |
| `query` | `(req: TaishinPayQueryIpcRequest) => Promise<TaishinPayPaymentIpcResponse>` | `devices:taishinPay:query` | 查詢交易 |

### TaishinPayPaymentIpcRequest

| 欄位 | 型別 | 說明 |
|------|------|------|
| `barcode` | `string` | 條碼 |
| `amount` | `number` | 付款金額 |
| `saleName` | `string` | 銷售單編號（用於產生 merchantTradeNo） |
| `items?` | `string[]` | 品項名稱列表（LINE Pay 等錢包為必填） |

### 回應格式（Discriminated Union）

```typescript
type TaishinPayPaymentIpcResponse =
  | { success: true; data: TaishinPayXMLData }
  | { success: false; error: string };
```

> 詳細欄位定義參見 `ragdoll-taishin-one-pay` skill。

---

## 宜睿禮券 (EdenredDeviceIPC)

存取路徑：`ragdollAPI.devices.edenred`

| 方法 | 簽名 | IPC Channel | 說明 |
|------|------|-------------|------|
| `getVoucher` | `(req: EdenredGetVoucherIpcRequest) => Promise<EdenredGetVoucherIpcResponse>` | `devices:edenred:getVoucher` | 查詢票券狀態 |
| `authorization` | `(req: EdenredAuthorizationIpcRequest) => Promise<EdenredAuthorizationIpcResponse>` | `devices:edenred:authorization` | 執行授權核銷 |

### EdenredVoucher 票券資料

| 欄位 | 型別 | 說明 |
|------|------|------|
| `product_code` | `string` | 票券代碼 |
| `product_label` | `string` | 票券名稱 |
| `remaining_value` | `number` | 票券剩餘價值（實際金額） |
| `expiration_date` | `string` | 有效日期（`YYYY-MM-DD HH:mm:ss`） |
| `ref` | `string` | 票券編號 |

---

## IPC_CHANNELS 完整對照表

**定義位置**：
- 主進程：`electron/main/types/ipc-devices.ts`
- Preload：`electron/main/settings/ipc-renderer-preload.ts`（重複定義，需同步）

| 常數名稱 | Channel 字串 | 裝置 |
|----------|-------------|------|
| `INVOICE_PING` | `devices:invoice:ping` | 發票機 |
| `INVOICE_PRINT` | `devices:invoice:print` | 發票機 |
| `INVOICE_OPEN` | `devices:invoice:open` | 發票機（錢櫃） |
| `CREDIT_CARD_PING` | `devices:creditCard:ping` | 刷卡機 |
| `CREDIT_CARD_SALE` | `devices:creditCard:sale` | 刷卡機 |
| `CREDIT_CARD_VOID` | `devices:creditCard:void` | 刷卡機 |
| `CREDIT_CARD_REFUND` | `devices:creditCard:refund` | 刷卡機 |
| `CREDIT_CARD_IS_BUSY` | `devices:creditCard:isBusy` | 刷卡機 |
| `CREDIT_CARD_CANCEL` | `devices:creditCard:cancel` | 刷卡機 |
| `TAISHIN_PAY_PAYMENT` | `devices:taishinPay:payment` | 台新 ONE 碼 |
| `TAISHIN_PAY_REFUND` | `devices:taishinPay:refund` | 台新 ONE 碼 |
| `TAISHIN_PAY_QUERY` | `devices:taishinPay:query` | 台新 ONE 碼 |
| `EDENRED_GET_VOUCHER` | `devices:edenred:getVoucher` | 宜睿禮券 |
| `EDENRED_AUTHORIZATION` | `devices:edenred:authorization` | 宜睿禮券 |
| `UPLOAD_OFFLINE_SALES_TRIGGER` | `trigger-upload-offline-sales` | 系統 |
| `COMMIT_INVOICE` | `commit-invoice` | 系統 |
| `SYNC_INVOICE_OFFSET` | `sync-invoice-offset` | 系統 |
