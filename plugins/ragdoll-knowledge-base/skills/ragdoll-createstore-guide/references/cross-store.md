# 跨 Store 功能

## useInjectedStores

透過 `useInjectedStores` 在 store 內部明確宣告對其他 stores 的依賴：

```typescript
const useMemberStore = createStore({
  name: 'member',
  states: {
    member: { type: 'value', initialValue: null as Member | null },
  },
  actions: {
    login: ({ state, setState }, member: Member) => {
      setState({ member });
    },
  },
});

const useCheckoutStore = createStore({
  name: 'checkout',
  states: {
    discount: { type: 'value', initialValue: 0 },
  },
  // ✅ 函數形式，在 render 時呼叫注入的 store hooks
  useInjectedStores: () => ({
    memberStore: useMemberStore(),
  }),
  actions: {
    applyMemberDiscount: ({ setState, injected }) => {
      // ✅ 透過鍵名存取注入的 store
      const member = injected.memberStore.state.member;
      if (member?.tier === 'vip') {
        setState({ discount: 0.2 });
      }
    },
  },
});
```

### 重要規則

- `useInjectedStores` 是函數，在每次 render 時被呼叫
- 函數內部呼叫的 hooks **必須無條件呼叫**（遵守 React Rules of Hooks）
- 不可在條件式或迴圈中呼叫 hooks

### 型別系統

```typescript
// TInjected 的 value 是 StoreHook（i.e. () => StoreReturn<...>）
type InjectedDefinition = Record<string, StoreHook<Record<string, unknown>, ActionsDefinition>>;

// 將 hook 型別解析為實際的 StoreReturn 型別
type ResolvedInjected<TInjected extends InjectedDefinition> = {
  [K in keyof TInjected]: ReturnType<TInjected[K]>
};

// 使用範例
const config = {
  useInjectedStores: () => ({
    memberStore: useMemberStore(),   // 得到 StoreReturn<MemberState, MemberActions>
    authStore: useAuthStore(),       // 得到 StoreReturn<AuthState, AuthActions>
  }),
  actions: {
    someAction: ({ injected }) => {
      // injected.memberStore 完整型別推導
      const member = injected.memberStore.state.member;
      const login = injected.memberStore.actions.login;
      const isLoading = injected.memberStore.runningActions.login;
    }
  }
};
```

---

## Subscriptions（自動觸發）

Subscriptions 可以監聽自己 store 或注入的其他 stores 的狀態變化，當指定的值發生變化時自動執行 invoke 處理器。

### 基本範例

```typescript
const useAuthStore = createStore({
  name: 'auth',
  states: {
    user: { type: 'value', initialValue: null as User | null },
  },
});

const useProfileStore = createStore({
  name: 'profile',
  states: {
    profile: { type: 'value', initialValue: null as Profile | null },
  },
  actions: {
    fetchProfile: async ({ setState }, userId: string) => {
      const data = await api.fetchProfile(userId);
      setState({ profile: data });
    },
  },
  useInjectedStores: () => ({
    authStore: useAuthStore(),
  }),
  // ✅ 訂閱其他 store 的狀態變化（跨 store 響應）
  subscriptions: [
    {
      // 監聽 authStore 的 user（注入的其他 store）
      watcher: (ctx) => ctx.injected.authStore.state.user,
      // 當 authStore 的 user 變化時，自動載入該用戶的個人資料
      invoke: async (ctx, prevUser, currentUser) => {
        if (currentUser && prevUser?.id !== currentUser.id) {
          await ctx.actions.fetchProfile(currentUser.id);
        }
      },
    },
  ],
});
```

### Subscriptions 型別系統

型別推導是自動的，`invoke` 的 `prev` 和 `current` 參數類型由 `watcher` 的返回類型決定：

```typescript
subscriptions: [
  {
    // watcher 返回 string
    watcher: (ctx) => ctx.state.status,
    // ✅ prev 和 current 自動推導為 string
    invoke: (ctx, prev, current) => {
      if (current === 'success') {
        console.log('操作成功');
      }
    },
  },
  {
    // watcher 返回 User | null
    watcher: (ctx) => ctx.injected.authStore.state.user,
    // ✅ prev 和 current 自動推導為 User | null
    invoke: async (ctx, prev, current) => {
      if (current && prev?.id !== current.id) {
        await ctx.actions.loadUserProfile(current.id);
      }
    },
  },
],
```

### Subscriptions 配置格式

```typescript
type SubscriptionConfig<TState, TActions, TInjected, TProps, V> = {
  // 監聽器：從 context 中取得要監聽的值
  watcher: (ctx: StoreContext<TState, TActions, TInjected, TProps>) => V;
  // 處理器：當值變化時被調用
  // - ctx 不含 signal（Omit<ActionContext, 'signal'>）
  // - prev 和 current 的類型自動推導為 V
  invoke: (
    ctx: Omit<ActionContext<TState, TActions, TInjected, TProps>, 'signal'>,
    prevValue: V,
    currentValue: V
  ) => void | Promise<void>;
};
```

### 重要注意事項

- watcher 返回的值使用**淺比較（shallow equality）**
- 建議 watcher 返回基本類型或穩定的引用
- 只有當 watcher 返回的值發生變化時，invoke 才會被呼叫

---

## 最佳實踐

1. **合理拆分 Stores** - 按功能領域拆分（如 auth、cart、checkout）
2. **使用 useInjectedStores 建立依賴關係** - 明確宣告依賴，便於維護
3. **避免循環依賴** - Store A 依賴 Store B，Store B 不應再依賴 Store A
4. **善用 Subscriptions 響應變化** - 比手動監聽更清晰

```typescript
subscriptions: [
  {
    watcher: (ctx) => ctx.state.user,
    invoke: (ctx, prevUser, currentUser) => {
      if (prevUser?.id !== currentUser?.id) {
        ctx.actions.loadUserData();
      }
    },
  },
]
```
