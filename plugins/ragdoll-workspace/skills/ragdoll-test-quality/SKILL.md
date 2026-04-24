---
name: ragdoll-test-quality
description: >
  Ragdoll 專案的測試品質規範，定義有意義測試的三個條件、常見反模式清單（Passthrough / Mock-then-query 等）與 Given/When/Then 標準格式。
  electron-qa 與 next-qa agent 必須在執行任何測試撰寫或驗收前遵循此規範。
---

# Ragdoll 測試品質規範

## 有意義測試的三個條件

一條測試必須同時滿足以下三點：

1. **能說明受測的業務行為**（不是函式名稱，是業務場景）
2. **若把被測邏輯改成永遠回傳固定值，測試應該失敗**
3. **Assertion 驗證的是行為結果，不是中間步驟**

## Ragdoll 常見反模式清單

| 反模式 | 說明 | 如何判斷 |
|---|---|---|
| **Mock-then-query** | 自己設資料再用 find/filter 查同一份資料 | 把查詢邏輯移除後測試仍會 pass |
| **Passthrough test** | 只確認函式有被呼叫，沒有驗證輸出 | assertion 只有 `toHaveBeenCalled`，無回傳值驗證 |
| **Internal detail test** | 測試實作細節（特定方法被呼叫幾次）而非行為 | 重構實作但不改行為後測試失敗 |
| **Guaranteed-pass test** | assertion 條件必然成立 | 不執行受測函式，assertion 仍然 pass |

## 標準格式：Given / When / Then

每條 test case 必須能對應到以下結構：

```
Given: [系統初始狀態 / 前置條件]
When:  [觸發的操作或輸入]
Then:  [預期的業務行為結果]
```

**好的測試（Next.js 層範例）：**

```typescript
// Given: 購物車中有一項商品，庫存剩 0
// When:  結帳時嘗試確認數量
// Then:  回傳庫存不足錯誤，購物車狀態不變
it('庫存不足時應拒絕結帳並保持購物車狀態', async () => {
    const { result } = setupTest({ items: [{ id: 1, qty: 1 }], stock: 0 });
    await result.current.actions.checkout();
    expect(result.current.state.error).toBe('STOCK_INSUFFICIENT');
    expect(result.current.state.items).toHaveLength(1);
});
```

**不好的測試（反模式 Mock-then-query）：**

```typescript
// ❌ 這在測 Array.find，不是業務邏輯
it('應該找到商品', () => {
    const items = [{ id: 1, name: 'A' }];
    const result = items.find(i => i.id === 1);
    expect(result).toEqual({ id: 1, name: 'A' });
});
```

**好的測試（Electron 層範例）：**

```typescript
// Given: 已有一筆促銷規則，滿 500 折 50
// When:  計算金額 600 的訂單
// Then:  折扣應為 50，最終金額應為 550
it('滿額折扣應正確計算折扣金額', () => {
    const promotion = { threshold: 500, discount: 50 };
    const result = calcDiscount(600, promotion);
    expect(result.discount).to.equal(50);
    expect(result.finalAmount).to.equal(550);
});
```

## 自我檢核問題

**MUST** 在每條測試撰寫完成後回答：

> 「若移除這條測試，哪個需求的變化會無法被偵測到？」

若答不出來，該測試**必須重寫或刪除**。

## 測試品質不通過的處置

以下任一情況即判定測試品質不通過，**MUST** 打回 RD 修正，不得 commit：

| 不通過條件 | 判斷方式 |
|---|---|
| Mock-then-query | 測試使用 mock 資料且 assertion 只驗證同一份 mock 資料的查詢結果 |
| 缺少業務行為說明 | 測試無法對應 Given/When/Then 的 Then 結果 |
| 零業務保護價值 | 移除該測試後，沒有任何需求的回歸無法被偵測 |
