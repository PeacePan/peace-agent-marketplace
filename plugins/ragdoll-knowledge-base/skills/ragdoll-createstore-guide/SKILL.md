---
name: ragdoll-createstore-guide
description: Ragdoll 專案的 createStore 狀態管理完整指南。當用戶詢問關於 Ragdoll 中的 createStore、Zustand、store 實作、狀態管理、Promise state、TrackedPromise、subscriptions、actions、跨 store 通信、useInjectedStores、並發控制策略、onMount、useProps 傳遞 props、runningActions loading 狀態等任何相關主題時觸發。也適用於「如何建立 store」、「store 之間如何通信」、「如何處理異步操作」、「Promise 狀態追蹤」、「跨 store 訂閱」、「action 互相呼叫」等問題。即使用戶只是提到 store、狀態、Zustand，也應該考慮使用此技能來提供準確且完整的資訊。
user-invocable: false
---

# Ragdoll createStore 狀態管理指南

Ragdoll 使用基於 Zustand 的自訂 `createStore` 進行狀態管理（位於 `next/lib/utils/stores/`）。

**回答原則：** 繁體中文回覆，提供準確、完整的資訊，並輔以程式碼範例說明。

---

## 快速開始

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
  },
});

function Counter() {
  const { state, actions } = useCounterStore();
  return <button onClick={() => actions.increment()}>{state.count}</button>;
}
```

> 更多範例見 [references/quick-start.md](references/quick-start.md)

---

## State 類型

```typescript
// Value State
{ type: 'value', initialValue: T }

// Promise State（自動追蹤 status / value / error）
{ type: 'promise', initialValue: Promise<T> }
```

> Promise State 與 TrackedPromise 詳見 [references/tracked-promise.md](references/tracked-promise.md)

---

## Actions

```typescript
actions: {
  // 同步 action
  addItem: ({ state, setState }, item: Item) => {
    setState({ items: [...state.items, item] });
  },

  // Async action（含並發策略與錯誤處理）
  fetchData: {
    strategy: 'takeLatest',            // takeLatest | takeLeading | takeEvery
    handler: async ({ setState, signal }) => {
      setState({ status: 'loading' });
      const data = await api.fetch({ signal });
      setState({ data, status: 'success' });
    },
    onError: ({ error, setState }) => {  // 提供 onError 則錯誤不拋出
      setState({ status: 'error' });
    },
  },
}
```

**`state` 是 Proxy，永遠指向最新值 — `await` 後讀取不會 stale。**

> Actions 完整說明見 [references/actions.md](references/actions.md)
> 並發策略與 `onMount`、`useProps` 見 [references/advanced.md](references/advanced.md)

---

## 跨 Store 功能

```typescript
const useCheckoutStore = createStore({
  name: 'checkout',
  states: { discount: { type: 'value', initialValue: 0 } },

  // ✅ 注入其他 store（函數形式，遵守 React Hook 規則）
  useInjectedStores: () => ({
    memberStore: useMemberStore(),
  }),
  actions: {
    applyDiscount: ({ setState, injected }) => {
      const member = injected.memberStore.state.member;
      if (member?.tier === 'vip') setState({ discount: 0.2 });
    },
  },

  // ✅ 訂閱狀態變化（watcher 返回類型自動推導 prev/current 型別）
  subscriptions: [
    {
      watcher: (ctx) => ctx.injected.memberStore.state.member,
      invoke: (ctx, prev, current) => {
        if (prev?.id !== current?.id) ctx.actions.applyDiscount();
      },
    },
  ],
});
```

> useInjectedStores 與 Subscriptions 詳見 [references/cross-store.md](references/cross-store.md)

---

## runningActions（Loading 狀態）

```typescript
const { actions, runningActions } = useDataStore();

// ✅ boolean，未啟動的 action 鍵不存在（undefined）
if (runningActions.fetchData) return <Spinner />;
```

---

## API Reference 速查

| 欄位 | 說明 |
|------|------|
| `state` | Proxy，永遠最新，Promise → `TrackedPromise<T> & ReactPromise<T>` |
| `actions` | Reference 穩定，可安全放入 `useEffect` 依賴陣列 |
| `runningActions` | `Partial<Record<keyof TActions, boolean>>` |
| `subscribe` | Zustand subscribe API |
| `setState` | 可在 actions 外部直接更新狀態 |

> 完整 API 定義見 [references/api-reference.md](references/api-reference.md)

---

## References

| 文件 | 主題 |
|------|------|
| [quick-start.md](references/quick-start.md) | 基本使用、Async Actions、Promise State |
| [tracked-promise.md](references/tracked-promise.md) | TrackedPromise 完整 API、靜態工廠方法 |
| [actions.md](references/actions.md) | Actions 互相呼叫、onError、Action Context |
| [cross-store.md](references/cross-store.md) | useInjectedStores、Subscriptions、型別推導 |
| [advanced.md](references/advanced.md) | useProps、onMount、並發策略、完整範例 |
| [api-reference.md](references/api-reference.md) | createStore Config、State Config、StoreReturn |

---

## 相關程式碼位置

- `next/lib/utils/stores/` — createStore 實作
- `next/lib/stores/` — Store 使用範例
- `AGENTS.md` — Ragdoll 專案總指南


