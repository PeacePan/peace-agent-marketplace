# Step 1-2：銷售員登入與會員登入

---

## Step 1：銷售員登入

**元件**：`next/app/checkout/components/saler-login.tsx`
**Store**：`next/lib/stores/checkout/saler/use-saler.ts`

### UI 互動邏輯

- 本地 state `salerInput` 控制受控輸入框
- 支援 `Enter` 鍵觸發登入（`onKeyDown` event）
- 登入成功後切換為顯示員工姓名 + 「登出」按鈕的模式
- 登入中透過 `runningActions.login` 顯示 `Loader2` 旋轉動畫（防止重複送出）

### Store State

| 欄位 | 型別 | 說明 |
|------|------|------|
| `saler` | `Saler \| null` | 目前已登入的銷售員資料（null 表示未登入） |

### Store Actions

| Action | 參數 | 說明 |
|--------|------|------|
| `login` | `employeeId: string` | 呼叫 `ragdollAPI.salerLogin` 進行員工認證，成功後更新 `saler` |
| `logout` | — | 清除 `saler` 狀態 |

### 業務規則

- 銷售員**必須先登入**才能點擊「小計」進入下一流程
- `handleSubtotalClick`（在 `checkout/page.tsx`）中明確驗證 `saler !== null`，不符合時阻擋並顯示提示

---

## Step 2：顧客電話號碼（會員）登入

**元件**：`next/app/checkout/components/member-login/index.tsx`

### 子元件清單

| 元件 | 說明 |
|------|------|
| `member-points-info.tsx` | 顯示剩餘點數與依匯率換算的折抵金額 |
| `member-coupon-info.tsx` | 顯示門市/美容可用優惠券數量，點擊展開清單彈窗 |
| `member-pet-info.tsx` | 統計並顯示該會員名下的寵物物種數量 |

**Store**：`next/lib/stores/checkout/member/use-checkout-member.ts`

### 三階段智慧搜尋流程（`searchMember` 函數）

搜尋依序嘗試以下三個階段，若上一階段找到唯一結果則停止：

**第一階段：精確搜尋**
- 手機號碼自動轉換為國際格式（`0912345678` → `+886912345678`）
- 或以會員 ID 直接查詢

**第二階段：常用欄位模糊搜尋**
- 姓名片段或手機號碼片段

**第三階段：進階欄位搜尋**
- 聯絡人或顯示名稱欄位

### 登入成功後的並行非同步載入（Deferred Promise 模式）

`setMember(value)` 呼叫後，立即並行啟動以下 5 個非同步請求，並以 Promise 佔位方式存入 Store state。UI 層透過 React 19 的 `use(promise)` 搭配 `Suspense` 邊界處理 Loading 狀態。

```
setMember(value) 呼叫後立即並行啟動：
  ├─ fetchStoreCoupons()    → storeCoupons: Promise<PetParkCoupon[]>
  ├─ fetchSalonCoupons()    → salonCoupons: Promise<PetParkCoupon[]>
  ├─ fetchAvailablePoints() → availablePoints: Promise<number>
  ├─ fetchHistorySales()    → historySales: Promise<MemberHistorySale[]>
  └─ fetchPets()            → pets: Promise<PosPet[]>
```

**中止機制**：切換會員時對舊請求呼叫 `abort()`，避免 Race Condition，確保畫面始終反映最新一次搜尋結果。

### 登入後觸發的額外操作（`handleMemberLogin` 中）

1. `refreshPointDiscount()` — 刷新點數折現匯率設定（例如 10 點換 1 元）
2. `updateValidPointPromotions()` — 取得當前門市有效的點加金活動清單

### Store State

| 欄位 | 型別 | 說明 |
|------|------|------|
| `member` | `WonderPetMember \| null` | 目前登入的會員基本資料 |
| `storeCoupons` | `Promise<PetParkCoupon[] \| null>` | 門市通路可用優惠券（非同步） |
| `salonCoupons` | `Promise<PetParkCoupon[] \| null>` | 美容通路可用優惠券（非同步） |
| `availablePoints` | `Promise<number \| null>` | 會員帳戶可用總點數（非同步） |
| `remainingPoints` | `Promise<number \| null>` | 扣除本次預計折抵後剩餘點數 |
| `historySales` | `Promise<MemberHistorySale[] \| null>` | 近 3 個月消費紀錄（非同步） |
| `pets` | `Promise<PosPet[] \| null>` | 該會員名下的寵物清單（非同步） |

### Store Actions

| Action | 說明 |
|--------|------|
| `setMember(value)` | 三階段搜尋 + 並行非同步載入的主要入口 |
| `redeemPoints(points)` | 預扣點數（點加金兌換時呼叫），更新 `remainingPoints` |
| `recoverPoints(points)` | 退回已預扣的點數（移除點加金項目時呼叫） |
| `clear()` | 登出會員，清除所有 Promise 與暫存資料 |

### 點數查詢與排序規則

- **來源**：`pointaccount` 資料表
- **過濾條件**：餘額 > 0 且未過期
- **排序邏輯**：**先到期者優先**（確保門市人員能優先扣除即將到期的點數，避免點數浪費）
