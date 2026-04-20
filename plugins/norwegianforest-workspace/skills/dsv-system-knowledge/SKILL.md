---
name: dsv-system-knowledge
description: >
  NorwegianForest DSV 出貨系統完整業務知識。涵蓋 dsvorder、dsvorderdetail、
  dsvshipment、dsvdailytask、dsvinventory、dsvinventoryoperation 六個表格的
  欄位定義、業務邏輯、狀態機與表格關聯。當需要撰寫或修改任何 DSV 相關腳本，
  或需要了解 DSV 出貨流程、批號回填機制、庫存同步邏輯時，務必先讀此 skill。
---

# DSV 出貨系統業務知識

DSV 是 NorwegianForest 使用的第三方物流（3PL）服務商，負責總倉商品出貨到門市。
本系統以六個表格記錄從「建立出貨單」到「交貨完成」的完整生命週期。

## 參考文件目錄

| 文件 | 內容摘要 | 何時閱讀 |
|-----|---------|---------|
| [tables-overview.md](references/tables-overview.md) | 六個表格的用途、欄位摘要與表格關聯圖 | 第一次了解 DSV 系統架構 |
| [dsvorder.md](references/dsvorder.md) | 出貨單主表：狀態機、flowStatus、排程與函式 | 修改 dsvorder 相關邏輯 |
| [dsvorderdetail.md](references/dsvorderdetail.md) | 出貨明細：批號回填機制、batchPolicy 邏輯 | 修改 dsvorderdetail 或批號相關邏輯 |
| [dsvshipment.md](references/dsvshipment.md) | 貨況追蹤：同步機制、狀態同步排程 | 修改貨況同步邏輯 |
| [dsvdailytask.md](references/dsvdailytask.md) | 每日配貨檔：庫存同步機制、FTP 流程 | 修改每日庫存同步邏輯 |
| [inventory-tracking.md](references/inventory-tracking.md) | dsvinventory 與 dsvinventoryoperation：配貨庫存結構 | 修改庫存相關查詢或異動記錄 |

## 快速定位

- **出貨單狀態不對** → [dsvorder.md](references/dsvorder.md) 的狀態機
- **批號沒有回填** → [dsvorderdetail.md](references/dsvorderdetail.md) 的 batchPolicy 邏輯
- **貨況沒有更新** → [dsvshipment.md](references/dsvshipment.md) 的同步機制
- **庫存數字不準** → [dsvdailytask.md](references/dsvdailytask.md) 的同步機制
- **表格之間如何關聯** → [tables-overview.md](references/tables-overview.md) 的關聯圖

## 核心業務流程（一句話版）

```
transferorder.policy → upsertDSVOrder
  → dsvorder (PENDING) + dsvorderdetail (無批號)
  → dsvorderdetail.batchPolicy 回填批號
  → 人工拋單 → CSV 上傳 FTP
  → DSV 排程同步狀態 → dsvshipment 記錄貨況
  → 調轉驗 → ITEM_RECEIPT
```
