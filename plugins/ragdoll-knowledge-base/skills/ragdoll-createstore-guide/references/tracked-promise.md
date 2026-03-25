# TrackedPromise 完整指南

`TrackedPromise` 定義於 `@shared/utils/promise`，可用於追蹤 Promise 的執行狀態（`pending`、`fulfilled`、`rejected`）。

**TrackedPromise 實作了 `PromiseLike` 介面**，因此可以像原生 Promise 一樣使用。

---

## 基本用法

```typescript
import { TrackedPromise } from '@shared/utils/promise';

// 建立
const tracked = new TrackedPromise(fetchUserData());

// 讀取狀態
console.log(tracked.status);  // 'pending' | 'fulfilled' | 'rejected'
console.log(tracked.value);   // 值（fulfilled 時）
console.log(tracked.error);   // 錯誤（rejected 時）
```

---

## PromiseLike 功能

```typescript
// ✨ 可以直接 await
const result = await tracked;

// ✨ 使用 then/catch/finally
tracked
  .then(data => console.log(data))
  .catch(err => console.error(err))
  .finally(() => console.log('done'));

// ✨ 與 Promise.all 一起使用
const [user, posts] = await Promise.all([
  new TrackedPromise(fetchUser()),
  new TrackedPromise(fetchPosts()),
]);

// ✨ 與 Promise.race 一起使用
const fastest = await Promise.race([
  new TrackedPromise(fetchFromAPI1()),
  new TrackedPromise(fetchFromAPI2()),
]);
```

---

## 在 React Component 中使用

```typescript
function DataLoader() {
  const [tracked] = useState(() => new TrackedPromise(fetchData()));

  if (tracked.status === 'pending') return <Spinner />;
  if (tracked.status === 'rejected') return <Error error={tracked.error} />;

  return <Data value={tracked.value} />;
}
```

---

## 在 async function 中使用

```typescript
async function loadUserData() {
  const tracked = new TrackedPromise(fetchUser());

  try {
    // 直接 await
    const user = await tracked;
    console.log('User:', user);

    // await 後仍可檢查狀態
    console.log('Status:', tracked.status);  // 'fulfilled'
  } catch (error) {
    console.error('Error:', error);
    console.log('Status:', tracked.status);  // 'rejected'
  }
}
```

---

## 靜態工廠方法

```typescript
// 建立可取消的 Promise
const tracked = TrackedPromise.create((signal) => {
  return fetch('/api/data', { signal });
});
tracked.abort('User cancelled');

// 建立帶超時的 Promise
const tracked = TrackedPromise.withTimeout(
  fetchData(),
  5000,
  'Request timeout after 5s'
);

// 建立帶重試的 Promise
const tracked = TrackedPromise.withRetry(
  () => fetch('/api/data').then(r => r.json()),
  { maxRetries: 3, retryDelay: 1000 }
);
```

---

## AbortController 支援

```typescript
const tracked = new TrackedPromise(fetchData());

// 內建的 AbortController
console.log(tracked.abortController);
console.log(tracked.signal);

// 取消 Promise
tracked.abort('User cancelled');
console.log(tracked.isAborted);  // true
```

---

## 更新和手動控制

```typescript
const tracked = new TrackedPromise(fetchData());

// 更新為新的 Promise
const newTracked = tracked.update(fetchNewData());

// 手動 resolve
const resolved = tracked.resolve({ id: 1, name: 'John' });

// 手動 reject
const rejected = tracked.reject(new Error('Failed'));
```

---

## 型別守衛

```typescript
if (TrackedPromise.isTrackedPromise(someValue)) {
  console.log(someValue.status);
  console.log(someValue.value);
}
```

---

## 重要注意事項

- **不要直接修改** `state.promiseData.status`
- 使用 `setState` 傳入新的 `TrackedPromise` 來更新 Promise 狀態
- `status` 三種值：`'pending'`、`'fulfilled'`、`'rejected'`
- `value` 只在 `fulfilled` 時有值；`error` 只在 `rejected` 時有值
