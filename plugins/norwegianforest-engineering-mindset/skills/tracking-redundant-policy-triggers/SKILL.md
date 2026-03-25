---
name: tracking-redundant-policy-triggers
description: >
  追蹤並消除系統中冗餘的 policy/hook 觸發的工程方法論。
  當遇到操作逾時、效能異常緩慢、或懷疑有重複觸發邏輯時，使用此 skill
  系統性地繪製觸發鏈、識別冗餘節點，並設計最小化修正方案。
  適用於任何具備 event-driven hook 機制的系統（不限 NorwegianForest）。
---

# 追蹤冗餘 Policy 觸發的工程方法論

## 問題特徵

當你看到以下症狀，可能存在冗餘觸發問題：

- 單筆操作執行時間遠超預期（例如 push 1 筆資料卻花了 50 秒）
- 日誌中相同的查詢或計算重複出現多次
- 資源使用量（記憶體、DB 連線）與操作規模不成比例

---

## 方法論：五步驟分析法

### Step 1：確認單一操作的邊界

明確定義「一次操作」是什麼：

```
誰（使用者/排程）在什麼時機對哪個表做什麼動作
例：人工對 transferorder push 1 筆表身列
```

### Step 2：繪製第一層觸發

從該操作開始，列出**直接觸發**的 hooks/policies：

```
操作 → [hook1] → [hook2] → ...
```

針對每個 hook，記錄：
- 它做了哪些 **寫入操作**（write）
- 每個寫入操作的目標表格
- `ignorePolicy` 設定是 true/false/undefined

### Step 3：遞迴展開觸發鏈

對每個寫入操作，繼續展開它可能觸發的 hooks：

```
操作
  → write A（ignorePolicy:false）
      → A.policy
          → write B
              → B.batchPolicy
                  → write C → ...
  → write D（ignorePolicy:true）
      → D.batchBeforeUpdate（仍然觸發！）
          → write E → ...
```

**關鍵原則**：
- `ignorePolicy: true` 只跳過 `policy` 和 `batchPolicy`，**不跳過 `beforeInsert`、`beforeUpdate`、`batchBeforeInsert`、`batchBeforeUpdate`** 這四個 before hook
- INSERT 觸發 batchPolicy 時，`oldRecords = undefined`

繼續遞迴，直到所有路徑都終止（不再有新的寫入）。

### Step 4：標記每個觸發的必要性

對每個節點標記 ✅ / ❌：

| 節點 | 標記 | 判斷依據 |
|-----|-----|---------|
| dsvorder.policy [D2] | ✅ | 由 upsertDSVOrder 觸發，是主要的庫存計算 |
| dsvorder.policy [D1] | ❌ | B1 中的量變更新，但 D2 在 B1 完成後執行，結果更準確 |
| dsvorder.policy [D4] | ❌ | batchBeforeUpdate 中的 dsvorder 更新，D2 已涵蓋 |

**判斷冗餘的核心問題**：

> 「如果這個觸發被跳過，最終結果還是正確的嗎？」
> 「有沒有另一個觸發（在更晚的時間點）會得到同樣甚至更正確的結果？」

關鍵洞察：**越晚執行的觸發，看到的狀態越完整**。如果一個必要的觸發在所有寫入完成後才執行，中間的相同觸發通常是冗餘的。

### Step 5：設計最小化修正

針對每個冗餘節點，選擇最小侵入性的修正方式：

| 修正方式 | 適用場景 | 範例 |
|---------|---------|-----|
| 加上 `&& oldRecords` 條件 | INSERT 情境下誤觸發的邏輯 | batchPolicy 的 quantityChanged 區塊 |
| 傳遞旗標（userContent flag） | 特定來源觸發時跳過部分邏輯 | `isFromDSVOrderDetailBatchPolicy: true` |
| 將 `ignorePolicy: undefined` 改為 `true` | batchPolicy 被冗餘觸發 | batchBeforeUpdate 更新 dsvorderdetail |
| 將 `.then()` 鏈拆分，條件化執行 | 某些情況下不需要後續更新 | batchBeforeUpdate 的 dsvorder 更新 |

---

## 觸發鏈繪製範本

使用以下格式記錄觸發鏈（方便審視）：

```
[操作] push X 筆
  │
  ├─ [HOOK-A] table.batchBeforeUpdate（always runs，ignorePolicy 對所有 before hook 無效）
  │     │
  │     └─ write B（ignorePolicy:false）
  │           └─ [B.policy] ← 標注必要性 ✅/❌
  │
  └─ [HOOK-C] table.policy（ignorePolicy:true → skipped）
        │
        └─ write D（ignorePolicy:false）
              └─ [D.batchPolicy] → INSERT，oldRecords=undefined
                    ├─ write E（ignorePolicy:true）
                    │     └─ [E.batchBeforeUpdate] ← 仍然觸發（before hook 無法被 ignorePolicy 跳過）
                    └─ write F（觸發條件：oldRecords 有值）← ✅ 已加防護
```

---

## 實際案例參考

詳見 [case-study-wh-transferorder.md](references/case-study-wh-transferorder.md)：

NorwegianForest WH 調撥單 push 表身列的完整分析，
`dsvorder.policy` 從 4 次減少為 1 次，執行時間從 >50 秒降至 ~15 秒。
