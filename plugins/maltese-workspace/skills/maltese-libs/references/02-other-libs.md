# 其他函式庫工具

## fcFactory.tsx

> 檔案：`src/libs/fcFactory.tsx`

`myFuncCompFactory` 的型別延伸，提供額外的 Option 擴充欄位。
目前主要用於型別別名的再匯出。

```typescript
/** 型別別名 */
type FCFactoryEvent<S, A, P> = MyFuncCompFactoryEvent<S, A, P>;

/** 擴充的 Option 介面 */
interface FCFactoryOption<S, A, P, C> extends MyFuncCompFactoryOption<S, A, P, C> {
  /** 是否將 state 與 actions 轉成 context */
  contextlize?: boolean;
  /** 是否傳遞 loading 和 loadingMap 到 view（透過 __loading、__loadingMap 收取） */
  passLoading?: boolean;
  /** 是否傳遞 props 到 view（透過 __props 收取） */
  passProps?: boolean;
}
```

---

## stashArrayFactory.ts

> 檔案：`src/libs/stashArrayFactory.ts`

操作 localStorage 的暫存陣列工具。讀取時自動過濾 24 小時前的過期資料，
確保暫存資料不會無限累積。

### 使用方式

```typescript
const stash = stashArrayFactory<SomeRecord>('localStorageKey');
```

### 回傳介面

```typescript
interface StashArrayFactoryReturn<Record> {
  /** 新增一筆資料，自動附加 _createdAt 時間戳，同步更新 localStorage */
  push: (record: Record) => number;

  /** 列出所有資料，依建立時間排序（最新在最前面） */
  list: () => Record[];

  /** 清除所有資料，同步更新 localStorage */
  clear: () => void;

  /** 根據條件刪除一筆資料，回傳被刪除的資料或 null */
  removeBy: (by: (record: Record) => boolean) => Record | null;
}
```

### 過期清理機制

- 建立 factory 實例時，立即讀取 localStorage 中的資料
- 過濾掉 `_createdAt` 距今超過 24 小時的資料
- 若有資料被過濾，立即寫回 localStorage
- 後續的 push / list / clear / removeBy 都操作過濾後的陣列

### key 來源

localStorage key 必須來自 `src/config` 中定義的 `cLocalStorageKey` 常數，確保全專案 key 統一管理。

---

## classes.ts

> 檔案：`src/libs/classes.ts`

### Warning 錯誤類別

繼承 `Error`，用於區分「警告」與「一般錯誤」。
在 action 中可以 `throw new Warning('message')` 來表示非致命性的問題。

```typescript
class Warning extends Error {
  static NAME = 'Warning' as const;
  constructor(message: string) {
    super(message);
    this.name = Warning.NAME;
  }
}
```

判斷方式：

```typescript
// 方式 1：instanceof
if (error instanceof Warning) { ... }

// 方式 2：name 比對
if (error.name === 'Warning') { ... }
if (error.name === Warning.NAME) { ... }
```
