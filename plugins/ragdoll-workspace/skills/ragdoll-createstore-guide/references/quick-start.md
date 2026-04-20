# createStore 快速開始

## 核心特性

- **Readonly State** - State 為唯讀，所有更新必須透過 `setState`
- **setState 立即渲染** - 狀態更新立即觸發 re-render
- **Actions Reference 穩定** - Actions 在建立時固定，reference 永久不變
- **Actions 互相呼叫** - 透過 `actions` 參數自由呼叫其他 actions
- **Promise State 追蹤** - 自動追蹤 Promise 的 `status`、`value`、`error`
- **跨 Store 響應式訂閱** - 透過 `subscriptions` 監聽自己或注入的其他 stores 的狀態變化
- **跨 Store 存取** - 透過 `useInjectedStores` 明確宣告依賴關係
- **簡單的 Loading 狀態** - `runningActions` 提供布林值的執行狀態
- **並發控制策略** - 支援 takeLatest、takeLeading、takeEvery
- **完整 TypeScript 支援** - 全面的型別推導和安全性

---

## 基本使用

```typescript
import { createStore } from '@/lib/utils/stores';

const useCounterStore = createStore({
  name: 'counter',
  states: {
    count: { type: 'value', initialValue: 0 },
  },
  actions: {
    increment: ({ state, setState }) => {
      setState({ count: state.count + 1 });
    },
    incrementBy: ({ state, setState }, amount: number) => {
      setState({ count: state.count + amount });
    },
  },
});

// 在 Component 中使用
function Counter() {
  const { state, actions } = useCounterStore();

  return (
    <div>
      <p>Count: {state.count}</p>
      <button onClick={() => actions.increment()}>+1</button>
      <button onClick={() => actions.incrementBy(5)}>+5</button>
    </div>
  );
}
```

---

## Async Actions

`state` 是一個 Proxy，永遠指向最新的 store 值，在 `await` 後讀取 `state` 不會取得過時的快照。

```typescript
const useDataStore = createStore({
  name: 'data',
  states: {
    items: { type: 'value', initialValue: [] as Item[] },
    status: { type: 'value', initialValue: 'idle' as Status },
  },
  actions: {
    fetchData: async ({ state, setState }) => {
      setState({ status: 'loading' });  // ✅ 立即觸發 re-render

      const data = await api.fetchItems();

      // ✅ state 是 Proxy，await 後讀取仍是最新值，不會 stale
      console.log(state.status);

      setState({ items: data, status: 'success' });
    },
  },
});

function DataList() {
  const { state, actions, runningActions } = useDataStore();

  // ✅ 簡單的 boolean loading 狀態
  if (runningActions.fetchData) {
    return <Spinner />;
  }

  if (state.status === 'success') {
    return <List items={state.items} />;
  }

  return <button onClick={() => actions.fetchData()}>Load</button>;
}
```

---

## Promise State 基本用法

Promise State 轉換為 `TrackedPromise<T> & ReactPromise<T>` 交集型別，可同時使用手動狀態追蹤和 React 19 Suspense 宣告式非同步處理。

```typescript
const useDataStore = createStore({
  name: 'data',
  states: {
    // Promise State 會自動追蹤 status
    userData: {
      type: 'promise',
      initialValue: fetchUserData()
    },
  },
});

// 方式一：手動狀態追蹤（TrackedPromise）
function UserProfile() {
  const { state } = useDataStore();

  if (state.userData.status === 'pending') {
    return <Spinner />;
  }

  if (state.userData.status === 'rejected') {
    return <Error error={state.userData.error} />;
  }

  // status === 'fulfilled'
  return <Profile user={state.userData.value} />;
}

// 方式二：React 19 Suspense 宣告式處理（ReactPromise）
function UserProfileSuspense() {
  const { state } = useDataStore();

  return (
    <Suspense fallback={<Spinner />}>
      <UserProfileInner promise={state.userData} />
    </Suspense>
  );
}
```

> 詳細的 TrackedPromise 文件見 [tracked-promise.md](tracked-promise.md)
