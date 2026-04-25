# Ragdoll Workflow Superpowers Handoff 改善設計

## 問題

`ragdoll-develop-workflow` 在呼叫 superpowers skill 時，有兩個自動化中斷點：

1. **writing-plans Execution Handoff 詢問** — `writing-plans` 儲存 Plan 後會問使用者選擇「Subagent-Driven 或 Inline Execution」，與 ragdoll workflow 的自主執行衝突。
2. **漏掉 plan-challenger** — `writing-plans` 完成後，模型偶爾直接進入 [PLAN] 階段，跳過 Step 2.5 的 plan-challenger HARD GATE。

## 根因

現行的禁止寫法（「MUST NOT 呼叫 X」）是消極的，無法在 LLM 同時載入兩份 skill 指令時明確告知「在這個時間點，下一個動作是什麼」。模型收到矛盾訊號後選擇詢問使用者。

## 解法範圍

只修改 `plugins/ragdoll-workspace/skills/ragdoll-develop-workflow/SKILL.md`，不新增或 fork 任何 skill。

## 人為參與邊界

- **需要人為介入**：[DEFINE] 階段需求收集、Step 2.5 plan-challenger 審查結果的決策
- **全自動**：writing-plans 完成後 → plan-challenger → [PLAN] → 後續所有階段

## 修改點

### 修改一：Step 2 末尾加入 writing-plans 流程覆寫

在 `### Step 2 — 擬定 Plan + 三層 Test Cases` 呼叫 `superpowers:writing-plans` 的段落後，緊接加入：

```
> **⚠ writing-plans 流程覆寫（MUST 遵守）**
> writing-plans 儲存 Plan 文件後會詢問「Subagent-Driven 或 Inline Execution？」。
> 在本工作流程中，**MUST 跳過此問題，不得詢問使用者，立即進入 Step 2.5**。

**⛔ HARD GATE — writing-plans 完成後，唯一的下一步是 Step 2.5，不得跳過。**
```

### 修改二：Step 2.5 開頭補充自動觸發說明

在 `### Step 2.5 — HARD GATE：plan-challenger 審查` 標題下方加入：

```
> 此步驟在 writing-plans 儲存 Plan 完成後**自動觸發**，不需使用者確認。
```

## 預期效果

`writing-plans → plan-challenger → [PLAN]` 變成強制的全自動序列，模型在任何情況下都不會在這段路徑上詢問使用者。
