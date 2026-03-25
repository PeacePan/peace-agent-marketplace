# 調撥單類型（type）差異

## 四種調撥單別

| 類型 | 名稱 | 觸發方式 | 是否走 DSV | 來源倉庫限制 |
|-----|-----|---------|-----------|------------|
| `WH` | 總倉調撥 | 人工建立 | ✅ 是（預設）| W17R01 / W17R05 |
| `WHAT` | 總倉自動調撥 | 系統自動（hqreorder 任務） | ✅ 是（預設）| W17R01 / W17R05 |
| `ST` | 門市調撥 | 人工建立 | ❌ 否 | 門市三碼 / S000 前綴 |
| `DN` | 捐贈調撥 | 人工建立 | ❌ 否 | 無限制 |

## WH（總倉調撥）

- **特徵**：人工建立，需要通過「總倉調撥可分配數」檢查（`hqWareHouseStatus` 狀態機）
- **DSV 整合**：建立後自動呼叫 `upsertDSVOrder`，產生 DSV 出貨單與明細
- **批號回填**：DSV 出貨明細建立後，`dsvorderdetail.batchPolicy` 自動回填批號與效期
- **鎖庫支援**：可設定 `unlock` 鎖庫別，限制調撥數量在鎖庫保留數內
- **skipLogistics**：可切換為一般調撥（不走 DSV），須在未拋單前操作
- **isHqWareHouseTransfer**：來源倉庫必須是 `W17R01` 或 `W17R05`

```typescript
// NorwegianForest/tables/inventory/scripts/transferorder/policy.ts
export function isHqWareHouseTransfer(locationName: string): boolean {
  return locationName === 'W17R01' || locationName === 'W17R05';
}
```

## WHAT（總倉自動調撥）

- **特徵**：由 `hqreorder.ts` 系統任務建立，不需要人工干預
- **hqWareHouseStatus**：由任務建立時直接設為 `可調撥`（任務已確認可調撥才建立）
- **自動批號分配**：批號與效期由任務建立時指定（不需 batchPolicy 回填）
- **fromTransferOrderName**：記錄來源的 WH 調撥單，用於雙向數量同步
- **人工更新時**：被人工更新時必須重新走 WH 的檢查流程（視為 WH 處理）
- **防無限迴圈**：任務執行時透過 `skipBeforeUpdate: true` + `ignoreDSVOrderDetailPolicy: true` 旗標跳過循環邏輯

```typescript
// 判斷是否由系統任務觸發（非人工）
const isTriggerByHuman = !Validator.isCronTrigger(ctx.user);

// policy.ts 中的 WHAT 處理邏輯
if (to.body.type === 'WHAT') {
  if (!to.lines?.items?.length) {
    systemUpdateBody.hqWareHouseStatus = '不可調撥'; // 無明細直接預約封存
    systemUpdateBody.reserveArchive = true;
  } else if (to.body.hqWareHouseStatus !== '可調撥') {
    systemUpdateBody.hqWareHouseStatus = '可調撥'; // 任務建立的都是可調撥
  }
}
```

## ST（門市調撥）

- **特徵**：門市之間的調撥，不走 DSV 物流系統
- **來源/目標倉庫**：必須是三碼數字（門市 ID）或 `S000` 前綴
- **料件限制**：不允許捐贈料件（捐贈料件只能用 DN 類型）

## DN（捐贈調撥）

- **特徵**：捐贈用途的調撥，不走 DSV
- **料件限制**：表身列中的料件**必須全部是捐贈料件**（`Procurement.isDonateItem()` 判斷）
- **特殊**：WH/ST 類型中若混入捐贈料件，policy 會直接拒絕

## 共同驗證規則

```typescript
// policy.ts 中的共同檢查
if (fromLocation === toLocation) return '不能自己調撥給自己';
if (!oldTo && !toItems.length) return '調撥明細不可為空';

// 捐贈料件檢查（適用 DN, ST, WH）
if (to.body.type === 'DN' && !isDonateItem) → 拒絕
if (to.body.type !== 'DN' && isDonateItem) → 拒絕

// 藥品檢查（目標倉庫為門市時）
if (Validator.isStoreId(toLocation)) → 檢查目標門市是否有藥牌
```

## DSV 上線前後的差異（2025-07-29）

**DSV 上線時間點**：台灣時間 2025-07-29 05:00:00

- **上線前建立的調撥單**：沒有 `hqWareHouseStatus` 欄位，一律視為 `可調撥`，不檢查
- **上線後建立的 WH 調撥單**：必須經過「總倉調撥可分配數」非同步檢查，狀態進入 `検查中`

```typescript
// policy.ts 中的時間點判斷
if (dayjs(to.body._createdAt).isAfter(dayjs.tz('2025-07-29 05:00:00', 'Asia/Taipei'))
    && isHqWareHouseTransfer(fromLocation)) {
  // DSV 上線後的新邏輯
} else if (to.body.hqWareHouseStatus !== '可調撥') {
  systemUpdateBody.hqWareHouseStatus = '可調撥'; // 上線前統一設為可調撥
}
```
