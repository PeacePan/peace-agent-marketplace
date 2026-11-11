#!/usr/bin/env node
/**
 * 把「相依群組合計超過單次請求上限」的 patch，拆成多個 GraphQL 請求依序送到 staging。
 *
 * 為什麼可行：「相依表必須同批」只是 `npm run patch:staging`（tables/index.ts 的 checkTableDependencies）
 * 在產生 body 之前做的檢查；產生出來的 patchV2 body 本身是一個 data 陣列，伺服器逐筆處理，可以分次請求。
 * 代價：請求之間 staging 有短暫（秒級）的版本不一致。
 *
 * 本腳本送出的內容與工具完全相同：同一份 `bin/table.sh --staging print` 的結果、同一個 mutation、
 * 同一份存在 tables/.table.patch.env 的 staging 憑證。它不做相依檢查，也不做 ⚠️ 檢查，
 * 所以必須先用 `CHECK_ONLY=1 run-patch.sh` 讓工具把整個群組檢查過（版本、相依、⚠️），再用本腳本送出。
 *
 * 用法：
 *   node send-split.mjs --worktree <worktree 根目錄> --requests "表1,表2|表3,表4" [--dry] [--no-probe]
 *     --requests  每個請求一組、以 `|` 分隔；表名以 `,` 分隔（可由 plan.json 的 batches[].requests 取得）
 *     --dry       只檢查版號、算大小、探測，不送出 patch
 *     --no-probe  略過大小探測
 *
 * 流程：①print 各表內容 ②查 staging 現值並確認「分支版號 > 現值」③以無副作用的大請求探測最大那個請求的大小
 * 是否被接受（413 就中止，不會寫入任何東西）④依序送出，任何一個請求失敗就立刻停止並列出已寫入／未寫入的表。
 *
 * 結束碼：0 全部寫入成功（或 --dry 通過）；1 失敗或中止。
 *
 * @example
 * ```
 * node send-split.mjs --worktree <repo>/.claude/worktrees/nf-staging-patch \
 *   --requests "possale,posofflinetransaction|posservicesale,posreturn,posservicereturn,poscustomerorder,poscustomerorderwithdraw"
 * ```
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const cEndpoint = 'https://data-api-staging.wonderpet.asia/graphql';
const cPatchMutation = 'mutation($data: [PatchRecord!]!) { patchV2(table: "__table__" data: $data) }';
const cFindQuery =
  'query findV2($table: String!, $skipLines: Boolean, $archived: ArchivedStatus, $approved: ApprovedStatus, $filters: [FindFilter!], $selects: [String]) { findV2 ( table: $table, filters: $filters, archived: $archived, skipLines: $skipLines, selects: $selects, approved: $approved ) { _id bodyFields { fieldName valueType boolean string number date id } lineRows { lineName lineFields { fieldName valueType boolean string number date id } } } }';

/**
 * 解析 `--key value` 與 `--flag` 形式的參數
 * @param {string[]} argv 命令列參數
 * @returns {Record<string, string | boolean>} 參數對照表
 */
function parseArgs(argv) {
  /** @type {Record<string, string | boolean>} */
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith('--')) continue;
    const next = argv[i + 1];
    if (next === void 0 || next.startsWith('--')) args[argv[i].slice(2)] = true;
    else args[argv[i].slice(2)] = argv[++i];
  }
  return args;
}

/**
 * 送出一個 GraphQL 請求（與 patch 工具相同的標頭）
 * @param {string} jwt staging 的 JWT
 * @param {string} cookie session cookie
 * @param {unknown} body 請求內容
 * @returns {Promise<{ status: number, text: string, json: any }>} 回應狀態、原文與解析結果（解析失敗為 undefined）
 */
async function post(jwt, cookie, body) {
  const res = await fetch(cEndpoint, {
    method: 'post',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${jwt}`, cookie },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    json = void 0;
  }
  return { status: res.status, text, json };
}

// ============================================================
// Step 1: 讀參數、憑證，取得各表的 patch 內容
// ============================================================
const args = parseArgs(process.argv.slice(2));
if (typeof args.worktree !== 'string' || typeof args.requests !== 'string') {
  console.error('用法：node send-split.mjs --worktree <worktree 根目錄> --requests "表1,表2|表3" [--dry] [--no-probe]');
  process.exit(1);
}
const nfDir = path.join(args.worktree, 'NorwegianForest');
const groups = args.requests.split('|').map((g) => g.split(',').map((s) => s.trim()).filter(Boolean));
const names = groups.flat();
if (new Set(names).size !== names.length) {
  console.error('同一張表出現在多個請求中');
  process.exit(1);
}
const auth = JSON.parse(fs.readFileSync(path.join(nfDir, 'tables', '.table.patch.env'), 'utf8')).auth?.staging;
if (!auth?.jwt) {
  console.error('worktree 的 .table.patch.env 沒有 staging 憑證：先用 run-patch.sh 讓工具登入（會要 OTP）');
  process.exit(1);
}
const exp = JSON.parse(Buffer.from(auth.jwt.split('.')[1], 'base64url').toString()).exp * 1000;
if (exp < Date.now()) {
  console.error('staging 憑證已過期：先用 run-patch.sh 讓工具重新登入（會要 OTP）');
  process.exit(1);
}
const printed = spawnSync('bash', ['bin/table.sh', '--staging', 'print', names.join(',')], { cwd: nfDir, encoding: 'utf8', maxBuffer: 1 << 30 });
if (printed.status !== 0) {
  console.error(printed.stderr);
  process.exit(1);
}
/** @type {Record<string, { record: any, version: number }>} */
const local = {};
for (const line of printed.stdout.split('\n')) {
  if (!line.startsWith('{')) continue;
  const record = JSON.parse(line);
  const field = (fieldName) => record.bodyFields.find((f) => f.fieldName === fieldName);
  local[field('name').string] = { record, version: field('version')?.number };
}
const missing = names.filter((n) => !local[n]);
if (missing.length > 0) {
  console.error(`print 不到這些表：${missing.join(', ')}`);
  process.exit(1);
}

// ============================================================
// Step 2: 版本檢查（與工具相同：分支版號必須嚴格大於 staging 現值，否則中止，不送任何請求）
// ============================================================
const found = await post(auth.jwt, auth.sessionCookie ?? '', {
  query: cFindQuery,
  variables: {
    table: '__table__',
    filters: names.map((n) => ({ bodyConditions: [{ fieldName: 'name', valueType: 'STRING', operator: 'in', string: n }] })),
    archived: 'NORMAL',
    skipLines: true,
    selects: ['body.name', 'body.version'],
    approved: null,
  },
});
/** @type {Record<string, number | undefined>} */
const remote = {};
for (const item of found.json?.data?.findV2 ?? []) {
  const field = (fieldName) => item.bodyFields.find((f) => f.fieldName === fieldName);
  remote[field('name')?.string] = field('version')?.number;
}
let versionOk = true;
for (const n of names) {
  const ok = n in remote && (typeof remote[n] !== 'number' || local[n].version > remote[n]);
  if (!ok) versionOk = false;
  console.log(`${ok ? '✅' : '❌'} ${n}：分支版號 ${local[n].version}，staging 現值 ${remote[n] ?? '（無）'}`);
}
if (!versionOk) {
  console.error('版本檢查未通過，沒有送出任何請求');
  process.exit(1);
}

// ============================================================
// Step 3: 組出各請求的 body 並算大小
// ============================================================
const requests = groups.map((group) => {
  const data = group.map((n) => ({ keyName: 'name', keyValue: n, bodyFields: local[n].record.bodyFields, lineRows: local[n].record.lineRows }));
  const body = { query: cPatchMutation, variables: { data } };
  return { group, body, bytes: Buffer.byteLength(JSON.stringify(body)) };
});
console.log('\n| 請求 | 表數 | 大小 | 表 |\n|---|---|---|---|');
requests.forEach((r, i) => console.log(`| ${i + 1} | ${r.group.length} | ${(r.bytes / 1e6).toFixed(2)}MB | ${r.group.join(', ')} |`));

// ============================================================
// Step 4: 探測最大請求的大小會不會被擋（無副作用的查詢加上同樣大小的填充；413 就中止，什麼都不會寫）
// ============================================================
const largest = Math.max(...requests.map((r) => r.bytes));
if (!args['no-probe']) {
  const probe = await post(auth.jwt, auth.sessionCookie ?? '', { query: 'query($pad: String) { __typename }', variables: { pad: 'x'.repeat(largest) } });
  console.log(`\n探測 ${(largest / 1e6).toFixed(2)}MB：HTTP ${probe.status}${probe.status === 413 ? '（Request Entity Too Large）' : '（大小被接受）'}`);
  if (probe.status === 413) {
    console.error('最大的請求超過上限，沒有寫入任何東西；請拆成更多個請求');
    process.exit(1);
  }
}
if (args.dry) {
  console.log('\n--dry：不送出 patch');
  process.exit(0);
}

// ============================================================
// Step 5: 依序送出；任何一個失敗就立刻停止，並列出已寫入與未寫入的表
// ============================================================
/** @type {string[]} */
const written = [];
for (const [i, r] of requests.entries()) {
  const res = await post(auth.jwt, auth.sessionCookie ?? '', r.body);
  const ids = res.json?.data?.patchV2;
  if (Array.isArray(ids) && ids.length === r.group.length) {
    written.push(...r.group);
    console.log(`請求 ${i + 1}/${requests.length} 成功：寫入 ${ids.length} 張，id：${ids.join(',')}`);
    continue;
  }
  console.error(`請求 ${i + 1}/${requests.length} 失敗：HTTP ${res.status}，回應前 300 字：${res.text.slice(0, 300)}`);
  console.error(`已寫入：${written.join(', ') || '（無）'}`);
  console.error(`未寫入：${names.filter((n) => !written.includes(n)).join(', ')}`);
  process.exit(1);
}
console.log('\n全部請求成功。成功與否仍以 MCP 查 staging 的 body.version 為準。');
