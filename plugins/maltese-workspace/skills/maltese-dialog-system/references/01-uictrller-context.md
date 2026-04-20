# UICtrllerContext 架構

> 檔案：`src/contexts/uiCtrller.tsx`

## dialogStack 資料結構

```typescript
type UICtrllerDialogProps = {
  /** Dialog 開啟狀態 */
  isOpen?: boolean;
  /** 欲開啟的 Dialog 內容 */
  contentName?: DialogContentName;
  /** 目前開啟中的 Dialog 使用的 props 參數 */
  dialogProps?: Pick<
    MuiDialogProps,
    'title' | 'disableBackdropClose' | 'disableEscapeKeyDown' | 'disableClose'
    | 'disableConfirm' | 'fullWidth' | 'maxWidth' | 'showClose' | 'onClosed' | 'noPadding'
  > | null;
  /** 外部要傳遞給 dialog content 的 props */
  childProps?: AnyObject;
};

type UICtrllerState = {
  /** 最大層數由 cDialogLimit 控制（目前為 3） */
  dialogStack: Array<UICtrllerDialogProps | undefined>;
  drawerContentName: DrawerContentName | null;
  isDrawerOpen: boolean;
};
```

## Dialog 生命週期

```
openDialog(name, options?)
    → dialogStack 中新增一筆 { isOpen: true, contentName: name, ... }
    → Dialog 顯示

closeDialog(index?)
    → 將 isOpen 設為 false（觸發關閉動畫）
    → 回傳 Promise，等待動畫結束

clearDialog(index?)
    → 從 dialogStack 中移除該筆資料
    → Dialog 完全從 DOM 消失
```

**重點**：偵測「Dialog 完全消失」必須等 `clearDialog` 後（stack 中已無此項目），而不是偵測 `isOpen: false`。`isOpen: false` 只代表關閉動畫開始播放，Dialog 仍存在於 DOM 中。

## openDialog 函式簽章

```typescript
openDialog: <Name extends DialogContentName, ChildProps extends AnyObject = never>(
  name: Name,
  options?: {
    dialogProps?: NonNullable<UICtrllerDialogProps['dialogProps']>;
    childProps?: ChildProps;
  }
) => void;
```

- `Name` 約束為 `DialogContentName` 的子型別
- `ChildProps` 泛型預設為 `never`（不傳時不接受任何 childProps）
- `options` 為可選，只傳 `name` 即可開啟不需要額外參數的 Dialog

## DialogContentName 型別

`DialogContentName` 是 `TaskName`（定義於 `src/components/tasks/interface.ts`）與非 Task Dialog 名稱的聯合型別：

```typescript
export type DialogContentName =
  | TaskName                       // 約 45 個 Task Dialog
  | 'searchMember'                 // 以下為非 Task Dialog
  | 'consumption'
  | 'saleDetail'
  | 'serviceSaleDetail'
  | 'memberDetail'
  | 'itemDetail'
  | 'itemListOperation'
  | 'assignBeautician'
  | 'selectReportDate'
  | 'resetChangeTasksConfirm'
  | 'addPriceItem'
  | 'batchPrintItemFilter'
  | 'expenditureInfo'
  | 'addonItemList'
  | 'freebieItemList'
  | 'fullReturnList'
  | 'selectVoucherItems'
  | 'taiShinPayments'
  | 'taishinOnePay'
  | 'refreshEGUICarrier'
  | 'memberInfo'
  | 'memberOtherInfo'
  | 'monthCardDetail'
  | 'fullReturnSaleContent'
  | 'packageReturnSaleContent'
  | 'selectPriceCardVersion'
  | 'itemPriceChange'
  | 'promotionItemPriceChange'
  | 'promotionPrintPriceCard'
  | 'itemSummary'
  | 'afterClickSummary'
  | 'salonSummary'
  | 'takePackageServiceDetail'
  | 'importDeliveryOrder'
  | 'memberValidation'
  | 'memberPointDetail'
  | 'redeemItemSearch'
  | 'simpleConfirm'
  | 'newStorePrintPriceCard'
  | 'corporatePrintPriceCard'
  | 'printItemReceipt'
  | 'memberPromotion'
  | 'updateServiceSale'
  | 'changeMember'
  | 'invalidItemList'
  | 'salesTarget'
  | 'salonSalesTarget'
  | 'cancelCustomerOrder'
  | 'printableCouponInvalid'
  | 'rePrintPrintableCoupon'
  | 'petparkCouponUsageChosen'
  | 'partialSearchOrExchange'
  | 'importInvoiceInfo'
  | 'itemPromotionPriceChange';
```

## cDialogContent 對照表

`uiCtrller.tsx` 中的 `cDialogContent` 常數定義了每個 `DialogContentName` 對應的中文標題與元件：

```typescript
export const cDialogContent: Record<DialogContentName, /** 中文顯示標題 */> = { ... };
```

當需要查詢某個 Dialog 的預設標題或確認名稱是否存在時，可以查看此常數。

## 其他 Actions

| Action | 說明 |
|--------|------|
| `closeDialog(index?)` | 關閉指定層的 Dialog（預設第 0 層），回傳 Promise |
| `clearDialog(index?)` | 從 stack 移除指定層的 Dialog |
| `openDrawer(name)` | 開啟側邊抽屜（`'itemSummary'` 或 `'salonSummary'`） |
| `closeDrawer()` | 關閉抽屜 |
| `reset(options?)` | 清除所有結帳流程相關資料，關閉 Dialog 與 Drawer |
| `openConfirm(content, options?)` | 開啟確認對話框，回傳 `Promise<void \| boolean>` |
