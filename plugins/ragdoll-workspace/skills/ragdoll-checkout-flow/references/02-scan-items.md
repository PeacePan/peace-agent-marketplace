# Step 3：商品掃描與購物車管理

---

## 商品掃描輸入

**元件**：`next/app/checkout/components/item-input.tsx`
**Store**：`next/lib/stores/checkout/items/use-items.ts`

### `useBindFocus` 焦點鎖定機制

Hook 路徑：`next/lib/hooks/use-bind-focus.ts`

POS 高速掃碼的關鍵設計。行為規則：
- **正常狀態**：任何鍵盤輸入自動將焦點集中到商品掃描輸入框
- **例外狀態**（焦點不強制轉移）：
  - 目前焦點已在某個 Modal 或 Popover 容器內
  - 目前焦點在其他 `<input>` 或 `<textarea>` 等可輸入元件

這個機制確保銷售員可以連續拿起掃描槍掃碼，無需每次手動點擊輸入框。

### `scanItem(query)` 完整執行流程

```
scanItem(query) 呼叫後：

1. 檢查 normalItems 中是否已有相同商品（非 OPEN_PRICE 類型）
   ├─ 有 → 累加數量（amount + 1）→ 結束
   └─ 無 → 繼續

2. fetchItem(query) 從本地 DB 查詢商品資料（先查 name，再查 barCode）
   ├─ 查無 → throw Error('查無此商品')
   └─ 查到 → 繼續

3. 偵測是否為時價商品（openPriceMin != null && openPriceMax != null）
   ├─ 是 → 設定 pendingOpenPrice（驅動 OpenPriceDialog）→ 結束
   └─ 否 → 繼續

4. 根據會員狀態選擇價格：
   ├─ member !== null → 使用 memberPrice（會員價）
   └─ member === null → 使用 labelPrice（定價）

5. 建立 CheckoutItem（saleItemType: 'NORMAL'），加入 normalItems
```

### 時價商品定價流程

時價商品（如活體動物）沒有固定售價，門市人員需手動輸入。

```
1. scanItem 偵測到時價商品 → 設定 pendingOpenPrice
2. OpenPriceDialog 顯示（auto-focus 售價欄位）
   - 顯示：料件編號/條碼、商品名稱、建議售價區間
   - 驗證：openPriceMin <= 售價 <= openPriceMax
3. 確認 → 組裝 CheckoutItem（saleItemType: 'OPEN_PRICE'）
   - memberPrice = labelPrice = 輸入的售價（無固定定價）
4. addOpenPriceItem → 加入 openPriceItems（同名同價合併，不同價獨立）
5. pendingOpenPrice 清除，Dialog 關閉
```

**為什麼每次掃描都要重新定價？**
同一種時價商品的每一件售價可能不同（例如同品種的魚大小不同），因此不像一般商品可以自動累加數量。

### 會員價即時同步機制（Store Subscription）

`useItems` 訂閱 `useCheckoutMember` 的 `member` 狀態。觸發時機：
- 會員**登入**→ 遍歷整個購物車，所有商品價格切換為 `memberPrice`
- 會員**登出**→ 遍歷整個購物車，所有商品價格切換為 `labelPrice`

注意：此 subscription **僅處理 `normalItems`**，`openPriceItems` 和 `adjustPriceItems` 不受影響（時價由人工決定，變價已授權固定）。

---

## 商品變價功能

**元件**：`next/app/checkout/components/price-change-dialog.tsx`

### 必填欄位

| 欄位 | 說明 | 稽核目的 |
|------|------|---------|
| `reason` | 變價原因（下拉選擇） | 記錄業務理由 |
| `authorizer` | 授權主管員編 | 內控追蹤，確認有主管授權 |

### `adjustItemPrice` 執行邏輯

```
adjustItemPrice({ itemName, newPrice, amount, reason, authorizer })

情境 A：變價數量 < 原始數量
  1. 從 normalItems 扣除指定數量
  2. 剩餘數量以新價格移入 adjustPriceItems
  3. 原始數量部分保留在 normalItems（維持原價）

情境 B：變價數量 = 原始數量
  1. 將整筆商品從 normalItems 移除
  2. 以新價格、授權資訊建立新項目，移入 adjustPriceItems
```

### 稽核資訊保留

`adjustPriceItems` 中每筆紀錄含有：
- `reason`: 變價原因
- `authorizer`: 授權主管員編
- `originalPrice`: 原始定價

這些欄位最終會存入 `offline_sale.lines.items`，供後台查核。

---

## 購物車顯示元件

**`cart-list.tsx`**：使用 `ScrollArea` 處理列表捲動，支援 100+ 件商品不卡頓。

**`cart-item/index.tsx`**：依 `variant` 切換兩種顯示風格（`default` / `compact`）。

**`cart-item-default.tsx`** 顯示邏輯：

| 商品類型 | 背景色 | 特殊標記 |
|----------|--------|---------|
| 一般商品 | 白色 | — |
| 變價商品 | 琥珀色（amber） | 顯示授權人名稱 |
| 時價商品 | 白色 | 僅提供移除操作（無數量調整） |

**`CartItemPromotion`**（內嵌於 `cart-item-default.tsx`）：
- 在商品行下方展示「可能適用」的促銷活動提示清單
- 資料來源為後端活動設定，讓銷售員即時了解此商品是否能觸發活動

---

## Store State 與 Actions

### State

| 欄位 | 型別 | 說明 |
|------|------|------|
| `normalItems` | `CheckoutItem[]` | 一般正常銷售的商品列表 |
| `adjustPriceItems` | `CheckoutItem[]` | 經授權手動變價的商品列表 |
| `openPriceItems` | `CheckoutItem[]` | 時價商品列表（已確認價格） |
| `pendingOpenPrice` | `PendingOpenPrice \| null` | 等待定價的時價商品（驅動 OpenPriceDialog） |

### Actions

| Action | 說明 |
|--------|------|
| `scanItem(query)` | 掃描條碼的主要入口，優先累加、否則查詢 API |
| `addItem(item)` | 直接新增商品，同品項累加數量 |
| `updateItemAmount(name, amount)` | 更新指定商品數量 |
| `adjustItemPrice(params)` | 變價並分拆至 `adjustPriceItems` |
| `addOpenPriceItem(item)` | 新增時價商品（同名同價合併，不同價獨立），同時清除 pendingOpenPrice |
| `removeOpenPriceItem(name, price)` | 依 name + price 移除時價商品 |
| `clearOpenPriceItems()` | 清空所有時價商品 |
| `clearPendingOpenPrice()` | 取消定價 Dialog |
| `clearAll()` | 清空整個購物車 + pendingOpenPrice（結帳完成後呼叫） |

### 合併策略

- **`normalItems`**：同名稱商品合併為一筆（累加 `amount`）
- **`adjustPriceItems`**：同名稱**且同變價金額**才合併；不同變價金額的分開顯示（因為原因/授權人可能不同）
- **`openPriceItems`**：同名稱**且同售價**才合併；不同售價的分開顯示（每次定價可能不同）
