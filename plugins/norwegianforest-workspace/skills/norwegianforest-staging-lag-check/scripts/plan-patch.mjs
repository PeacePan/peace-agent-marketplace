#!/usr/bin/env node
/**
 * 依「落後清單」產生 staging patch 計畫：
 * 讀出各表在 staging 分支上的版號、相依關係與 patch 內容大小，
 * 分出「可以 patch 的批次」與「被擋下的表（含原因）」。
 *
 * 為什麼需要這支腳本：patch 工具（NorwegianForest/tables/index.ts）有三個限制，
 * 沒算好會讓整批作廢，甚至「假成功」，必須在動手前先算出來：
 *   1. 版本檢查：只要有一張表「分支版號 <= staging 現值」，整批中止，什麼都不會寫入。
 *   2. 相依檢查：表的 dependencyTables／source 必須和它在同一個指令一起 patch。
 *   3. 請求大小：單次請求太大會被伺服器回 413，但工具仍然印「已成功更新表格」。
 *
 * 用法：
 *   node plan-patch.mjs --lag <lag.tsv> --worktree <worktree 根目錄> [--max-bytes 3500000] [--out <輸出目錄>]
 *
 * lag.tsv：每行 `表名<TAB>production 版號<TAB>staging 版號`。
 *   production 版號未知（例如補查反向相依表時）寫 `-`。
 *
 * 輸出：
 *   <輸出目錄>/plan.json  機器可讀的計畫（batches、blocked、expected、verifyFilters）
 *   stdout                給人看的 Markdown 摘要
 *
 * 結束碼：0 計畫完成；2 有相依表需要補查 staging 版號（補進 lag.tsv 後重跑）。
 *
 * @example
 * ```
 * node plan-patch.mjs --lag /tmp/lag.tsv --worktree <repo>/.claude/worktrees/nf-staging-patch
 * ```
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

/**
 * 單次請求大小上限的預設值。
 * 2026-11-11 在 staging 實測：3.54MB 成功、7.88MB 回 413，真正上限落在兩者之間，
 * 取 3.5MB 是「已證實可行」的保守值，可用 --max-bytes 調整。
 */
const cDefaultMaxBytes = 3_500_000;

/**
 * 解析 `--key value` 形式的參數
 * @param {string[]} argv 命令列參數（不含 node 與腳本路徑）
 * @returns {Record<string, string>} 參數對照表
 */
function parseArgs(argv) {
  /** @type {Record<string, string>} */
  const args = {};
  for (let i = 0; i < argv.length; i += 2) {
    if (argv[i].startsWith('--')) args[argv[i].slice(2)] = argv[i + 1];
  }
  return args;
}

/**
 * 掃描 tables/<領域>/<表名>.ts，找出宣告了 dependencyTables 或 `source: TABLE_NAME.*` 的表格定義檔。
 * 用靜態掃描而不是一次 print 全部表，是因為全站表格 print 出來有上百 MB。
 * @param {string} nfDir NorwegianForest 目錄
 * @returns {string[]} 有相依宣告的表名（檔名即表名）
 */
function findDependencyBearingTables(nfDir) {
  const root = path.join(nfDir, 'tables');
  /** @type {string[]} */
  const names = [];
  for (const domain of fs.readdirSync(root, { withFileTypes: true })) {
    if (!domain.isDirectory()) continue;
    for (const file of fs.readdirSync(path.join(root, domain.name), { withFileTypes: true })) {
      if (!file.isFile() || !file.name.endsWith('.ts')) continue;
      const text = fs.readFileSync(path.join(root, domain.name, file.name), 'utf8');
      if (/^[ \t]*(dependencyTables:|source:[ \t]*TABLE_NAME\.)/m.test(text)) names.push(file.name.slice(0, -3));
    }
  }
  return names;
}

/**
 * 用 `bin/table.sh --staging print` 取得各表實際的 patch 內容。
 * 這與 patch 時送出的 bodyFields 一致，所以版號、相依欄位、大小都以它為準，不靠檔案內容推測。
 * @param {string} nfDir NorwegianForest 目錄
 * @param {string[]} names 要 print 的表名
 * @returns {Record<string, { version: number | undefined, deps: string[], bytes: number }>} 各表資訊
 */
function printTables(nfDir, names) {
  const r = spawnSync('bash', ['bin/table.sh', '--staging', 'print', names.join(',')], {
    cwd: nfDir,
    encoding: 'utf8',
    maxBuffer: 1 << 30,
  });
  if (r.status !== 0) {
    console.error(r.stderr);
    process.exit(1);
  }
  /** @type {Record<string, { version: number | undefined, deps: string[], bytes: number }>} */
  const result = {};
  for (const line of r.stdout.split('\n')) {
    if (!line.startsWith('{')) continue;
    const record = JSON.parse(line);
    /** @param {string} fieldName */
    const field = (fieldName) => record.bodyFields.find((f) => f.fieldName === fieldName);
    const name = field('name')?.string;
    const deps = [...(field('dependencyTables')?.string ?? '').split(','), field('source')?.string ?? '']
      .map((s) => s.trim())
      .filter(Boolean);
    result[name] = { version: field('version')?.number, deps, bytes: Buffer.byteLength(line) };
  }
  return result;
}

// ============================================================
// Step 1: 讀參數與落後清單
// ============================================================
const args = parseArgs(process.argv.slice(2));
if (!args.lag || !args.worktree) {
  console.error('用法：node plan-patch.mjs --lag <lag.tsv> --worktree <worktree 根目錄> [--max-bytes N] [--out DIR]');
  process.exit(1);
}
const maxBytes = Number(args['max-bytes'] ?? cDefaultMaxBytes);
const outDir = args.out ?? path.dirname(path.resolve(args.lag));
const nfDir = path.join(args.worktree, 'NorwegianForest');
/** @type {Map<string, { prod: number | undefined, staging: number | null }>} */
const rows = new Map();
for (const line of fs.readFileSync(args.lag, 'utf8').split('\n')) {
  const [name, prod, staging] = line.trim().split('\t');
  if (!name) continue;
  rows.set(name, { prod: prod === '-' ? void 0 : Number(prod), staging: staging === '-' ? null : Number(staging) });
}

// ============================================================
// Step 2: 取得分支上各表的版號、相依與大小（兩輪：落後清單＋有相依宣告的表，再補相依對象）
// ============================================================
const info = printTables(nfDir, [...new Set([...rows.keys(), ...findDependencyBearingTables(nfDir)])]);
const missingDeps = new Set();
for (const t of Object.values(info)) t.deps.forEach((d) => info[d] ?? missingDeps.add(d));
if (missingDeps.size > 0) Object.assign(info, printTables(nfDir, [...missingDeps]));

// ============================================================
// Step 3: 從落後清單出發，沿相依關係（雙向）找出所有相連的表
// ============================================================
/** @type {Map<string, Set<string>>} */
const adjacency = new Map();
/**
 * @param {string} a 表 a
 * @param {string} b 表 b
 */
function link(a, b) {
  adjacency.set(a, (adjacency.get(a) ?? new Set()).add(b));
  adjacency.set(b, (adjacency.get(b) ?? new Set()).add(a));
}
for (const [name, t] of Object.entries(info)) t.deps.forEach((d) => link(name, d));
const connected = new Set(rows.keys());
const queue = [...rows.keys()];
while (queue.length > 0) {
  for (const next of adjacency.get(queue.shift()) ?? []) {
    if (connected.has(next)) continue;
    connected.add(next);
    queue.push(next);
  }
}
const needStaging = [...connected].filter((n) => !rows.has(n) && info[n]);
if (needStaging.length > 0) {
  console.log('## 需要補查 staging 版號\n');
  console.log('下列表與落後清單內的表有相依關係，計畫需要它們在 staging 的現值（用 MCP 查 `__table__` 的 `body.version`）：\n');
  for (const n of needStaging) console.log(`- ${n}（分支版號 ${info[n].version}）`);
  console.log('\n補查後以 `<表名><TAB>-<TAB><staging 版號>` 加進 lag.tsv 再重跑。');
  process.exit(2);
}

// ============================================================
// Step 4: 分類：分支版號 > staging 現值才可 patch；相依群組同批；超過大小上限的擋下
// ============================================================
/** @type {{ name: string, reason: string }[]} */
const blocked = [];
const patchSet = new Set();
for (const name of connected) {
  const row = rows.get(name);
  const branchVersion = info[name]?.version;
  if (!info[name] || typeof branchVersion !== 'number') {
    blocked.push({ name, reason: '分支上找不到這張表或沒有版號' });
    continue;
  }
  if (row.staging === null || branchVersion > row.staging) patchSet.add(name);
  else if (row.prod !== void 0)
    blocked.push({ name, reason: `分支版號 ${branchVersion} ≤ staging 現值 ${row.staging}，版本檢查必擋；分支還沒收到 production 那版（需等 release→staging 同步或 hotfix-staging）` });
}
/** @type {Map<string, string>} */
const parent = new Map([...patchSet].map((n) => [n, n]));
/**
 * @param {string} n 表名
 * @returns {string} 並查集代表
 */
function find(n) {
  while (parent.get(n) !== n) n = parent.get(n);
  return n;
}
for (const name of patchSet) for (const d of info[name].deps) if (patchSet.has(d)) parent.set(find(name), find(d));
/** @type {Map<string, string[]>} */
const groups = new Map();
for (const name of patchSet) groups.set(find(name), [...(groups.get(find(name)) ?? []), name]);
/** @type {{ label: string, kind: 'group' | 'singles' | 'split-group', tables: string[], bytes: number, requests?: string[][] }[]} */
const groupBatches = [];
/** @type {{ members: string[], bytes: number }[]} */
const splitGroups = [];
/** @type {{ name: string, bytes: number }[]} */
const singles = [];
for (const members of groups.values()) {
  const bytes = members.reduce((sum, n) => sum + info[n].bytes, 0);
  const lackingDeps = members.flatMap((m) => info[m].deps.filter((d) => !members.includes(d)).map((d) => `${m} 依賴 ${d}`));
  if (lackingDeps.length > 0) members.forEach((n) => blocked.push({ name: n, reason: `相依表不在可 patch 範圍（其版本沒有新版）：${lackingDeps.join('、')}` }));
  else if (bytes > maxBytes) splitGroups.push({ members, bytes });
  else if (members.length > 1) groupBatches.push({ label: '', kind: 'group', tables: members, bytes });
  else singles.push({ name: members[0], bytes: info[members[0]].bytes });
}
groupBatches.sort((a, b) => a.bytes - b.bytes).forEach((b, i) => (b.label = `G${i + 1}`));

/**
 * 相依群組合計超過單次請求上限時，拆成多個請求：
 * 「相依表必須同批」只是 npm 指令在產生 body 之前的檢查，產生出來的 patchV2 body 是 data 陣列，可以分次送。
 * 依大小由大到小塞進請求、每個請求不超過上限；只有「單表就超過上限」才真的擋下。
 * 拆開後請求之間 staging 有秒級的版本不一致，執行時改用 send-split.mjs（先用 CHECK_ONLY=1 讓工具檢查整個群組）。
 */
/** @type {typeof groupBatches} */
const splitBatches = [];
for (const [i, g] of splitGroups.entries()) {
  const tooBig = g.members.filter((n) => info[n].bytes > maxBytes);
  if (tooBig.length > 0) {
    g.members.forEach((n) => blocked.push({ name: n, reason: `相依群組超過上限需要拆開，但 ${tooBig.join('、')} 單表就超過單次請求上限 ${(maxBytes / 1e6).toFixed(1)}MB` }));
    continue;
  }
  /** @type {{ tables: string[], bytes: number }[]} */
  const bins = [];
  for (const n of [...g.members].sort((a, b) => info[b].bytes - info[a].bytes)) {
    const bin = bins.find((b) => b.bytes + info[n].bytes <= maxBytes);
    if (bin) {
      bin.tables.push(n);
      bin.bytes += info[n].bytes;
    } else bins.push({ tables: [n], bytes: info[n].bytes });
  }
  splitBatches.push({ label: `X${i + 1}`, kind: 'split-group', tables: g.members, bytes: g.bytes, requests: bins.map((b) => b.tables) });
}

// ============================================================
// Step 5: 無相依的表依大小由大到小塞進批次（每批不超過上限）
// ============================================================
/** @type {{ label: string, kind: 'group' | 'singles', tables: string[], bytes: number }[]} */
const singleBatches = [];
for (const s of singles.sort((a, b) => b.bytes - a.bytes)) {
  if (s.bytes > maxBytes) {
    blocked.push({ name: s.name, reason: `單表 ${(s.bytes / 1e6).toFixed(2)}MB 超過單次請求上限` });
    continue;
  }
  const bin = singleBatches.find((b) => b.bytes + s.bytes <= maxBytes);
  if (bin) {
    bin.tables.push(s.name);
    bin.bytes += s.bytes;
  } else singleBatches.push({ label: `S${singleBatches.length + 1}`, kind: 'singles', tables: [s.name], bytes: s.bytes });
}
const batches = [...groupBatches, ...splitBatches, ...singleBatches];

// ============================================================
// Step 6: 輸出 plan.json 與 Markdown 摘要
// ============================================================
const blockedNames = new Set(blocked.map((b) => b.name));
/** @type {Record<string, number>} */
const expected = {};
for (const b of batches) for (const t of b.tables) expected[t] = info[t].version;
const verifyNames = [...new Set([...batches.flatMap((b) => b.tables), ...blockedNames])];
const verifyFilters = verifyNames.map((n) => ({ bodyConditions: [{ fieldName: 'name', valueType: 'STRING', operator: 'in', string: n }] }));
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'plan.json'), JSON.stringify({ maxBytes, batches, blocked, expected, verifyFilters }, null, 2));

console.log(`## Patch 計畫（單次請求上限 ${(maxBytes / 1e6).toFixed(1)}MB）\n`);
console.log(`- 可 patch：${Object.keys(expected).length} 張，分 ${batches.length} 批；被擋下：${blocked.length} 張\n`);
console.log('| 批次 | 類型 | 表數 | 大小 | 表 |\n|---|---|---|---|---|');
/** @type {Record<string, string>} */
const kindLabel = { group: '相依群組（必須同批）', singles: '無相依', 'split-group': '相依群組超過上限，拆成多個請求' };
for (const b of batches) console.log(`| ${b.label} | ${kindLabel[b.kind]} | ${b.tables.length} | ${(b.bytes / 1e6).toFixed(2)}MB | ${b.tables.join(', ')} |`);
for (const b of batches) if (b.kind === 'split-group') console.log(`\n${b.label} 拆成 ${b.requests.length} 個請求，用 send-split.mjs 送出，--requests 參數：\n\`${b.requests.map((r) => r.join(',')).join('|')}\``);
if (blocked.length > 0) {
  console.log('\n## 被擋下、不會 patch 的表\n\n| 表 | 原因 |\n|---|---|');
  for (const b of blocked) console.log(`| ${b.name} | ${b.reason} |`);
}
const notable = Object.keys(expected).flatMap((n) => {
  const prod = rows.get(n)?.prod;
  const version = info[n].version;
  if (prod === void 0 || version === prod) return [];
  return [`- ${n}：分支 ${version}，production ${prod}（${version > prod ? 'patch 後 staging 會領先 production' : 'patch 後仍落後 production'}）`];
});
if (notable.length > 0) console.log(`\n## 分支版號與 production 不同的表（patch 後不會剛好對齊）\n\n${notable.join('\n')}`);
console.log(`\n計畫已寫入 ${path.join(outDir, 'plan.json')}`);
