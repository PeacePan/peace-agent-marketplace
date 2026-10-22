#!/usr/bin/env node
/**
 * 對 Ragdoll 主程序（Electron main process）的 Node inspector 執行一段 JS，印出回傳值。
 * 供「模擬資料法」包住 ipcMain 處理器、讀取命中紀錄與還原使用（見 references/memory-fixture.md）。
 *
 * 用法：node inspector-eval.mjs <運算式檔案> [--port 9229]
 * 需求：Node 22+（內建 fetch 與 WebSocket）。`npm run dev` 啟動的 Electron 預設開 9229。
 * 運算式檔案必須是單一運算式，建議寫成立即執行函式 `(() => { ... })()`，回傳值需可序列化。
 *
 * 結束碼：0 成功；1 運算式拋出例外；2 參數錯誤；3 連不上 inspector；4 逾時。
 */
import { readFileSync } from 'node:fs';

const args = process.argv.slice(2);
const exprFile = args.find((arg) => !arg.startsWith('--'));
const portIndex = args.indexOf('--port');
const port = portIndex > -1 ? args[portIndex + 1] : (process.env.INSPECTOR_PORT ?? '9229');

if (exprFile === void 0) {
  console.error('用法：node inspector-eval.mjs <運算式檔案> [--port 9229]');
  process.exit(2);
}

const expression = readFileSync(exprFile, 'utf8');
const targets = await fetch(`http://127.0.0.1:${port}/json/list`)
  .then((res) => res.json())
  .catch(() => []);

if (!Array.isArray(targets) || targets.length === 0) {
  console.error(`找不到 inspector 目標（port ${port}）。Ragdoll 是否已用 npm run dev 啟動？`);
  process.exit(3);
}

const ws = new WebSocket(targets[0].webSocketDebuggerUrl);
const timer = setTimeout(() => {
  console.error('逾時（10 秒）');
  process.exit(4);
}, 10000);

ws.onerror = () => {
  console.error('WebSocket 連線失敗');
  process.exit(3);
};
ws.onopen = () => {
  ws.send(JSON.stringify({
    id: 1,
    method: 'Runtime.evaluate',
    params: { expression, returnByValue: true, awaitPromise: true },
  }));
};
ws.onmessage = (msg) => {
  const data = JSON.parse(msg.data);
  if (data.id !== 1) return;
  clearTimeout(timer);
  const exception = data.result?.exceptionDetails;
  if (exception !== void 0 || data.error !== void 0) {
    console.error('執行失敗：', exception?.exception?.description ?? exception?.text ?? JSON.stringify(data.error));
    ws.close();
    process.exit(1);
  }
  console.log(JSON.stringify(data.result?.result?.value ?? null, null, 2));
  ws.close();
};
