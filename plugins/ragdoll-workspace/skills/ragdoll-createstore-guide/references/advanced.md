# 進階功能

## useProps（傳遞外部 Props）

在 store 配置中定義 `useProps`，可以在 store 內部調用 React hooks 獲取外部依賴（如 toast、router 等）。這種方式符合 React Hook 規則，無需在組件中手動傳入 props。

```typescript
import { useToast } from '@/lib/hooks/use-toast';
import { createStore } from '@/lib/utils/stores';

interface StoreProps {
  toast: (message: string) => void;
}

const useUserStore = createStore<
  { user: User | null },
  { login: (username: string, password: string) => Promise<void> },
  never,
  StoreProps  // 第 4 個泛型參數
>({
  name: 'user',
  states: {
    user: { type: 'value', initialValue: null },
  },
  // ✅ 在 store 內部調用 hooks 獲取 props
  useProps: () => {
    const { toast } = useToast();
    return { toast };
  },
  actions: {
    login: async (ctx) => {
      const [username, password] = ctx.args as [string, string];
      try {
        const user = await api.login(username, password);
        ctx.setState({ user });
        // ✅ 直接使用 props（型別為 Partial<StoreProps>）
        ctx.props.toast?.('登入成功');
      } catch (error) {
        ctx.props.toast?.('登入失敗');
        throw error;
      }
    },
  },
});

// 組件中使用，無需傳入 props
function LoginPage() {
  const userStore = useUserStore();  // ✅ 不需要傳參數

  return (
    <button onClick={() => userStore.actions.login('user', 'pass')}>
      登入
    </button>
  );
}
```

### useProps 注意事項

- `props` 透過 ref 維護，永遠指向最新值（即使在異步操作中）
- 可在 actions、subscriptions、onMount 中透過 `ctx.props` 訪問
- `ActionContext.props` 型別為 `Partial<TProps>`，需使用可選鏈（`ctx.props.toast?.()`）
- TProps 預設為 `never`，不需要 props 時可省略此泛型參數
- 建議只傳入函數或穩定引用，避免傳入會頻繁變化的物件

---

## onMount（初始化）

`onMount` 在 store 第一次被 component 使用時執行一次，內部透過 module-level flag 保證全域只觸發一次，並以 `queueMicrotask` 延遲到 render 完成後才執行。

```typescript
const useCartStore = createStore({
  name: 'cart',
  states: {
    items: { type: 'value', initialValue: [] as Item[] },
  },
  actions: {
    loadFromStorage: ({ state, setState }) => {
      const saved = localStorage.getItem('cart');
      if (saved) {
        setState({ items: JSON.parse(saved) });
      }
    },
  },
  // ✅ 首次挂載時執行（全域只執行一次，透過 queueMicrotask 延遲）
  onMount: ({ actions }) => {
    actions.loadFromStorage();
  },
});
```

---

## 並發控制策略

### takeLatest：取消前一個，只保留最新的

適用於搜尋、篩選等場景，使用者持續輸入時只需最後一次結果。

```typescript
actions: {
  search: {
    strategy: 'takeLatest',
    handler: async ({ state, setState, signal }, query: string) => {
      setState({ query });

      // 使用 signal 檢查是否被取消
      const results = await api.search(query, { signal });

      if (!signal.aborted) {
        setState({ results });
      }
    },
  },
}
```

### takeLeading：忽略新請求，等待前一個完成

適用於提交表單、付款等場景，防止重複操作。

```typescript
actions: {
  submitOrder: {
    strategy: 'takeLeading',
    handler: async ({ state }) => {
      await api.submitOrder(state.cart);
    },
  },
}
```

### takeEvery：允許所有請求並行執行（預設）

適用於日誌記錄、獨立並行操作等場景。

```typescript
actions: {
  logEvent: {
    strategy: 'takeEvery',
    handler: async (_, event: Event) => {
      await api.logEvent(event);
    },
  },
}
```

### runningActions

每個 action 對應一個 boolean 的 loading 狀態：

```typescript
function Component() {
  const { actions, runningActions } = useSearchStore();

  return (
    <div>
      {runningActions.search && <Spinner />}
      <button onClick={() => actions.search('query')}>搜尋</button>
    </div>
  );
}
```

> 未啟動的 action 鍵不存在於 `runningActions`（undefined），只有執行中才為 `true`

---

## 完整範例（整合所有進階功能）

```typescript
export const useCheckoutStore = createStore({
  name: 'checkout',

  states: {
    cart: { type: 'value', initialValue: { items: [], total: 0 } },
    status: { type: 'value', initialValue: 'idle' as CheckoutStatus },
  },

  useInjectedStores: () => ({
    memberStore: useMemberStore(),
    promotionStore: usePromotionStore(),
  }),

  useProps: () => {
    const { toast } = useToast();
    return { toast };
  },

  actions: {
    addItem: ({ state, setState }, item: Item) => {
      setState({
        cart: {
          items: [...state.cart.items, item],
          total: state.cart.total + item.price,
        }
      });
    },

    checkout: {
      strategy: 'takeLeading',
      handler: async ({ state, setState, actions, injected, signal }) => {
        setState({ status: 'processing' });

        actions.calculateDiscount();

        const promotion = injected.promotionStore.state.active;
        const order = await api.createOrder(state.cart, { signal });

        setState({ status: 'success' });
        return order;
      },
      onError: ({ error, setState, props }) => {
        setState({ status: 'error' });
        props.toast?.('結帳失敗，請重試');
      },
    },

    calculateDiscount: ({ state, setState, injected }) => {
      const member = injected.memberStore.state.member;
      // 計算折扣邏輯...
    },
  },

  subscriptions: [
    {
      watcher: (ctx) => ctx.state.status,
      invoke: (ctx, prevStatus, currentStatus) => {
        if (currentStatus === 'success') {
          ctx.props.toast?.('結帳成功！');
        }
      },
    },
  ],

  onMount: ({ actions }) => {
    actions.loadCartFromStorage();
  },
});
```
