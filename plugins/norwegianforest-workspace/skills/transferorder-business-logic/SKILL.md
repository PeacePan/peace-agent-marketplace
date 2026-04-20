---
name: transferorder-business-logic
description: >
  NorwegianForest 調撥單（transferorder）完整業務邏輯知識。
  當需要撰寫或修改調撥單相關腳本（policy、batchBeforeUpdate、各種 function），
  或需要了解調撥單與 DSV 出貨系統的整合方式、hqWareHouseStatus 狀態機、
  WH/WHAT/ST/DN 各類型差異時，務必先讀此 skill。
---

# 調撥單（transferorder）業務邏輯全覽

調撥單是 NorwegianForest 存貨移轉的核心單據，負責記錄從來源倉庫到目標倉庫的調撥作業。

## 參考文件目錄

| 文件 | 內容摘要 | 何時閱讀 |
|-----|---------|---------|
| [schema.md](references/schema.md) | 完整欄位定義、lines 結構、表格關聯 | 接觸調撥單欄位時 |
| [types.md](references/types.md) | WH/WHAT/ST/DN 類型差異、各類型的業務規則 | 撰寫類型相關判斷邏輯時 |
| [hq-warehouse-status.md](references/hq-warehouse-status.md) | hqWareHouseStatus 狀態機、DSV 上線後的流程變化 | 修改總倉調撥檢查流程時 |
| [dsv-integration.md](references/dsv-integration.md) | transferorder → dsvorder 整合流程、upsertDSVOrder 邏輯 | 修改 policy 或涉及 DSV 出貨時 |
| [scripts-reference.md](references/scripts-reference.md) | 13 個腳本的用途說明、batchBeforeUpdate 重點邏輯 | 不確定要改哪個腳本時 |

## 快速定位

- **調撥單建立** → [dsv-integration.md](references/dsv-integration.md) 的「建立流程」
- **push/set/pull 表身列觸發的邏輯** → [scripts-reference.md](references/scripts-reference.md) 的「batchBeforeUpdate 詳解」
- **為什麼調撥單有 hqWareHouseStatus** → [hq-warehouse-status.md](references/hq-warehouse-status.md)
- **WHAT 自動調撥與 WH 手動調撥的差異** → [types.md](references/types.md)
- **調撥單欄位一覽** → [schema.md](references/schema.md)
