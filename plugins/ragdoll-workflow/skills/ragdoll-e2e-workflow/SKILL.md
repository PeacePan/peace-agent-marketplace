---
name: ragdoll-e2e-workflow
description: >
  Ragdoll 專案 E2E 測試建立工作流程指南。當需要為 Ragdoll 專案撰寫、新增或修復 Playwright E2E 測試時必須使用此技能。
  適用情境：「幫我寫 XX 的 e2e 測試」、「新增測試案例給 XX 頁面」、「為 XX 功能建立端對端測試」、「e2e 測試失敗請修復」、「補充結帳流程的測試覆蓋率」等。
  此技能提供從閱讀前置知識、建立 Page Object、準備測試資料、撰寫測試，到執行後錯誤診斷的完整流程。
---

# Ragdoll E2E 測試建立工作流程

## 重要前提：先取得知識

在開始撰寫任何 e2e 測試前，**必須先讀取以下兩個技能的完整內容**，因為它們提供了撰寫正確測試所必需的業務邏輯與最佳實踐：

1. **`ragdoll-checkout-flow`** — 結帳流程每個步驟的業務邏輯、Store 架構、資料結構定義。沒有這份文件就無法理解要測試的行為。
2. **`playwright-best-practices`** — Playwright 測試的最佳實踐，包含 Page Object Model、Fixture、斷言等。

---

## 工作流程步驟

### Step 1：了解測試範圍

確認以下事項：
- 要測試的**頁面或對話框**是什麼？
- 測試的**業務場景**是什麼（例如：現金結帳、信用卡、加購商品）？
- 需要哪些**外部依賴**（GraphQL API、SQLite、硬體設備）？

### Step 2：建立或更新 Page Object

每個要操作的頁面或對話框，都必須在 `test/e2e/pages/` 下建立對應的 Page Object 類別。

**原則：**
- 每個方法代表一個**具有業務意義的操作**，不是單純的技術操作
- 正確範例：`loginSaler(employeeId)`、`scanItem(barcode)`、`validateCoupon(couponCode)`
- 錯誤範例：`clickButton()`、`fillInput(value)` — 這種命名沒有業務含義
- 方法內部處理等待邏輯（`waitForSelector`、`waitForResponse`），不要讓測試檔案自己等待

**範例結構：**
```typescript
// test/e2e/pages/my-dialog.ts
import { Page } from '@playwright/test';

export class MyDialog {
  constructor(private readonly page: Page) {}

  async waitForOpen() {
    await this.page.waitForSelector('[data-testid="my-dialog"]');
  }

  async confirmSelection() {
    await this.page.click('[data-testid="confirm-btn"]');
    await this.page.waitForSelector('[data-testid="my-dialog"]', { state: 'hidden' });
  }

  async skipSelection() {
    await this.page.click('[data-testid="skip-btn"]');
  }
}
```

**現有 Page Objects（可直接使用或繼承）：**
- `CheckoutPage` — 登入、搜尋會員、掃商品、點擊小計、發票選項
- `AddonGiftDialog` — 加購/贈品/點加金對話框
- `PromotionSummaryDialog` — 優惠摘要、折扣碼、點數折抵
- `SummaryPage` — 付款方式選擇、完成結帳

### Step 3：準備測試資料

測試資料存放於 `test/e2e/fixtures/test-data/`，使用工廠函數建立，並在 spec 檔案最上方定義。

**可用的工廠函數：**
```typescript
import { createTestItem, TEST_ITEM_A, TEST_ITEM_B } from '../fixtures/test-data/items';
import { createTestMember, TEST_MEMBER } from '../fixtures/test-data/members';
import { createTestSaler, TEST_SALER } from '../fixtures/test-data/saler';
import { createTestCoupon } from '../fixtures/test-data/coupons';
import { createTestFreebie, createTestPointPromotion } from '../fixtures/test-data/promotions';
```

**資料設計原則：**
- 只建立**這個測試場景真正需要**的最小資料集
- 不同的測試場景應建立不同的資料常數，名稱要反映場景（例如 `ADDON_TEST_ITEM`、`COUPON_TEST_MEMBER`）
- 若需要新的工廠函數，在對應的 `test-data/*.ts` 檔案中新增

### Step 4：撰寫測試檔案

**目錄規則：**
```
test/e2e/
├── 0-basic/          # 應用程式啟動驗證
├── 1-checkout-flow/  # 核心結帳流程（現金、信用卡）
├── 2-promotions/     # 加購、贈品、會員優惠、複合促銷
├── 3-invoice-options/# 發票類型
```

**每個測試檔案的必要結構：**

```typescript
import { test, expect } from '@playwright/test';
import { useElectronApp } from '../fixtures';  // 必須使用這個
import { CheckoutPage } from '../pages/checkout-page';
// ... 其他 Page Object

// 1. 定義測試資料
const testItem = createTestItem({ ... });
const testSaler = TEST_SALER;

// 2. 啟動 App（每個 describe block 都需要）
const launch = useElectronApp({
  salersByName: { [testSaler.employeeId]: testSaler },
  itemsByBarcode: { [testItem.barCode]: testItem },
  members: [],
  petParkCoupons: [],
  freebies: [],
  // 依需求加入 GraphQL mock 資料
});

test.describe('功能名稱', () => {
  test('should 預期行為描述', async () => {
    const { window } = launch;
    const checkoutPage = new CheckoutPage(window);

    // 使用 Page Object 的業務操作方法
    await checkoutPage.loginSaler(testSaler.employeeId);
    await checkoutPage.scanItem(testItem.barCode);

    // 斷言也要有業務意義
    await expect(window.locator('[data-testid="cart-total"]')).toContainText('450');
  });
});
```

**關鍵規則：**
- `useElectronApp` 必須在 `describe` block 之外呼叫（它內部使用 `beforeAll`/`afterAll`）
- 所有外部依賴（API、硬體）都已在 fixture 中自動 mock，不需要額外設定
- 測試名稱使用 `should + 行為描述`

### Step 5：執行測試並診斷錯誤

執行測試：
```bash
# 執行特定檔案
npm run test:e2e test/e2e/1-checkout-flow/cash-no-member.spec.ts

# 跳過重建 App，適合快速重跑同一個測試檔案
npm run test:e2e test/e2e/1-checkout-flow/cash-no-member.spec.ts -- --skip-build

# 執行全部
npm run test:e2e

# 跳過重建 App 執行全部（適合修復後快速驗證）
npm run test:e2e -- --skip-build
```

**⚠️ 錯誤診斷的黃金法則：測試失敗時，絕對不可以自行推論錯誤原因。**

必須到 `test/e2e/test-results/` 查看：
- **截圖**（`.png` 檔案）— 看失敗當下頁面的實際狀態
- **錯誤訊息**（`-error.txt` 或 Playwright HTML report）— 看實際的 assertion failure 訊息
- **Trace 檔案**（`.zip`）— 用 `npx playwright show-trace <file>` 查看完整互動過程

根據**實際看到的截圖和錯誤訊息**來修復，而不是根據猜測。常見需要確認的情況：
- `data-testid` 是否正確（截圖中看實際 DOM）
- 等待時機是否正確（截圖中看頁面狀態）
- Mock 資料格式是否符合預期（看 error message 中的資料）

---

## 常見錯誤與避免方式

| 錯誤 | 正確做法 |
|------|----------|
| 在測試中直接 `page.click('[data-testid="btn"]')` | 封裝在 Page Object 的業務方法中 |
| 自行推論測試失敗的原因 | 去 `test-results/` 看截圖和錯誤訊息 |
| 在 `describe` 內呼叫 `useElectronApp` | 在 `describe` 外部呼叫 |
| 建立過多不必要的測試資料 | 只建立測試場景需要的最小資料集 |
| 不等待 UI 狀態變化就繼續操作 | 在 Page Object 方法內處理等待邏輯 |
