# API Reference

## createStore&lt;TState, TActions, TInjected, TProps&gt;(config)

建立一個 store，回傳一個 React Hook。

### Config 完整介面

```typescript
interface StoreConfig<TState, TActions, TInjected, TProps = never> {
  // Store 名稱（用於 devtools）
  name: string;

  // States 配置
  states: StatesConfigFor<TState>;

  // Actions 定義
  actions?: ActionsConfig<TState, TActions, TInjected, TProps>;

  // 注入其他 stores（函數形式，在 render 時調用 hooks）
  useInjectedStores?: () => ResolvedInjected<TInjected>;

  // 獲取外部 props（在 store 內部調用 React hooks）
  useProps?: () => TProps;

  // Subscriptions（陣列形式，每個元素的類型獨立推導）
  subscriptions?: Array<SubscriptionConfig<TState, TActions, TInjected, TProps, any>>;

  // 首次挂載時執行（全域只執行一次）
  onMount?: OnMountHandler<TState, TActions, TInjected, TProps>;
}
```

---

## State Config

### Value State

```typescript
{ type: 'value', initialValue: T }
```

一般的值類型 state，`setState` 後立即觸發 re-render。

### Promise State

```typescript
{ type: 'promise', initialValue: Promise<T> }
```

Promise 類型 state，自動轉換為 `TrackedPromise<T> & ReactPromise<T>`，追蹤 `status`、`value`、`error`。

---

## Action Context

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

## Store Return

```typescript
type StoreReturn<TState, TActions> = {
  // State（Proxy，永遠最新，Promise<T> 轉換為 TrackedPromise<T> & ReactPromise<T>）
  state: TransformState<TState>;

  // Actions（reference 穩定，可安全放入 useEffect 依賴陣列）
  actions: Actions<TActions>;

  // Action 執行狀態（boolean loading states，未啟動的 action 鍵不存在）
  runningActions: Partial<Record<keyof TActions, boolean>>;

  // 訂閱 state 變化（Zustand subscribe API）
  subscribe: StoreApi<TransformState<TState>>['subscribe'];

  // 批次更新 state（可在 actions 外部直接使用）
  setState: (updater: Partial<TState> | ((prev: TState) => Partial<TState>)) => void;
}
```

---

## TransformState

`TransformState` 會將 state 中的 `Promise<T>` 轉換為 `TrackedPromise<T> & ReactPromise<T>`，其餘類型保持不變：

```typescript
// 定義
states: {
  count: { type: 'value', initialValue: 0 },
  userData: { type: 'promise', initialValue: fetchUser() },
}

// 在 component 中
const { state } = useStore();
state.count;       // number
state.userData;    // TrackedPromise<User> & ReactPromise<User>
state.userData.status;  // 'pending' | 'fulfilled' | 'rejected'
state.userData.value;   // User | undefined
state.userData.error;   // unknown | undefined
```

---

## 泛型參數說明

```typescript
createStore<TState, TActions, TInjected, TProps>(config)
```

| 泛型 | 說明 | 預設值 |
|------|------|--------|
| `TState` | State 的型別定義 | 自動推導 |
| `TActions` | Actions 的型別定義 | 自動推導 |
| `TInjected` | 注入 stores 的型別定義 | `never` |
| `TProps` | useProps 返回的型別 | `never` |

大多數情況下，TypeScript 可以自動推導所有泛型參數。只有在需要顯式聲明 `TProps` 時才需要手動指定：

```typescript
const useStore = createStore<
  { user: User | null },      // TState
  { login: () => void },      // TActions
  never,                       // TInjected（沒有注入 stores）
  { toast: (msg: string) => void }  // TProps
>({
  // ...
});
```

---

## 注意事項

### State 是 Proxy，永遠指向最新值

- `state` 透過 Proxy 攔截屬性存取，每次讀取都會返回最新的 store 值
- 在 async action 中 `await` 後讀取 `state` **不會**取得過時的快照
- **禁止**直接修改：`state.count = 1` ❌
- **必須**使用 setState：`setState({ count: 1 })` ✅

### setState 是批次的

- 多次呼叫 `setState` 會被 zustand 自動批次處理，不必手動合併

### Actions Reference 穩定

- Actions 在 store 建立時固定，可以安全地放入 `useEffect` 依賴陣列
- 不需要使用 `useCallback` 包裝
