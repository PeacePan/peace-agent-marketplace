# Actions 完整指南

## Actions 互相呼叫

透過 `actions` 參數可以在一個 action 中呼叫其他 action：

```typescript
const useCartStore = createStore({
  name: 'cart',
  states: {
    items: { type: 'value', initialValue: [] as Item[] },
    total: { type: 'value', initialValue: 0 },
  },
  actions: {
    addItem: ({ state, setState }, item: Item) => {
      setState({ items: [...state.items, item] });
    },
    calculateTotal: ({ state, setState }) => {
      setState({ total: state.items.reduce((sum, item) => sum + item.price, 0) });
    },
    // ✅ 可以呼叫其他 actions
    addItemAndCalculate: ({ actions }, item: Item) => {
      actions.addItem(item);
      actions.calculateTotal();
    },
  },
});
```

---

## 錯誤處理：onError vs 拋出

### 方式一：使用 onError（錯誤不拋出，只在內部處理）

```typescript
actions: {
  fetchData: {
    handler: async ({ setState, signal }) => {
      setState({ status: 'loading' });
      const data = await api.fetch({ signal });
      setState({ items: data, status: 'success' });
    },
    onError: ({ error, setState }) => {
      // 錯誤在此處理，不會拋出到呼叫端
      if (!(error instanceof PromiseAbortError)) {
        setState({ status: 'error' });
      }
    },
  },
}
```

### 方式二：不使用 onError（錯誤會拋出，可在呼叫端 catch）

```typescript
actions: {
  fetchDataWithThrow: async ({ setState, signal }) => {
    setState({ status: 'loading' });
    // 如果發生錯誤，會自動拋出
    const data = await api.fetch({ signal });
    setState({ items: data, status: 'success' });
  },
}
```

---

## Action Context 完整欄位

```typescript
interface ActionContext<TState, TActions, TInjected, TProps = never> {
  // State（Proxy，永遠指向最新值，在 await 後讀取不會 stale）
  state: TransformState<TState>;

  // 批次更新 state
  setState: (updater: Partial<TState> | ((prev: TransformState<TState>) => Partial<TState>)) => void;

  // 同一 store 的其他 actions
  actions: Actions<TActions>;

  // 注入的外部 stores（來自 useInjectedStores）
  injected: ResolvedInjected<TInjected>;

  // 外部傳入的 props（永遠是最新值，型別為 Partial<TProps>）
  props: Partial<TProps>;

  // AbortSignal（配合 strategy 取消請求）
  signal: AbortSignal;
}
```

---

## Action 返回值

Actions 可以直接返回結果，呼叫端可以 await 取得：

```typescript
actions: {
  checkout: {
    strategy: 'takeLeading',
    handler: async ({ state, setState, signal }) => {
      setState({ status: 'processing' });
      const order = await api.createOrder(state.cart, { signal });
      setState({ status: 'success' });

      // ✅ 直接返回結果，可在呼叫端使用
      return order;
    },
  },
}

// 呼叫端
const order = await actions.checkout();
```

---

## 完整 Action 配置格式

```typescript
// 簡單函數形式（無 strategy）
actions: {
  increment: ({ state, setState }) => {
    setState({ count: state.count + 1 });
  },
}

// 完整物件形式（含 strategy 和 onError）
actions: {
  submit: {
    strategy: 'takeLeading',  // 'takeLatest' | 'takeLeading' | 'takeEvery'
    handler: async ({ state, setState, signal }) => {
      // handler 邏輯
    },
    onError: ({ error, setState }) => {
      // 錯誤處理（提供此函數後，錯誤不會拋出）
    },
  },
}
```

> 並發控制策略（takeLatest/takeLeading/takeEvery）的詳細說明見 [advanced.md](advanced.md)
