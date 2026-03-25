# Step 4-5：加購、贈品、點加金對話框

---

## Step 4：點擊「小計」進入對話框

### `handleSubtotalClick`（`next/app/checkout/page.tsx`）

進入對話框的驗證條件（任一不符則阻擋並顯示提示）：

| 驗證項目 | 說明 |
|----------|------|
| `saler !== null` | 銷售員已登入 |
| `itemCount > 0` | 購物車至少有一件商品 |

通過後：`setShowAddonGiftDialog(true)` 開啟對話框。

---

## 加購/贈品/點加金對話框

**元件**：`next/app/checkout/components/addon-gift-dialog/index.tsx`

對話框頂部提供搜尋框（透過關鍵字篩選活動名稱或商品名稱），下方為三個分頁 Tab。

---

### 加購（Addon）分頁

**Store**：`next/lib/stores/checkout/items/use-addons.ts`

**顯示內容**：
- 列出當前適用的加購活動（來自後端活動設定）
- 每個活動下展示可選的加購商品，含圖片、名稱、售價

**選擇邏輯**：
- 可選擇活動內不同商品及其數量
- 即時計算所有已選加購商品的小計金額（顯示於對話框底部）

**條碼掃描支援**（`barcode-input.tsx`）：
- 在對話框內也可直接使用掃描槍
- 若掃描到的條碼出現在多個加購活動中 → 彈出選擇清單讓銷售員挑選活動
- 確認後將商品加入對應活動的加購選擇

---

### 贈品（Freebie）分頁

**Store**：`next/lib/stores/checkout/items/use-freebies.ts`

**顯示內容**：
- 列出當前適用的贈品活動
- 每個活動下展示可領取的贈品，價格固定標示為 0 元

**業務限制**：

**互斥驗證**（`isFreebieValid`）：
- 不同贈品活動間若有互斥標記（由後端活動設定決定），只能擇一選取
- 選擇與已選活動互斥的贈品時，顯示提示並阻擋選取

**資料記錄**：選擇後需記錄關聯的 `posFreebie` 活動原始資料，在後續計算器中使用。

---

### 點加金（Point+Money）分頁

**Store**：`next/lib/stores/checkout/discount/point-promotion/use-point-promotion.ts`

**顯示內容**：
- 活動列表來自 `validPointPromotions`（由 `updateValidPointPromotions()` 載入）
- 每個活動顯示所需點數＋補足金額，以及可兌換的商品

**即時點數顯示**：
- 頂部顯示 `remainingPoints`（考慮已兌換項目後的剩餘可用點數）
- 底部顯示本次已使用總點數（`totalPoints`）

**兌換驗證邏輯**（`redeemPointItem` 內部）：
1. 檢查活動是否有**限購數量**（`maxQuantity`），超量時拒絕
2. 計算此次兌換需要的點數
3. 驗證 `remainingPoints` 是否足夠
4. 不足時顯示錯誤，拒絕兌換

**即時點數更新**：
- 兌換成功 → 呼叫 `checkoutMember.redeemPoints(points)` 即時扣減
- 移除已兌換項目 → 呼叫 `checkoutMember.recoverPoints(points)` 即時退回

**條碼掃描支援**：
- 呼叫 `redeemPointItemByBarcode(barcode)` 直接查找對應活動並兌換

---

## Step 5：確認選擇 → `handleAddonGiftConfirm`

**函數**：`handleAddonGiftConfirm`（`next/app/checkout/page.tsx`）

### 完整執行序列

```
handleAddonGiftConfirm({
  addonSelections,     // AddonSelection[]
  freebieSelections,   // FreebieSelection[]
  pointItemSelections  // PointItemSelection[]
}) 呼叫後：

1. 依活動分組加購商品
   for each addonGroup:
     addonActions.addAddonItems(items, posFreebie)
     （自動合併相同活動中的相同料件，累加數量）

2. 依活動分組贈品商品
   for each freebieGroup:
     freebieActions.addFreebieItems(items, posFreebie)
     （price 固定為 0）

3. 逐一兌換點加金項目（for-await 迴圈確保順序執行）
   for each pointItem:
     await pointPromotionActions.redeemPointItem(promotionName, item)
     → 內部自動呼叫 checkoutMember.redeemPoints()（即時扣減）

4. 重置所有優惠輸入狀態
   memberCouponActions.reset()
   discountCodeActions.reset()
   memberPointsActions.reset()
   （原因：見下方說明）

5. await saleActions.calculateCheckoutDiscount()
   （依序執行完整的 10 個折扣計算器管道）

6. setShowPromotionSummaryDialog(true)
   → 關閉 AddonGiftDialog，開啟促銷結算確認對話框
```

### 步驟 4 重置的必要原因

新增的加購商品、點加金商品會改變訂單小計，導致：
- 已套用的整單折扣門檻可能不再滿足（例如原本 $1,000 滿額折扣，加購後超過門檻可能有更好活動）
- 點數折抵上限（通常是訂單金額的某個百分比）隨之改變
- 已驗證的優惠券可能基於舊金額計算，需要重新套用

---

## 相關 Store State 與 Actions

### `useAddons` Store

| State | 說明 |
|-------|------|
| `addonItems` | `FreebieCheckoutItem[]` — 已選擇的加購商品列表 |
| `applyPosFreebies` | `PosFreebieLocalRecord[]` — 關聯的活動原始記錄 |

| Action | 說明 |
|--------|------|
| `addAddonItems(items, posFreebie)` | 加入並合併同活動同料件 |
| `posAddonCalculator(iterate)` | 折扣計算器：轉換為 `FREEBIE_ADDON` 型別銷售明細 |
| `clear()` | 清除所有加購選擇 |

### `useFreebies` Store

| State | 說明 |
|-------|------|
| `freebieItems` | `FreebieCheckoutItem[]` — 已選擇的贈品列表 |
| `applyPosFreebies` | `PosFreebieLocalRecord[]` — 關聯的活動原始記錄 |

| Action | 說明 |
|--------|------|
| `addFreebieItems(items, posFreebie)` | 加入贈品，price 固定為 0 |
| `posFreebieCalculator(iterate)` | 折扣計算器：轉換為 `FREEBIE_GIVE` 型別銷售明細 |
| `clear()` | 清除所有贈品選擇 |

### `usePointPromotion` Store

| State | 說明 |
|-------|------|
| `validPointPromotions` | `Promise<PointPromotionLocalRecord[] \| null>` — 有效活動清單 |
| `pointItems` | `PointPromotionStateItem[]` — 已兌換的點加金商品 |
| `totalPoints` | `number \| null` — 本次使用的總點數 |

| Action | 說明 |
|--------|------|
| `updateValidPointPromotions()` | 根據當前門市篩選有效活動 |
| `redeemPointItem(promotionName, item)` | 兌換（含驗證 + 扣點） |
| `redeemPointItemByBarcode(barcode)` | 條碼掃描直接兌換 |
| `removePointItem(promotionName, itemName)` | 移除並退回點數 |
| `pointPromotionCalculator(iterate)` | 折扣計算器：轉換為 `POINT_PLUS_MONEY` 型別 |
| `clear()` | 清除所有點加金選擇 |
