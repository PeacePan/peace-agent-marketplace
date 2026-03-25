---
name: maltese-libs
description: >
  Maltese POS 專案 `src/libs/` 函式庫完整知識庫。涵蓋 myFuncCompFactory（state/actions/view 三層分離的
  Context Provider 工廠函式）、fcFactory（myFuncCompFactory 的型別延伸）、stashArrayFactory（操作
  localStorage 的暫存陣列工具）、Warning 錯誤類別，以及底層 state-decorator 的整合細節。

  以下情況必須參考此文件再動手：
  - 使用 myFuncCompFactory 建立新的 Context Provider
  - 修改現有 Context 的 state、actions、events、view 定義
  - 需要了解 myFuncCompFactory 的 View Props 結構（state + actions 如何傳遞給 View）
  - 處理 abortableActions（可中斷的非同步行為）相關邏輯
  - 修改 actionsImpl 中的非同步 action（getPromise / effects / sideEffects / errorSideEffects）
  - 需要了解 events 機制如何監聽 props/context 變化並更新 state 或觸發 action
  - 使用 stashArrayFactory 操作 localStorage 暫存資料
  - 處理 state-decorator 的 clone 問題或 SSR useLayoutEffect 警告
---

# Maltese `src/libs/` 函式庫知識庫

## 檔案總覽

| 檔案 | 用途 |
|------|------|
| `myFuncCompFactory.tsx` | Context Provider 工廠函式，封裝 state-decorator，分離 state/actions/view |
| `fcFactory.tsx` | myFuncCompFactory 的型別延伸介面（`FCFactoryOption`、`FCFactoryEvent`） |
| `stashArrayFactory.ts` | 操作 localStorage 的暫存陣列工具，自動過濾 24 小時前的過期資料 |
| `classes.ts` | `Warning` 錯誤類別，用於區分警告與一般錯誤 |
| `README.md` | 函式庫功能描述與注意事項（專案原始文件） |

---

## 各章節參考文件

### myFuncCompFactory 完整說明
參見 [references/01-myfunccompfactory.md](./references/01-myfunccompfactory.md)：
- 工廠函式簽章與四個泛型參數（State、Actions、Props、Context）
- Option 參數結構（getInitialState、actionsImpl、view、useContext、events、abortableActions）
- 非同步 Action 的生命週期（getPromise → effects → sideEffects → errorSideEffects）
- View Props 結構：state + actions + loading 狀態如何傳遞給 View 元件
- Context 化機制與 `useXxxContext()` hook 的產生方式
- events 機制：watch → mapToState / triggerAction
- abortableActions 與 `MYFC_ABORT_ERROR` 中斷機制
- 輔助型別：`SetStateActions`、`OptimizeDecoratedActions`

### 其他函式庫工具
參見 [references/02-other-libs.md](./references/02-other-libs.md)：
- `fcFactory.tsx`：FCFactoryOption 擴充欄位（contextlize、passLoading、passProps）
- `stashArrayFactory.ts`：push / list / clear / removeBy 操作介面與過期機制
- `classes.ts`：Warning 類別的判斷方式（`instanceof Warning` / `error.name === 'Warning'`）
