# 模擬資料法（記憶體 fixture）

**用途**：驗收條件需要的邊界資料在 dev 找不到（空值、缺欄位、查無對應、「已被他單使用」…），又不能為了造資料去寫共用的 dev 中台或本機 DB 時，在 Electron **主程序**把 IPC 處理器包一層，**只在記憶體中改寫回應**，讓真實的 UI 元件渲染這些資料。

比 Step 6 的「純函式論證法」強：畫面是真的，可以截圖；缺點是資料是模擬的，報告 MUST 標明（證據等級＝「實機·模擬資料」）。

**不適用**：要驗證「後端／中台行為」本身（模擬回應驗不出後端）；要驗證寫入落地（那要真的操作與真實資料）。

## 原理

`ragdollAPI` 是 preload 以 `contextBridge.exposeInMainWorld('ragdollAPI', …)` 暴露給 renderer 的（`contextIsolation: true`，見 `electron/main/settings/ipc-renderer-preload.ts`），在 renderer 端改它很不可靠、也改不到實際的 IPC 呼叫；所以改從 IPC 的另一端——主程序——下手。`npm run dev` 啟動的 Electron 預設開 Node inspector（`--inspect=9229`），可以用 `Runtime.evaluate` 進主程序，把 `ipcMain._invokeHandlers` 裡的處理器換成「呼叫原處理器、再改寫結果」的包裝。常用通道：

| 通道 | 對應 | 備註 |
|---|---|---|
| `gql-query-find` | `ragdollAPI.graphql.find`（中台查詢，回傳記錄陣列） | 定義在 `electron/main/settings/ipc-main-setup.ts`；handler 簽名 `(event, args, options)`，`args.table`、`args.selects`、`args.filters` 可用來精準鎖定要改的查詢 |
| `db-list` | 本機 SQLite 查詢 | 可模擬「本機主檔變了」 |

換分支前先 `grep -n "handle('" electron/main/settings/ipc-main-setup.ts` 確認通道名稱與簽名沒變。

## 步驟

1. **鎖定查詢特徵**：讀 Step 3 找到的元件，找出它發出的查詢（`table`＋`selects` 的組合通常夠獨特，例：同時含 `lines.monthCards` 與 `lines.monthCardItems`）。特徵要夠精準，避免誤改其他畫面的查詢。
2. **寫三支運算式檔**（放暫存目錄，不進版控）：`wrap.js`（安裝）、`hits.js`（讀命中紀錄）、`restore.js`（還原），範本見下。
3. **安裝**：`node scripts/inspector-eval.mjs wrap.js`，回傳 `{"wrapped": true}`。
4. **觸發 UI 重新查詢**：fixture 只影響「之後」的查詢——要把對話框關掉再重開（或重新載入頁面），資料才會重抓。
5. **截圖＋讀命中紀錄**：`hits.js` 回傳哪些記錄被改成什麼，作為「畫面上的值確實來自改寫後的回應」的佐證；兩者一起放進報告。
6. **還原**：驗完立刻 `restore.js`，回傳 `{"restored": true}`，再跑 `hits.js` 確認 `wrapped: false`。

腳本用法：`node <本 skill 目錄>/scripts/inspector-eval.mjs <運算式檔> [--port 9229]`（Node 22+）。運算式檔寫成立即執行函式，回傳值要能序列化；結束碼 0 成功、1 例外、3 連不上 inspector。

## 範本

`wrap.js`（把 `MATCH`／`PATCH` 換成你的條件；以下以「改寫某張月卡的門市欄位」為例）：

```js
(() => {
  const { ipcMain } = process.mainModule.require('electron');
  const map = ipcMain._invokeHandlers;
  if (globalThis.__fixture) return { already: true };
  const state = { orig: map.get('gql-query-find'), hits: [], err: null };
  globalThis.__fixture = state;
  map.set('gql-query-find', async (event, args, options) => {
    const result = await state.orig(event, args, options);
    try {
      const selects = (args && args.selects) || [];
      const isTarget = args && args.table === 'posservicesale'
        && selects.indexOf('lines.monthCards') > -1 && selects.indexOf('lines.monthCardItems') > -1;   // MATCH
      if (isTarget && Array.isArray(result)) {
        for (const rec of result) {
          for (const mc of (rec && rec.lines && rec.lines.monthCards) || []) {
            if (rec.body.name === '<單號>' && mc.no === '01') {                                          // PATCH
              state.hits.push({ sale: rec.body.name, no: mc.no, before: [mc.allowStore, mc.allowStore_displayName] });
              mc.allowStore = '';
              delete mc.allowStore_displayName;
            }
          }
        }
      }
    } catch (e) { state.err = String(e); }
    return result;
  });
  return { wrapped: true };
})()
```

`hits.js`：

```js
(() => {
  const s = globalThis.__fixture;
  return s ? { wrapped: true, err: s.err, hitCount: s.hits.length, hits: s.hits.slice(-10) } : { wrapped: false };
})()
```

`restore.js`：

```js
(() => {
  const { ipcMain } = process.mainModule.require('electron');
  const s = globalThis.__fixture;
  if (!s) return { restored: false, reason: 'no fixture' };
  ipcMain._invokeHandlers.set('gql-query-find', s.orig);
  const same = ipcMain._invokeHandlers.get('gql-query-find') === s.orig;
  delete globalThis.__fixture;
  return { restored: same };
})()
```

## 注意事項

- **純記憶體**：不寫中台、不寫本機 DB。重啟 Electron 即消失，但仍要主動 `restore.js` 並驗證，不要留給下一個人。
- `ipcMain._invokeHandlers` 是 Electron 的**私有結構**，換 Electron 大版本可能失效；取不到就退回論證法，並在報告說明。
- 主程序是 CJS，用 `process.mainModule.require('electron')`；`require` 本身在 inspector 的全域不存在。
- 運算式檔內含中文字串時可直接寫（腳本以 UTF-8 讀入）；若不放心，用 `\uXXXX` 跳脫。
- 模擬的資料要**合理**：欄位組合是真實可能出現的（例：空字串門市、缺 `displayName`、他單已使用的 `usedDate`＋`serviceSaleName`），不要造出現實不可能的資料去「驗證」程式。
- 做完 Step 7 清理時，把「還原並驗證 `wrapped:false`」列為第一項。
