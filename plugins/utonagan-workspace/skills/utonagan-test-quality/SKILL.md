---
name: utonagan-test-quality
description: Utonagan（店系統）vitest 測試的品質規範：有意義測試的三個條件、反模式清單（Mock-then-query、Passthrough、取數層 Passthrough、SWR 快取汙染、元件只驗 mock 資料）、各層該怎麼測、Given/When/Then 格式與自我檢核問題。撰寫、審查或修復 Utonagan 的 `__tests__/` 測試前一律先載入；看到測試只驗 mock 出來的資料、只驗「有被呼叫」、或測試之間互相影響時也應使用。
---

# Utonagan 測試品質規範

測試數量與覆蓋率都不等於保護力。一條測試只有在「需求改壞時會失敗」時才有價值；只驗證 mock 自己回的資料、或只驗證「有被呼叫」的測試，綠燈亮著也保護不了任何需求，還會讓之後的重構誤以為安全。本規範用來擋下這類測試。

## 有意義測試的三個條件

一條測試必須同時滿足：

1. **能說明受測的業務行為**（是業務場景，不是函式名稱）
2. **若把被測邏輯改成永遠回傳固定值，測試應該失敗**
3. **Assertion 驗證的是行為結果，不是中間步驟**

## 反模式清單

| 反模式 | 說明 | 如何判斷 |
|---|---|---|
| **Mock-then-query** | 自己設資料再用 find / filter 查同一份資料 | 把被測邏輯移除後測試仍會 pass |
| **Passthrough** | 只確認函式有被呼叫，沒有驗證輸出 | assertion 只有 `toHaveBeenCalled`，沒有回傳值或畫面驗證 |
| **Internal detail** | 測實作細節（某方法被呼叫幾次）而非行為 | 重構實作但不改行為後測試失敗 |
| **Guaranteed-pass** | assertion 條件必然成立 | 不執行受測函式，assertion 仍然 pass |
| **取數層 Passthrough** | 取數函式（`fetchX`）刻意不做業務判斷，只 mock `client` 再驗證「有被呼叫」，等於在測 mock。有價值的是組出的 filter 是否正確、取回資料與純邏輯的銜接 | 拿掉取數函式的 filter 組裝邏輯，測試仍然 pass |
| **SWR 快取汙染** | 渲染用到 SWR 的 Hook 或元件時沒有隔離快取，測試之間共用全域快取，結果變成順序相依：單獨跑會過、整批跑會掛，或反之 | 把測試順序打亂或單獨跑，結果不同 |
| **元件只驗 mock 資料** | 把 hook 或 client 設成固定回傳值，只驗證畫面渲染出該筆資料，是 Mock-then-query 的 UI 版 | 把元件的狀態分支拿掉後測試仍會 pass；有價值的是四態切換與「使用者操作 → 觸發的呼叫」 |

## 各層該怎麼測

Utonagan 依 `Utonagan/CLAUDE.md` 分為取數、純邏輯、Hook、UI 四層，測試放在被測單元旁的 `__tests__/`，檔名 `<單元>.test.ts(x)`。測試檔沿用專案排版（Tab 縮排、單引號、分號、尾隨逗號）。

| 層 | 測什麼 | 怎麼測 | 現有範例 |
|---|---|---|---|
| 純邏輯 | 篩選、彙總、排序、換算等純函式 | 直接呼叫，不需任何 mock | `lib/report/negative-stock/__tests__/negativeStock.test.ts` |
| Hook（key 與 config） | 組出的 SWR key、傳給 SWR 的行為設定；`null` key 時不發查詢 | `vi.mock('@/lib/swr', ...)` 攔截 `useJavacatQuery`，記錄呼叫參數後斷言 | `lib/shell/__tests__/useStoreName.test.ts` |
| 元件（含取數） | 四態切換、使用者操作、送出的查詢 | `vi.mock('@/src/graphql/client', ...)` 注入假 client；用 `SWRConfig` 的 `provider: () => new Map()` 隔離快取；以 `fireEvent` 操作（專案沒有 `user-event`） | `components/pricetag/tabs/__tests__/TabPromo.test.tsx` |

### 純邏輯：直接驗證輸入到輸出

（取自 `lib/report/negative-stock/__tests__/negativeStock.test.ts`）
```ts
describe('負庫存報表', () => {
	const rows = buildNegativeStockRows(
		[
			{ item: 'A', amount: -3, updatedAt: '2026/06/03 14:22' },
			{ item: 'B', amount: 5, updatedAt: '2026/06/03 10:00' },
			{ item: 'C', amount: -8, updatedAt: '2026/06/02 18:40' },
		],
		itemMap
	);

	it('只列庫存為負的料件，庫存非負者排除', () => {
		expect(rows.map((row) => row.itemCode)).toEqual(['C', 'A']);
	});
```

Given 三筆庫存（兩筆為負、一筆為正）／When 組出報表列／Then 只剩負庫存且依最負排前。拿掉篩選邏輯，這條測試會失敗。

### Hook：攔截 `lib/swr`，驗證 key 與 config

（取自 `lib/shell/__tests__/useStoreName.test.ts`）
```ts
// 攔截中台存取封裝，改為記錄呼叫參數，驗證 useStoreName 傳給 SWR 的行為設定，
// 不實際打 graphql-pos。
const { useJavacatQueryMock } = vi.hoisted(() => ({
	useJavacatQueryMock: vi.fn<(key: unknown, fetcher: unknown, config?: unknown) => { data: string }>(() => ({
		data: '001文化店',
	})),
}));

vi.mock('@/lib/swr', () => ({
	useJavacatQuery: useJavacatQueryMock,
}));
```

（取自 `lib/shell/__tests__/useStoreName.test.ts`）
```ts
	it('已登入時以門市編號組出查詢 key；未登入（null）時 key 為 null，SWR 不發查詢', () => {
		useStoreName('001');
		expect(useJavacatQueryMock.mock.calls[0]?.[0]).toEqual(['storeName', '001']);

		useJavacatQueryMock.mockClear();
		useStoreName(null);
		expect(useJavacatQueryMock.mock.calls[0]?.[0]).toBeNull();
	});
```

這裡驗證的是「組出什麼 key、傳什麼 config」，是這個 Hook 自己的邏輯，不是在測 mock 回傳了什麼。

**何時需要 `renderHook`**：上面的 `useStoreName` 能直接當函式呼叫，只因為 mock 掉 `useJavacatQuery` 之後它沒有任何 React state。Hook 內只要用到 `useState`、`useEffect`、`useRef` 等 React hook，就必須用 `@testing-library/react` 的 `renderHook` 執行，否則會出現 `Invalid hook call`。現有範例：`lib/pricetag/hooks/__tests__/usePrintListDraft.test.ts`、`lib/emp-gate/__tests__/useUnlockedEmployee.test.ts`、`lib/emp-gate/__tests__/useLockOnRouteChange.test.ts`。

### 元件：注入假 client，並以獨立 SWR 快取渲染

（取自 `components/pricetag/tabs/__tests__/TabPromo.test.tsx`）
```tsx
vi.mock('@/src/graphql/client', () => ({
	getJavacatClient: () => ({
		query: {
			find: (args: { table: keyof typeof records }) => {
				findCalls.push(args.table);
				return Promise.resolve(records[args.table] ?? []);
			},
		},
	}),
}));
```

（取自 `components/pricetag/tabs/__tests__/TabPromo.test.tsx`）
```tsx
/**
 * 以獨立 SWR 快取渲染 TabPromo。
 * 指定促銷貨價卡包走 SWR 讀取，測試間共用全域快取會讓後測拿到前測的空包快取，故每次渲染都給全新快取。
 */
function renderTabPromoIsolated(onAddItems: () => void) {
	return render(
		<SWRConfig value={{ provider: () => new Map() }}>
			<TabPromo storeName="042" onAddItems={onAddItems} />
		</SWRConfig>
	);
}
```

注意 `findCalls` 逐筆記下被查詢的表，讓測試能斷言「某個操作不得送出查詢」，這是行為而非 mock 資料。

### 反例（示意，非取自專案）

```ts
// 把 hook 設成固定回傳值，再斷言畫面出現同一筆資料：移除元件的任何邏輯，測試都還是會過。
vi.mock('@/lib/pricetag/hooks/useCandidates', () => ({ useCandidates: () => ({ data: [{ name: 'A' }] }) }));
it('顯示候選料件', () => {
	render(<CandidateList />);
	expect(screen.getByText('A')).toBeInTheDocument();
});
```

## 標準格式：Given / When / Then

每條測試必須能對應：

```
Given: [系統初始狀態 / 前置條件]
When:  [觸發的操作或輸入]
Then:  [預期的業務行為結果]
```

`it(...)` 的描述文字直接寫業務結果，如上面範例的「只列庫存為負的料件，庫存非負者排除」，不要寫「應該正確運作」這類無法判斷對錯的描述。

## 時間與時區

`test/setup.ts` 把時區固定為台北時區（`Asia/Taipei`），並載入 `jest-dom`、每個測試後自動 `cleanup`。與日期有關的斷言以台北時區為準，不要在測試內另外改時區，也不要依賴執行當下的日期。

## 自我檢核問題

每條測試寫完後必須回答：

> 「若移除這條測試，哪個需求的變化會無法被偵測到？」

答不出來，這條測試必須重寫或刪除。

## 測試品質不通過的處置

以下任一情況即判定不通過，必須打回 `utonagan-rd` 或重寫，不得 commit：

| 不通過條件 | 判斷方式 |
|---|---|
| 反模式清單中的任一項 | 對照上表的「如何判斷」 |
| 缺少業務行為說明 | 測試無法對應 Given / When / Then 的 Then |
| 零業務保護價值 | 移除該測試後，沒有任何需求的回歸無法被偵測 |
