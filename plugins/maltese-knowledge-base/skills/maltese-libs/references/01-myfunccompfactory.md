# myFuncCompFactory 完整說明

> 檔案：`src/libs/myFuncCompFactory.tsx`

## 設計目的

`myFuncCompFactory` 是 Maltese 專案中用於建立 Context Provider 的工廠函式，
封裝 `state-decorator`（`useLocalStore`）並將 state、actions、view 三層分離。
專案中幾乎所有 Context（`UserProvider`、`UICtrllerProvider`、`PosSaleProvider` 等）都透過此工廠產生。

## 工廠函式簽章

```typescript
function myFuncCompFactory<
  State extends AnyObject,        // 狀態型別
  Actions extends DecoratedActions, // 行為函數型別
  Props extends AnyObject = EmptyObject,  // 上層傳入的屬性
  Context extends AnyObject = EmptyObject // useContext hook 回傳的屬性
>(
  option: Readonly<MyFuncCompFactoryOption<State, Actions, Props, Context>>,
  contextlize: boolean = false
): [MemoedComponent, ReactContext]
```

回傳值：
- `contextlize = false`：回傳 `[MemoedFC, null]`
- `contextlize = true`：回傳 `[MemoedFC, ReactContext]`，應用層可透過 `useContext(ReactContext)` 取得 state 和 actions

## Option 參數結構

```typescript
interface MyFuncCompFactoryOption<State, Actions, Props, Context> {
  /** 產生初始狀態 */
  getInitialState: (props: Props & Context) => State;

  /**
   * 行為實作，所有跟 state 相關的操作都實作於此
   * - 純操作 state 的 function：命名為 `setXXXXX`（比照 useState）
   * - 傳遞給 view 或複合型 action：命名為 `handleXXXXX`
   */
  actionsImpl: Readonly<StoreActions<State, Actions, Props & Context>>;

  /**
   * 渲染函數，接收 state + actions 作為 props
   * 通常將內容抽離成獨立元件
   * @defaultValue `<>{props.children}</>`
   */
  view?: FC<MyFuncCompFactoryViewProps<State, Actions, Props, Context>>;

  /**
   * 導入外部 React Context 的 hook
   * 命名為 useContext 是因為 eslint 要求 hook 命名必須 use 開頭
   * 回傳值會與 props 合併後傳給 actionsImpl 和 events
   */
  useContext?: (props: Props) => Context;

  /** 監聽 props/context 變化，產生新 state 或觸發 action */
  events?: ReadonlyArray<Readonly<MyFuncCompFactoryEvent<State, Actions, Props & Context>>>;

  /** 可被中斷的非同步 action 名稱清單 */
  abortableActions?: Array<AsyncActionNamesOnly<Actions>>;

  /** 啟用 log 顯示（使用 state-decorator 的 logDetailedEffects middleware） */
  logEnabled?: boolean;

  // 繼承自 state-decorator 的 lifecycle hooks
  onMount?: ...;
  onUnmount?: ...;
  notifySuccess?: ...;
  notifyError?: ...;
  notifyWarning?: ...;
}
```

## 非同步 Action 的生命週期

非同步 action 使用物件格式定義，包含完整的生命週期 hooks：

```typescript
actionsImpl: {
  setConsoleUser: {
    /**
     * 1. 發起非同步請求，取得結果
     * 若設定 abortable，第 5 個參數會注入 abortSignal
     */
    getPromise: async ({ args, s, p, abortSignal }) => {
      const [userName] = args;
      const result = await fetchSomething(userName);
      return result;
    },

    /**
     * 2. 根據 getPromise 的結果決定 state 更新
     * 回傳 null 表示不更新 state
     * 回傳 partial state 則合併更新
     */
    effects: ({ state, result, props }) => {
      if (!result) return null; // 不更新
      return { ...state, consoleUser: result };
    },

    /**
     * 3. state 更新後的副作用（例如 GTM 追蹤、localStorage 寫入）
     * 此時 state 已經更新完成
     */
    sideEffects: ({ result, props }) => {
      sendGTMEvent({ ... });
      localStorage.setItem('key', result.name);
    },

    /**
     * 4. getPromise 發生錯誤時的處理
     */
    errorSideEffects: ({ error, props }) => {
      props.muiToast.showToast(`失敗：${error.message}`, { intent: 'error' });
    },
  },

  // 同步 action 直接回傳新 state
  clearUser: ({ state }) => {
    return { ...state, consoleUser: null };
  },
}
```

**重點**：非同步 action 回傳的 Promise，若被 reject 會導致回傳值為 `void`。因此應用層呼叫時必須考慮空值情況。這由 `OptimizeDecoratedActions` 型別處理：

```typescript
type OptimizeDecoratedActions<A> = {
  [K in keyof A]: ReturnType<A[K]> extends Promise<any>
    ? (...args) => Promise<Awaited<ReturnType<A[K]>> | void>  // 加上 | void
    : A[K];
};
```

## View Props 結構

View 元件接收的 props 包含所有 state 欄位、所有 action 函式，以及 loading 狀態：

```typescript
type MyFuncCompFactoryViewProps<State, Actions, Props, Context> = PropsWithChildren<
  State & Actions & LoadingProps<Actions> & {
    /** 合併後的 props 與 context */
    mergedProps: Props & Context;
  }
>;
```

在 View 中可以直接解構使用：

```typescript
const MyView: FC<ViewProps> = (props) => {
  const { consoleUser, isUserDialogOpen, setConsoleUser, children } = props;
  // consoleUser → state 欄位
  // setConsoleUser → action 函式
  // children → 子元件
};
```

## Context 化機制

當 `contextlize = true` 時，工廠建立 `React.Context`，用 `Provider` 包裹 View 輸出。
應用層透過對應的 `useXxxContext()` hook 取得 state 和 actions：

```typescript
// 定義端
const [UserProvider, UserContext] = myFuncCompFactory<
  UserContextState,
  UserContextActions,
  EmptyObject,
  UserInnerContextValue
>({ ... }, true);

export const useUserContext = () => useContext(UserContext);

// 使用端
const { consoleUser, setConsoleUser, loadingMap } = useUserContext();
```

Context value 經過 `useMemo` 快取，只有 state 或 actions 變更時才會觸發 Provider 底下的元件重新渲染。

## Events 機制

Events 用於監聽 props/context 的變化，自動更新 state 或觸發 action：

```typescript
interface MyFuncCompFactoryEvent<State, Actions, Props> {
  /** 要監聯的 props key 列表（至少一個） */
  watch: Array<keyof Props>;

  /**
   * props 變化時產生新的 partial state
   * 回傳 null 則不更新
   */
  mapToState?: (state: State, newProps: Props) => Partial<State>;

  /** props 變化時觸發 action */
  triggerAction?: (state: State, newProps: Props, actions: Actions) => void;
}
```

每個 event 至少要設定 `mapToState` 或 `triggerAction` 其中之一（由 `assureMyFuncCompFactoryEvent` 驗證）。
多個 events 可以監聽同一個 prop key，會依序執行。

底層實作：工廠將所有 events 的 `watch` 合併後，透過 state-decorator 的 `onPropsChange.getDeps` 統一監聽，
當 deps 變化時依序執行符合條件的 `mapToState`（reduce 合併 state）和 `sideEffects`（觸發 action）。

## AbortableActions 中斷機制

設定 `abortableActions` 後，對應的非同步 action 會：

1. 設定 `conflictPolicy = ConflictPolicy.PARALLEL`（每個 promise 各自獨立）
2. 設定 `getPromiseId = () => uuidv4()`（唯一識別每次呼叫）
3. 注入 `abortSignal` 到 `getPromise` 參數中
4. 中斷時擲出 `DOMException`，名稱為 `MYFC_ABORT_ERROR`

```typescript
// 呼叫中斷
const { abortAction } = useXxxContext();
abortAction('actionName', promiseId);

// 在 getPromise 中使用 abortSignal
getPromise: async ({ args, abortSignal }) => {
  const response = await fetch(url, { signal: abortSignal });
  return response.json();
}
```

## SetStateActions 型別工具

用於將 state 定義轉換為 setter 函式定義：

```typescript
type SetStateActions<State> = {
  [Name in keyof State as `set${Capitalize<Name>}`]-?: (value: State[Name]) => void;
};

// 範例：
// { myState: boolean } → { setMyState: (value: boolean) => void }
```

## state-decorator 整合注意事項

### Clone 問題
state-decorator 預設用 `JSON.parse(JSON.stringify())` 複製 state，
當 state 或 props 含有 function 時會報錯。
專案在模組頂層設定 `setGlobalConfig({ clone: cloneDeep })` 改用 lodash 深拷貝。

### SSR useLayoutEffect 警告
state-decorator 內部使用 `useLayoutEffect`，SSR 環境下會產生警告。
專案透過以下方式消除（因為所有頁面都關閉 SSR，不影響實際行為）：

```typescript
if (isServerSide()) {
  React.useLayoutEffect = React.useEffect;
}
```

### Option 凍結
工廠在初始化時會 `Object.freeze(option)` 與 `Object.freeze(option.actionsImpl)`，
確保 option 在運行期間不可變。

## 實作新 Context 的標準步驟

1. 定義 `State`、`Actions`、`InnerContext`（如有）型別
2. 呼叫 `myFuncCompFactory<State, Actions, EmptyObject, InnerContext>({ ... }, true)`
3. 在 `actionsImpl` 中實作所有 action（同步用 reducer 格式、非同步用 getPromise 格式）
4. 如需 View 元件，定義 `view` 並接收 `MyFuncCompFactoryViewProps` 作為 props
5. Export `Provider` 元件和 `useXxxContext` hook
6. 在 `_app.pub.tsx` 或頁面層的 `MultipleProviders` 中掛載 Provider
