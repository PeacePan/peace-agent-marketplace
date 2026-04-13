---
name: norwegianforest-testing-architecture
description: >
  NorwegianForest 測試架構完整知識庫。涵蓋 Mocha/Chai/NYC 框架配置、
  MySandbox QueryProcessor Mock 策略、QueryEventEmitter 事件追蹤，
  以及 Policy / BatchPolicy / Approval / Hook / Function（含 TodoJob）/
  純單元測試六種腳本類型的標準測試模板。
  撰寫或維護 NorwegianForest tests/ 目錄下的測試時必讀。
---

# NorwegianForest 測試架構

NorwegianForest 測試套件涵蓋 43 個業務模組、86 個測試檔，全部使用 Mocha + Chai + TypeScript 撰寫。所有 DB 操作均透過 `MySandbox.queryProcessor` 攔截，無需連接真實資料庫。

## 參考文件目錄

| 文件 | 內容摘要 | 何時閱讀 |
|------|---------|---------|
| [01-framework-environment.md](references/01-framework-environment.md) | Mocha/Chai/NYC 配置、`generateExecuteFunc` / `executeFuncUntilDoneOrError` API、目錄結構慣例 | 剛開始撰寫測試、不知道工具函式用法時 |
| [02-mock-patterns.md](references/02-mock-patterns.md) | QueryProcessor Mock 模板、QueryEventEmitter 追蹤模式、Mock 工廠函式、SafeRecord2 格式 | 不知道如何 mock DB 查詢、需要追蹤特定查詢是否被呼叫時 |
| [03-script-type-testing.md](references/03-script-type-testing.md) | Policy / BatchPolicy / Approval / BeforeInsert / BeforeUpdate / Function / TodoJob / 純單元測試的完整程式碼模板 | 撰寫特定類型腳本的測試時 |

## 快速定位

- **剛接觸測試，不知從何下手** → 先讀 [01](references/01-framework-environment.md)，再讀 [02](references/02-mock-patterns.md)
- **Policy 測試怎麼寫** → [03 § 1 Policy](references/03-script-type-testing.md)
- **Approval 測試怎麼寫** → [03 § 3 Approval](references/03-script-type-testing.md)
- **Function 腳本測試，ctx 是 undefined / todoJob 是 undefined** → [01 § generateExecuteFunc 重要說明](references/01-framework-environment.md)（需傳 `[record, null]`）
- **TodoJob 多階段函式測試** → [03 § 7 Function TodoJob](references/03-script-type-testing.md)
- **如何確認腳本有觸發特定 updateV2** → [02 § QueryEventEmitter](references/02-mock-patterns.md)
- **不知道 mock 哪些 query.method** → [02 § query.method 完整列表](references/02-mock-patterns.md)
- **純計算函式測試（無 DB）** → [03 § 8 純單元測試](references/03-script-type-testing.md)
- **多個測試需要不同 mock 配置** → [02 § 條件式 Mock 工廠函式](references/02-mock-patterns.md)
