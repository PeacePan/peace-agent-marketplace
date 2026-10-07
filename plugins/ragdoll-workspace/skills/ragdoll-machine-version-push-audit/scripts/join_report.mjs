#!/usr/bin/env node
/**
 * 合併「門市機台檔／機台版本資訊／裝置推播管理檔」三份清單，產出 Ragdoll 機台稽核報告。
 *
 * 這是 join_report.py 的 Node 版，供沒有安裝 python3 的環境使用，兩支的輸出必須一致；
 * 修改邏輯時請兩支一起改，並用同一批資料比對輸出。需要 Node 18 以上，不依賴任何套件。
 *
 * 為什麼要用腳本：三張表各有數百列，必須以「收銀機編號（5 碼＝門市 3 碼＋機台 2 碼）」逐台對應。
 * 人工在對話裡比對幾百列容易漏列或錯列；腳本做 join 才能保證每一台機台都被檢查到。
 *
 * 輸入檔皆為純文字，每行一筆、欄位以空白或逗號分隔，`#` 開頭為註解（Claude 從 MCP 查詢結果抄寫而來）：
 *   --configs      機台清單   : <name> [mode]                              例：21112 CASH_REGISTER
 *   --versions     版本紀錄   : <name> <posVersion> <commitHash> <lastEnterAt>
 *                                                                        例：21112 1.2.1 f2cd18a39e 2026-10-02T06:53:50.080Z
 *   --devices      裝置紀錄   : <name> [D]（D＝disabled 為 true）           例：21112
 *   --devices-fcm  有推播 ID 的裝置紀錄（選用）: <name>                     例：21112
 *                  省略時視為「所有裝置紀錄都有推播 ID」，只有在 count 比對過兩者列數相等時才能省略。
 *
 * 用法：
 *   node join_report.mjs --configs c.txt --versions v.txt --devices d.txt \
 *       [--devices-fcm f.txt] [--stale-days 3] [--now 2026-10-07T07:00:00Z] [--csv out.csv]
 *
 * 輸出：Markdown 報告（stdout）；加 `--csv` 另存每台機台一列的完整明細。
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';

/** 機台編號（收銀機編號）：門市 3 碼＋機台 2 碼。 */
const cNamePattern = /^\d{5}$/;
/** 版本號：major.minor.patch。 */
const cVersionPattern = /^\d+\.\d+\.\d+$/;
/** ISO 8601 日期時間，必須帶時區（Z 或 ±hh:mm），避免被誤當成本機時間。 */
const cIsoTimePattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;
/** 目前最高版只有這麼少台時，很可能是測試機或預先發佈版，不應直接當成「正式最新版」。 */
const cFewTopMachines = 2;
const cDayMs = 86400000;
/** CSV 欄位順序，與 join_report.py 一致。 */
const cCsvColumns = ['name', 'mode', 'version', 'commit', 'lastEnterAt', 'ageDays', 'stale', 'rolledBack', 'deviceRows', 'push'];

/**
 * @typedef {Object} VersionEntry 某台機台的一筆版本紀錄
 * @property {Date} entered 最後進入時間
 * @property {string} version 版本號
 * @property {string} commit commitHash
 */

/**
 * @typedef {Object} MachineDetail 單台機台的判定結果
 * @property {string} name 收銀機編號
 * @property {string} mode 機台模式
 * @property {string} version 目前版本（無紀錄為空字串）
 * @property {string} commit 目前版本的 commitHash
 * @property {string} lastEnterAt 最後上報時間（ISO，無紀錄為空字串）
 * @property {number | null} ageDays 距今天數（無紀錄為 null）
 * @property {boolean} stale 是否早於「未上報」切點
 * @property {boolean} rolledBack 是否疑似降版
 * @property {number} deviceRows 裝置紀錄筆數
 * @property {string} push 推播登錄狀況
 */

/**
 * 四捨五入到小數 1 位（平手時進位）。
 * 與 join_report.py 的 round_half_up 同一演算法：Python 內建 round() 是銀行家捨入，
 * 與 toFixed 在平手時結果不同，兩支腳本改用同一個演算法才能保證輸出一致。
 */
function roundOneDecimal(value) {
  return Math.floor(value * 10 + 0.5) / 10;
}

/** 解析 ISO 8601 時間字串；格式不合法回傳 null。 */
function parseTime(text) {
  if (!cIsoTimePattern.test(text)) return null;
  const time = new Date(text);
  return Number.isNaN(time.getTime()) ? null : time;
}

/** 把 1.2.10 轉成數字陣列，避免字串排序把 1.2.10 排在 1.2.2 前面。 */
function versionKey(text) {
  return text.split('.').map(Number);
}

/** 版本比較：回傳負數代表 a 較舊、正數代表 a 較新。 */
function compareVersions(a, b) {
  for (let index = 0; index < Math.max(a.length, b.length); index++) {
    const diff = (a[index] ?? 0) - (b[index] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

/** 格式化為 `2026-10-07T06:55:14Z`（不含毫秒）。 */
function formatIsoSeconds(time) {
  return time.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/** 天數固定顯示一位小數，與 Python 版一致（例如 5 顯示為 5.0）。 */
function formatAge(ageDays) {
  return ageDays === null ? '' : ageDays.toFixed(1);
}

/** CSV 欄位跳脫：含逗號、雙引號或換行時加引號。 */
function csvCell(value) {
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * 讀取清單檔並回傳欄位陣列。
 * 格式不符的行不靜默丟棄，而是記入 warnings，讓抄寫錯誤（漏欄、機台編號不是 5 碼）
 * 能在報告最前面被看見。
 * @param {string} path 檔案路徑
 * @param {number} minCols 每行最少欄位數
 * @param {string} label 警告訊息用的檔案標籤
 * @param {string[]} warnings 警告收集陣列
 * @returns {string[][]}
 */
function readRows(path, minCols, label, warnings) {
  /** @type {string[][]} */
  const rows = [];
  readFileSync(path, 'utf8').split('\n').forEach((raw, index) => {
    const line = raw.trim();
    if (!line || line.startsWith('#')) return;
    const cols = line.split(/[\s,]+/).filter(Boolean);
    if (cols.length < minCols || !cNamePattern.test(cols[0])) {
      warnings.push(`${label} 第 ${index + 1} 行格式不符，已略過：'${line}'`);
      return;
    }
    rows.push(cols);
  });
  return rows;
}

/** 計數：回傳 Map<鍵, 次數>。 */
function countBy(items, getKey) {
  /** @type {Map<string, number>} */
  const counter = new Map();
  for (const item of items) {
    const key = getKey(item);
    counter.set(key, (counter.get(key) ?? 0) + 1);
  }
  return counter;
}

function main() {
  const { values } = parseArgs({
    options: {
      configs: { type: 'string' },
      versions: { type: 'string' },
      devices: { type: 'string' },
      'devices-fcm': { type: 'string' },
      'stale-days': { type: 'string', default: '3' },
      now: { type: 'string' },
      csv: { type: 'string' },
      help: { type: 'boolean', short: 'h' },
    },
  });
  if (values.help || !values.configs || !values.versions || !values.devices) {
    process.stderr.write('用法：node join_report.mjs --configs C --versions V --devices D [--devices-fcm F] [--stale-days 3] [--now ISO] [--csv OUT]\n');
    process.exit(values.help ? 0 : 2);
  }
  const staleDays = Number(values['stale-days']);
  if (!Number.isFinite(staleDays)) {
    process.stderr.write('--stale-days 必須是數字\n');
    process.exit(2);
  }
  const now = values.now ? parseTime(values.now) : new Date();
  if (now === null) {
    process.stderr.write('--now 不是合法的 ISO 8601 時間\n');
    process.exit(1);
  }
  /** @type {string[]} */
  const warnings = [];

  /**
   * ============================================================
   * Step 1: 讀入三份清單並轉成以機台編號為鍵的結構
   * ============================================================
   * 同一台機台每換一個版本就有一列；以 lastEnterAt 最大者為「目前版本」，
   * 因為舊版本的列在升版後就不再被更新，回退（降版）時舊列的 lastEnterAt 會重新變新。
   */
  /** @type {Map<string, string>} */
  const machines = new Map();
  for (const cols of readRows(values.configs, 1, 'configs', warnings)) machines.set(cols[0], cols[1] ?? '-');

  /** @type {Map<string, VersionEntry[]>} */
  const seenVersions = new Map();
  for (const cols of readRows(values.versions, 4, 'versions', warnings)) {
    const entered = parseTime(cols[3]);
    if (!cVersionPattern.test(cols[1]) || entered === null) {
      warnings.push(`versions 內容不合法，已略過：'${cols.join(' ')}'`);
      continue;
    }
    if (!seenVersions.has(cols[0])) seenVersions.set(cols[0], []);
    seenVersions.get(cols[0]).push({ entered, version: cols[1], commit: cols[2] });
  }

  /** @type {Map<string, number>} */
  const deviceRows = new Map();
  /** @type {Map<string, number>} */
  const disabledRows = new Map();
  for (const cols of readRows(values.devices, 1, 'devices', warnings)) {
    deviceRows.set(cols[0], (deviceRows.get(cols[0]) ?? 0) + 1);
    if (cols.length > 1 && cols[1].toUpperCase() === 'D') disabledRows.set(cols[0], (disabledRows.get(cols[0]) ?? 0) + 1);
  }

  /** @type {Map<string, number> | null} */
  const fcmNames = values['devices-fcm']
    ? countBy(readRows(values['devices-fcm'], 1, 'devices-fcm', warnings), (cols) => cols[0])
    : null;

  /**
   * ============================================================
   * Step 2: 逐台判定（只對 configs 內的機台，確保清單內每一台都被檢查）
   * ============================================================
   * 「未上報」的切點與查詢時間窗一致：都是「N 天前當天 00:00 UTC」。
   * 若改用精確的 N×24 小時，會出現「在查詢時間窗內、卻被標為未上報」的矛盾。
   */
  const cutoff = new Date(now.getTime() - staleDays * cDayMs);
  cutoff.setUTCHours(0, 0, 0, 0);
  /** @type {MachineDetail[]} */
  const details = [];
  for (const name of [...machines.keys()].sort()) {
    const entries = [...(seenVersions.get(name) ?? [])].sort(
      (a, b) => (b.entered.getTime() - a.entered.getTime()) || compareVersions(versionKey(b.version), versionKey(a.version)),
    );
    const latest = entries[0] ?? void 0;
    const highestSeen = entries.map((entry) => versionKey(entry.version)).sort(compareVersions).at(-1);
    const rows = deviceRows.get(name) ?? 0;
    /** @type {string} */
    let push;
    if (rows === 0) push = '無裝置紀錄';
    else if (rows - (disabledRows.get(name) ?? 0) === 0) push = '裝置已禁用';
    else if (fcmNames !== null && (fcmNames.get(name) ?? 0) === 0) push = '有裝置但無推播ID';
    else push = '已登入';
    details.push({
      name,
      mode: machines.get(name),
      version: latest?.version ?? '',
      commit: latest?.commit ?? '',
      lastEnterAt: latest ? formatIsoSeconds(latest.entered) : '',
      ageDays: latest ? roundOneDecimal((now.getTime() - latest.entered.getTime()) / cDayMs) : null,
      stale: Boolean(latest) && latest.entered < cutoff,
      rolledBack: Boolean(latest) && compareVersions(versionKey(latest.version), highestSeen) < 0,
      deviceRows: rows,
      push,
    });
  }

  const orphanVersions = [...seenVersions.keys()].filter((name) => !machines.has(name)).sort();
  const orphanDevices = [...deviceRows.keys()].filter((name) => !machines.has(name)).sort();

  /**
   * ============================================================
   * Step 3: 輸出報告
   * ============================================================
   */
  const total = details.length;
  const withVersion = details.filter((d) => d.version);
  const stale = withVersion.filter((d) => d.stale);
  const noVersion = details.filter((d) => !d.version);
  const pushed = details.filter((d) => d.push === '已登入');
  const noPush = details.filter((d) => d.push !== '已登入');
  const dupDevices = details.filter((d) => d.deviceRows > 1);
  const rolled = details.filter((d) => d.rolledBack);
  const top = withVersion.map((d) => versionKey(d.version)).sort(compareVersions).at(-1) ?? void 0;
  const topText = top ? top.join('.') : '';
  const behind = top ? withVersion.filter((d) => compareVersions(versionKey(d.version), top) < 0) : [];
  const pct = (part) => (total ? `${roundOneDecimal((part / total) * 100).toFixed(1)}%` : '-');
  const display = (d, key) => (key === 'ageDays' ? formatAge(d.ageDays) : String(d[key]));
  const cutoffDate = cutoff.toISOString().slice(0, 10);
  const listOrphans = (names) => (names.length ? `（${names.slice(0, 20).join(', ')}${names.length > 20 ? ' …' : ''}）` : '');

  /** @type {string[]} */
  const out = [];
  out.push(`# Ragdoll 機台稽核報告（資料時間基準 ${now.toISOString().slice(0, 16).replace('T', ' ')} UTC）`);
  if (warnings.length) {
    out.push('\n> ⚠️ 輸入檔有格式問題（請回頭檢查抄寫是否漏列）：');
    out.push(...warnings.map((w) => `> - ${w}`));
  }
  out.push('\n## 1. 總覽\n');
  const modeText = [...countBy(details, (d) => d.mode).entries()]
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    .map(([mode, cnt]) => `${mode} ${cnt} 台`)
    .join('、');
  out.push(`機型組成：${modeText}\n`);
  out.push('| 項目 | 台數 | 占比 |\n|---|---|---|');
  out.push(`| 機台清單（ACTIVE） | ${total} | 100% |`);
  out.push(`| 有 Ragdoll 版本紀錄 | ${withVersion.length} | ${pct(withVersion.length)} |`);
  out.push(`| 　其中未上報（最後上報早於 ${cutoffDate} UTC） | ${stale.length} | ${pct(stale.length)} |`);
  out.push(`| 完全沒有 Ragdoll 版本紀錄 | ${noVersion.length} | ${pct(noVersion.length)} |`);
  out.push(`| 已登入推播 ID | ${pushed.length} | ${pct(pushed.length)} |`);
  out.push(`| 未登入推播 ID | ${noPush.length} | ${pct(noPush.length)} |`);
  out.push(`| 裝置紀錄重複（同機台 >1 筆） | ${dupDevices.length} | ${pct(dupDevices.length)} |`);

  out.push('\n## 2. 目前版本分佈（以每台 lastEnterAt 最新的一筆為準；占比分母為機台清單）\n');
  /** @type {Map<string, {version: string, commit: string, cnt: number}>} */
  const versionCount = new Map();
  for (const d of withVersion) {
    const key = `${d.version} ${d.commit}`;
    const group = versionCount.get(key) ?? { version: d.version, commit: d.commit, cnt: 0 };
    group.cnt++;
    versionCount.set(key, group);
  }
  if (versionCount.size) {
    out.push('| 版本 | commit | 台數 | 占比 | 備註 |\n|---|---|---|---|---|');
    const groups = [...versionCount.values()].sort((a, b) => compareVersions(versionKey(b.version), versionKey(a.version)) || b.cnt - a.cnt);
    for (const { version, commit, cnt } of groups) {
      const note = compareVersions(versionKey(version), top) === 0 ? '目前最高版' : '';
      out.push(`| ${version} | ${commit} | ${cnt} | ${pct(cnt)} | ${note} |`);
    }
    if (noVersion.length) out.push(`| （無版本紀錄） | - | ${noVersion.length} | ${pct(noVersion.length)} | |`);
    const topCount = groups.filter((g) => compareVersions(versionKey(g.version), top) === 0).reduce((sum, g) => sum + g.cnt, 0);
    if (topCount <= cFewTopMachines) {
      out.push(`\n> ⚠️ 最高版 ${topText} 只有 ${topCount} 台，可能是測試機或預先發佈版；請向使用者確認真正的正式最新版，再重新判讀「落後」。`);
    }
  } else {
    out.push('（沒有任何版本紀錄）');
  }

  out.push('\n## 3. 需要關注的機台\n');

  /**
   * 輸出一個「標題＋表格＋備註」區段；沒有項目時只寫「無。」。
   * @param {string} title
   * @param {MachineDetail[]} items
   * @param {Array<[string, string]>} cols 表頭與欄位鍵
   * @param {string} [note] 表格後的備註
   */
  function section(title, items, cols, note) {
    out.push(`### ${title}（${items.length} 台）\n`);
    if (!items.length) {
      out.push('無。\n');
      return;
    }
    out.push(`| ${cols.map(([header]) => header).join(' | ')} |`);
    out.push(`|${'---|'.repeat(cols.length)}`);
    for (const d of items) out.push(`| ${cols.map(([, key]) => display(d, key)).join(' | ')} |`);
    if (note) out.push(`\n${note}`);
    out.push('');
  }

  section('3.1 完全沒有 Ragdoll 版本紀錄', noVersion, [['機台', 'name'], ['模式', 'mode'], ['推播', 'push']]);

  /** 落後清單依版本分組、每組一行：機台數多時表格會很長，分組後仍能完整列出而不佔篇幅。 */
  out.push(`### 3.2 落後目前最高版 ${topText} 的機台（${behind.length} 台，依版本分組）\n`);
  if (!behind.length) {
    out.push('無。\n');
  } else {
    /** @type {Map<string, MachineDetail[]>} */
    const grouped = new Map();
    for (const d of behind) {
      if (!grouped.has(d.version)) grouped.set(d.version, []);
      grouped.get(d.version).push(d);
    }
    for (const version of [...grouped.keys()].sort((a, b) => compareVersions(versionKey(b), versionKey(a)))) {
      const names = grouped.get(version).map((d) => (d.stale ? `${d.name}（${formatAge(d.ageDays)} 天前最後上報）` : d.name)).join('、');
      out.push(`- **${version}**（${grouped.get(version).length} 台）：${names}`);
    }
    out.push('');
  }

  section(`3.3 未上報（最後上報早於 ${cutoffDate} UTC）`, [...stale].sort((a, b) => b.ageDays - a.ageDays),
    [['機台', 'name'], ['模式', 'mode'], ['版本', 'version'], ['最後上報', 'lastEnterAt'], ['距今天數', 'ageDays']],
    '這些機台的「版本」是它最後一次上報 Ragdoll 時的版本，現況可能已不同（關機、換機或改跑其他平台）。');
  const overlap = noPush.filter((d) => !d.version).length;
  section('3.4 未登入推播 ID', noPush, [['機台', 'name'], ['模式', 'mode'], ['狀況', 'push'], ['版本', 'version']],
    overlap ? `其中 ${overlap} 台同時沒有版本紀錄（見 3.1），通常是尚未安裝或尚未啟用 Ragdoll。` : void 0);
  section('3.5 疑似降版（目前版本低於時間窗內出現過的更高版本）', rolled,
    [['機台', 'name'], ['目前版本', 'version'], ['最後上報', 'lastEnterAt']]);
  section('3.6 裝置紀錄重複', dupDevices, [['機台', 'name'], ['裝置紀錄筆數', 'deviceRows']],
    '同一台機台有多筆裝置紀錄（常見於換機後舊紀錄未清），不影響「有沒有登入」的判定，但推播會重複送到舊裝置。');

  out.push('### 3.7 不在機台清單內卻仍有資料\n');
  out.push('通常是已停用（INACTIVE）或已封存的機台；若是 INACTIVE 卻仍在上報版本，請確認 `posconfig.status` 是否設錯。\n');
  out.push(`- 有版本上報：${orphanVersions.length} 台${listOrphans(orphanVersions)}`);
  out.push(`- 有裝置紀錄：${orphanDevices.length} 台${listOrphans(orphanDevices)}`);

  if (noVersion.length) {
    out.push('\n## 4. 補查版本用的正規式\n');
    out.push('把下列字串貼進 `posversionhash` 查詢的 `configName like`，並放寬 `lastEnterAt` 時間窗：\n');
    out.push(`\`^(${noVersion.map((d) => d.name).join('|')})$\``);
  }

  console.log(out.join('\n'));

  if (values.csv) {
    const header = details.length ? cCsvColumns : ['name'];
    const lines = [header.join(',')];
    for (const d of details) lines.push(header.map((key) => csvCell(key === 'ageDays' ? formatAge(d.ageDays) : d[key])).join(','));
    writeFileSync(values.csv, `﻿${lines.join('\r\n')}\r\n`, 'utf8');
  }
}

main();
