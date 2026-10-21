#!/usr/bin/env node
/**
 * petpetgo-reviewer 的寫入防線：reviewer 只能建立 pending review，絕不能送出、Approve、刪除或解決討論串。
 * GitHub MCP 把 create／submit_pending／delete_pending／resolve_thread 放在同一個工具，
 * disallowedTools 無法只擋其中一個 method，所以改由這支 PreToolUse hook 依 agent_type 與 tool_input 判斷。
 * 只對 petpetgo-reviewer 生效，主對話與其他 agent 不受影響。
 * 放行的只有「create 且不帶 event」：帶 event（APPROVE／REQUEST_CHANGES／COMMENT）會立刻公開送出。
 * @see plugins/wonderpet-general/agents/petpetgo-reviewer.md 寫入準則
 */
const fs = require('fs');

const cReviewerAgentSuffix = 'petpetgo-reviewer';

/** 回傳 deny 決定給 Claude Code，並附上原因讓 reviewer 知道該怎麼做 */
function deny(reason) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: reason,
      },
    }),
  );
}

function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  if (!String(input.agent_type ?? '').endsWith(cReviewerAgentSuffix)) return;
  const { method, event } = input.tool_input ?? {};
  if (method === 'create' && !event) return;
  deny(
    `petpetgo-reviewer 只能用 pull_request_review_write 的 create（不帶 event）建立 pending review。` +
      `不可送出、Approve、刪除或解決討論串（method=${method}, event=${event ?? '無'}）。` +
      `請改用 add_comment_to_pending_review 加 inline comment，由人到 Files changed 頁面送出。`,
  );
}

main();
