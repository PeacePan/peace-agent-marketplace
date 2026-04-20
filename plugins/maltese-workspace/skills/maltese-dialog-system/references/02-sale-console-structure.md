# SaleConsole 元件結構

> 檔案：`src/components/layouts/saleConsole/index.tsx`

## 頁面與 SaleConsole 類型對應

| URL | 頁面檔案 | SaleConsoleType | 說明 |
|-----|----------|-----------------|------|
| `/` | `pages/index.pub.tsx` | N/A | BootUp 入口，不掛載 SaleConsole |
| `/checkout` | `pages/checkout/index.pub.tsx` | `item` | 一般商品銷售 |
| `/salon` | `pages/salon/index.pub.tsx` | `salon` | 美容服務銷售 |
| `/workbench` | `pages/workbench/index.pub.tsx` | N/A | 美容工作臺，不使用 SaleConsole |

所有頁面都用 `dynamic(() => ..., { ssr: false })` 關閉 SSR，頁面邏輯只在 Client 執行。

## SaleConsole 掛載條件

SaleConsole 只在 BootUp 完成後才被掛載：

```
isCompleted = false → SaleConsole 不掛載 → 內部 hook 不執行
isCompleted = true  → SaleConsole 掛載   → 內部 hook 執行
```

`isCompleted = true` 代表使用者已完成：身份驗證 → 選擇門市 → 選擇機台。

## Tab 結構

### item 類型（`/checkout`）

```typescript
{
  View: ItemView,         // 左側商品展示區
  tabs: [
    { tabId: 'checkout',   label: '結帳',  Component: ItemCheckout },
    { tabId: 'shortcut',   label: '商品',  Component: Shortcut },
    { tabId: 'management', label: '管理',  Component: Management },
  ]
}
```

### salon 類型（`/salon`）

```typescript
{
  View: SalonView,        // 左側美容服務展示區
  tabs: [
    { tabId: 'checkout',   label: '結帳',  Component: SalonCheckout },
    { tabId: 'management', label: '管理',  Component: SalonManagement },
  ]
}
```

## 元件檔案路徑

| 元件 | 檔案路徑 |
|------|----------|
| SaleConsole | `src/components/layouts/saleConsole/index.tsx` |
| ItemView | `src/components/layouts/saleConsole/item/index.tsx` |
| item/Checkout | `src/components/layouts/saleConsole/item/Checkout.tsx` |
| item/Shortcut | `src/components/layouts/saleConsole/item/Shortcut.tsx` |
| item/Management | `src/components/layouts/saleConsole/item/Management.tsx` |
| SalonView | `src/components/layouts/saleConsole/salon/index.tsx` |
| salon/Checkout | `src/components/layouts/saleConsole/salon/Checkout.tsx` |
| salon/Management | `src/components/layouts/saleConsole/salon/Management.tsx` |

## 佈局結構

```
┌─────────────────────────────────────────────┐
│ SaleConsole                                 │
├──────────┬──────────────────────┬───────────┤
│  info    │                      │ operation │
│ ┌──────┐ │       view           │ ┌───────┐ │
│ │Member│ │   (ItemView /        │ │ Tabs  │ │
│ │ View │ │    SalonView)        │ │結帳   │ │
│ ├──────┤ │                      │ │商品   │ │
│ │User  │ │                      │ │管理   │ │
│ │ Info │ │                      │ │       │ │
│ └──────┘ │                      │ └───────┘ │
└──────────┴──────────────────────┴───────────┘
```

## Provider 層級（_app → 頁面）

`_app.pub.tsx` 中的 Common Providers（由上而下）：

```
MuiToastProvider
  └ BootUpProvider
    └ UserProvider          ← 銷售員登入
      └ PosReportProvider
        └ ExpenditureProvider
          └ PosShelfProvider
            └ PosMemberProvider
              └ PosPetProvider
                └ PosShortcutProvider
                  └ PosMallSettingProvider
                    └ CheckoutInfoProvider
```

各頁面（checkout / salon）在上述 Common Providers 之上，再包裹頁面專屬的 Providers（如 UICtrllerProvider、PosSaleProvider 等）。
