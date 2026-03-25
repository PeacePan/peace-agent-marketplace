# Step 6：促銷結算對話框

---

**元件**：`next/app/checkout/components/promotion-summary-dialog/index.tsx`

此對話框是進入付款頁面前的最後確認畫面，分為左側商品概覽與右側優惠操作兩個區塊。使用者在右側進行的每次操作，都會重新觸發 `saleActions.calculateCheckoutDiscount()`，即時更新左側顯示的折扣結果。

---

## 左側面板：商品與促銷群組展示

**元件**：`promotion-summary-dialog/left-panel/promotion-item-list.tsx`

**顯示邏輯**：
- 依促銷活動將商品群組化，同一個促銷活動下的商品放在同一個區塊
- 分區塊顯示以下類型：
  - 一般商品（按套用的促銷活動分組）
  - 加購商品區塊（`FREEBIE_ADDON`）
  - 贈品區塊（`FREEBIE_GIVE`，標示 0 元）
  - 點加金商品區塊（`POINT_PLUS_MONEY`，顯示使用點數）
  - 整單折扣區塊（顯示各種整單折扣的折抵金額）

---

## 右側面板：三個優惠操作 Section

### 1. 會員優惠券（`member-coupon-section.tsx`）

**Store**：`next/lib/stores/checkout/discount/member-coupon/use-member-coupon.ts`

**UI 元素**：
- 文字輸入框（輸入券號）
- 「驗證」按鈕
- 驗證成功後顯示優惠券名稱與折抵金額

**執行流程**：
```
1. 使用者輸入券號 → 按下驗證

2. 呼叫驗證 API 確認：
   - 券號是否存在
   - 是否在有效期間內
   - 是否已被使用

3. 驗證成功 → 將券資訊存入 Store

4. 觸發 saleActions.calculateCheckoutDiscount()
   → 依序執行計算器，其中 petParkCouponDiscountCalculator
     會讀取已驗證的券，套用整單折扣

5. 更新左側面板顯示折後金額
```

---

### 2. 點數折抵（`member-points-section.tsx`）

**Store**：`next/lib/stores/checkout/discount/member-points/use-member-points.ts`

**UI 元素**：
- 滑桿（拖曳調整折抵金額）
- 數值輸入框（手動輸入折抵金額）
- 即時顯示：所需點數、折抵後應付金額

**三重上限校準邏輯**

使用者輸入的折抵金額會自動套用以下三個上限，取**最小值**：

| 上限 | 來源 | 說明 |
|------|------|------|
| 上限 1 | `PointDiscount.maxPercentage` | 後端設定的單筆訂單點數折抵上限百分比（例如最多折抵 20%） |
| 上限 2 | 當前應付小計 | 折抵金額不能超過訂單應付金額（不能產生負數應付） |
| 上限 3 | 會員剩餘可用點數換算金額 | 折抵金額不能超過會員現有點數可換算的最大金額 |

**執行流程**：
```
1. 使用者調整折抵金額

2. 自動校準：取三重上限的最小值

3. 依匯率計算所需點數
   例：折抵 $100，匯率 10 點/元 → 需 1,000 點

4. 觸發 saleActions.calculateCheckoutDiscount()
   → memberPointsCalculator 讀取折抵設定，
     產生 DISCOUNT_BY_POINTS 類型的 promotion 記錄

5. 更新應付金額顯示
```

---

### 3. 折扣碼（`discount-code-section.tsx`）

**Store**：`next/lib/stores/checkout/discount/pos-coupon/use-pos-coupon.ts`

**UI 元素**：
- 文字輸入框（輸入折扣代碼）
- 「套用」按鈕
- 套用成功後顯示折扣代碼名稱與折抵金額

**執行流程**：
```
1. 使用者輸入折扣代碼 → 按下套用

2. 呼叫 API 驗證代碼有效性

3. 驗證成功 → 將折扣資訊（百分比或直減金額）存入 Store

4. 觸發 saleActions.calculateCheckoutDiscount()
   → posCouponCalculator 讀取折扣碼，
     計算並套用折扣

5. 更新左側面板與底部總額顯示
```

---

## 確認按鈕：前往付款

按下「確認結帳」後，觸發 `handlePromotionSummaryConfirm`（`checkout/page.tsx`）：

```
1. 標記結算已確認（清除 rollback records，
   代表本次促銷選擇已定案，不允許再回頭修改）

2. connectionActions.checkInvoiceDevice()
   → 呼叫 IPC 確認發票機連線狀態

3a. 連線正常 → router.push('/summary')
3b. 連線異常 → 顯示警告 toast，阻擋跳轉（不能在無發票機的情況下結帳）
```
