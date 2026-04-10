---
name: github-update-pr-summary
description: 依照規範產生並更新 GitHub PR 描述。根據 PR 是否包含 Norwegianforest 資料夾的變更，自動選擇對應的描述範本（含或不含 NorwegianForest 開發者提醒事項）。
---

# GitHub PR 描述更新規範

本技能定義如何產生並更新 GitHub Pull Request 的描述內容。

---

## 執行步驟

1. **偵測 PR 是否包含 Norwegianforest 資料夾的變更**：

   ```bash
   gh pr diff <PR-number> --name-only | grep -i "norwegianforest"
   ```

   - 若有輸出結果 → 使用**NorwegianForest 範本**
   - 若無輸出結果 → 使用**標準範本**

2. **從分支名稱萃取 ticket 編號**：

   ```bash
   git branch --show-current
   ```

   從分支名稱中解析出 ticket 編號（依照呼叫方提供的 `branch-naming-rule` 格式）。
   若分支名稱不包含 ticket 編號，卡片連結欄位填入：`分支名稱沒有包含 ticket 編號，無法產生 ticket 連結`。

3. **使用對應範本填入描述後，更新 PR**：

   ```bash
   gh pr edit <PR-number> --body "<產生的描述內容>"
   ```

---

## 標準範本

適用於**不包含** Norwegianforest 資料夾變更的 PR。

```markdown
## 摘要
<!--
簡述如何實作此功能，如果是錯誤修正，請說明錯誤的發生原因
-->
{描述在此處}

## 卡片連結
{ticket-url-prefix}/{ticket}

## 提醒事項
### 📋 開發者提醒事項
- 確認 PR 標題描述正確
- 確認 Merge base
- 確認 Label 標示正確
### 📋 審查者提醒事項
- 確認 merge target
- 確認 Label 更改完成
- 確認代碼註解是否完善
- 列出建議修正項目
- 列出建議效能優化項目
```

---

## NorwegianForest 範本

適用於**包含** Norwegianforest 資料夾變更的 PR（開發者提醒事項增加 NorwegianForest 特有項目）。

```markdown
## 摘要
<!--
簡述如何實作此功能，如果是錯誤修正，請說明錯誤的發生原因
-->
{描述在此處}

## 卡片連結
{ticket-url-prefix}/{ticket}

## 提醒事項
### 📋 開發者提醒事項
- 確認 PR 標題描述正確
- 確認 Merge base
- 確認 Label 標示正確
- 表格變更 Review 完 Patch Dev 表格
- Hotfix 表格變更 Merge Sprint 表格分支後再 Patch 到 Dev 表格
- Hotfix 表格變更向下 Merge 後要再 Patch 到各個分支（Staging、Dev）的表格
- 如果有新開表格或是新增函數，請填寫 Confluence 文件
### 📋 審查者提醒事項
- 確認 merge target
- 確認 Label 更改完成
- 確認代碼註解是否完善
- 列出建議修正項目
- 列出建議效能優化項目
```

---

## 注意事項

- `{描述在此處}` 請根據本次 PR 實際的實作內容填寫，簡潔描述功能或錯誤修正原因。
- `{ticket-url-prefix}/{ticket}` 請替換為實際的卡片連結（由呼叫方提供的 `ticket-url-prefix` 參數與從分支名稱解析出的 ticket 編號組合而成）。
- 若無法解析 ticket 編號，卡片連結欄位填入：`分支名稱沒有包含 ticket 編號，無法產生 ticket 連結`。
