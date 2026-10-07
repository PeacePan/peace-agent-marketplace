#!/usr/bin/env python3
"""
合併「門市機台檔／機台版本資訊／裝置推播管理檔」三份清單，產出 Ragdoll 機台稽核報告。

沒有 python3 的環境改用同目錄的 join_report.mjs（Node 版），兩支輸出必須一致；修改邏輯時請兩支一起改，並用同一批資料比對輸出。

為什麼要用腳本：三張表各有數百列，必須以「收銀機編號（5 碼＝門市 3 碼＋機台 2 碼）」逐台對應。
人工在對話裡比對幾百列容易漏列或錯列；腳本做 join 才能保證每一台機台都被檢查到。

輸入檔皆為純文字，每行一筆、欄位以空白或逗號分隔，`#` 開頭為註解（Claude 從 MCP 查詢結果抄寫而來）：
  --configs      機台清單   : <name> [mode]                              例：21112 CASH_REGISTER
  --versions     版本紀錄   : <name> <posVersion> <commitHash> <lastEnterAt>
                                                                       例：21112 1.2.1 f2cd18a39e 2026-10-02T06:53:50.080Z
  --devices      裝置紀錄   : <name> [D]（D＝disabled 為 true）           例：21112
  --devices-fcm  有推播 ID 的裝置紀錄（選用）: <name>                     例：21112
                 省略時視為「所有裝置紀錄都有推播 ID」，只有在 count 比對過兩者列數相等時才能省略。

用法：
  python3 -I join_report.py --configs c.txt --versions v.txt --devices d.txt \\
      [--devices-fcm f.txt] [--stale-days 3] [--now 2026-10-07T07:00:00Z] [--csv out.csv]

輸出：Markdown 報告（stdout）；加 `--csv` 另存每台機台一列的完整明細。
"""
import argparse
import csv
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

cNamePattern = re.compile(r'^\d{5}$')
cVersionPattern = re.compile(r'^\d+\.\d+\.\d+$')
# 目前最高版只有這麼少台時，很可能是測試機或預先發佈版，不應直接當成「正式最新版」。
cFewTopMachines = 2


def parse_time(text):
    """解析 ISO 8601（含毫秒與 Z）時間字串；失敗回傳 None。"""
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).astimezone(timezone.utc)
    except ValueError:
        return None


def round_half_up(value):
    """
    四捨五入到小數 1 位（平手時進位）。刻意不用內建 round()：它是銀行家捨入（17.25 → 17.2），
    與 Node 版的 toFixed 不同；兩支腳本改用同一個演算法，才能保證輸出逐位元一致。
    """
    return math.floor(value * 10 + 0.5) / 10


def version_key(text):
    """把 1.2.10 轉成可比較的 tuple，避免字串排序把 1.2.10 排在 1.2.2 前面。"""
    return tuple(int(part) for part in text.split('.'))


def read_rows(path, min_cols, label, warnings):
    """
    讀取清單檔並回傳欄位陣列；格式不符的行不靜默丟棄，而是記入 warnings，
    讓抄寫錯誤（漏欄、機台編號不是 5 碼）能在報告最前面被看見。
    """
    rows = []
    with open(path, encoding='utf-8') as handle:
        for line_no, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            cols = [col for col in re.split(r'[\s,]+', line) if col]
            if len(cols) < min_cols or not cNamePattern.match(cols[0]):
                warnings.append(f'{label} 第 {line_no} 行格式不符，已略過：{line!r}')
                continue
            rows.append(cols)
    return rows


def main():
    parser = argparse.ArgumentParser(description='Ragdoll 機台版本與推播 ID 稽核')
    parser.add_argument('--configs', required=True)
    parser.add_argument('--versions', required=True)
    parser.add_argument('--devices', required=True)
    parser.add_argument('--devices-fcm')
    parser.add_argument('--stale-days', type=float, default=3.0)
    parser.add_argument('--now')
    parser.add_argument('--csv')
    args = parser.parse_args()

    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        sys.exit('--now 不是合法的 ISO 8601 時間')
    warnings = []

    # ============================================================
    # Step 1: 讀入三份清單並轉成以機台編號為鍵的結構
    # ============================================================
    machines = {}
    for cols in read_rows(args.configs, 1, 'configs', warnings):
        machines[cols[0]] = cols[1] if len(cols) > 1 else '-'

    # 同一台機台每換一個版本就有一列；以 lastEnterAt 最大者為「目前版本」，
    # 因為舊版本的列在升版後就不再被更新，回退（降版）時舊列的 lastEnterAt 會重新變新。
    seen_versions = defaultdict(list)
    for cols in read_rows(args.versions, 4, 'versions', warnings):
        entered = parse_time(cols[3])
        if not cVersionPattern.match(cols[1]) or entered is None:
            warnings.append(f'versions 內容不合法，已略過：{" ".join(cols)!r}')
            continue
        seen_versions[cols[0]].append((entered, cols[1], cols[2]))

    device_rows = Counter()
    disabled_rows = Counter()
    for cols in read_rows(args.devices, 1, 'devices', warnings):
        device_rows[cols[0]] += 1
        if len(cols) > 1 and cols[1].upper() == 'D':
            disabled_rows[cols[0]] += 1

    fcm_names = None
    if args.devices_fcm:
        fcm_names = Counter(cols[0] for cols in read_rows(args.devices_fcm, 1, 'devices-fcm', warnings))

    # ============================================================
    # Step 2: 逐台判定（只對 configs 內的機台，確保清單內每一台都被檢查）
    # ============================================================
    # 「未上報」的切點與查詢時間窗一致：都是「N 天前當天 00:00 UTC」。
    # 若改用精確的 N×24 小時，會出現「在查詢時間窗內、卻被標為未上報」的矛盾。
    cutoff = (now - timedelta(days=args.stale_days)).replace(hour=0, minute=0, second=0, microsecond=0)
    details = []
    for name in sorted(machines):
        entries = sorted(seen_versions.get(name, []), key=lambda e: (e[0], version_key(e[1])), reverse=True)
        latest = entries[0] if entries else None
        highest_seen = max((version_key(e[1]) for e in entries), default=None)
        age_days = (now - latest[0]).total_seconds() / 86400 if latest else None
        rolled_back = bool(latest) and version_key(latest[1]) < highest_seen
        rows = device_rows.get(name, 0)
        if rows == 0:
            push = '無裝置紀錄'
        elif rows - disabled_rows.get(name, 0) == 0:
            push = '裝置已禁用'
        elif fcm_names is not None and fcm_names.get(name, 0) == 0:
            push = '有裝置但無推播ID'
        else:
            push = '已登入'
        details.append({
            'name': name,
            'mode': machines[name],
            'version': latest[1] if latest else '',
            'commit': latest[2] if latest else '',
            'lastEnterAt': latest[0].strftime('%Y-%m-%dT%H:%M:%SZ') if latest else '',
            'ageDays': round_half_up(age_days) if age_days is not None else '',
            'stale': bool(latest) and latest[0] < cutoff,
            'rolledBack': rolled_back,
            'deviceRows': rows,
            'push': push,
        })

    orphan_versions = sorted(set(seen_versions) - set(machines))
    orphan_devices = sorted(set(device_rows) - set(machines))

    # ============================================================
    # Step 3: 輸出報告
    # ============================================================
    total = len(details)
    with_version = [d for d in details if d['version']]
    stale = [d for d in with_version if d['stale']]
    no_version = [d for d in details if not d['version']]
    pushed = [d for d in details if d['push'] == '已登入']
    no_push = [d for d in details if d['push'] != '已登入']
    dup_devices = [d for d in details if d['deviceRows'] > 1]
    rolled = [d for d in details if d['rolledBack']]
    top = max((version_key(d['version']) for d in with_version), default=None)
    top_text = '.'.join(map(str, top)) if top else ''
    behind = [d for d in with_version if version_key(d['version']) < top] if top else []

    def pct(part):
        return f'{round_half_up(part / total * 100):.1f}%' if total else '-'

    out = []
    out.append(f'# Ragdoll 機台稽核報告（資料時間基準 {now.strftime("%Y-%m-%d %H:%M")} UTC）')
    if warnings:
        out.append('\n> ⚠️ 輸入檔有格式問題（請回頭檢查抄寫是否漏列）：')
        out.extend(f'> - {w}' for w in warnings)
    out.append('\n## 1. 總覽\n')
    mode_text = '、'.join(f'{mode} {cnt} 台' for mode, cnt in sorted(Counter(d['mode'] for d in details).items()))
    out.append(f'機型組成：{mode_text}\n')
    out.append('| 項目 | 台數 | 占比 |\n|---|---|---|')
    out.append(f'| 機台清單（ACTIVE） | {total} | 100% |')
    out.append(f'| 有 Ragdoll 版本紀錄 | {len(with_version)} | {pct(len(with_version))} |')
    out.append(f'| 　其中未上報（最後上報早於 {cutoff.strftime("%Y-%m-%d")} UTC） | {len(stale)} | {pct(len(stale))} |')
    out.append(f'| 完全沒有 Ragdoll 版本紀錄 | {len(no_version)} | {pct(len(no_version))} |')
    out.append(f'| 已登入推播 ID | {len(pushed)} | {pct(len(pushed))} |')
    out.append(f'| 未登入推播 ID | {len(no_push)} | {pct(len(no_push))} |')
    out.append(f'| 裝置紀錄重複（同機台 >1 筆） | {len(dup_devices)} | {pct(len(dup_devices))} |')

    out.append('\n## 2. 目前版本分佈（以每台 lastEnterAt 最新的一筆為準；占比分母為機台清單）\n')
    version_count = Counter((d['version'], d['commit']) for d in with_version)
    if version_count:
        out.append('| 版本 | commit | 台數 | 占比 | 備註 |\n|---|---|---|---|---|')
        for (ver, commit), cnt in sorted(version_count.items(), key=lambda kv: (version_key(kv[0][0]), kv[1]), reverse=True):
            note = '目前最高版' if version_key(ver) == top else ''
            out.append(f'| {ver} | {commit} | {cnt} | {pct(cnt)} | {note} |')
        if no_version:
            out.append(f'| （無版本紀錄） | - | {len(no_version)} | {pct(len(no_version))} | |')
        top_count = sum(cnt for (ver, _), cnt in version_count.items() if version_key(ver) == top)
        if top_count <= cFewTopMachines:
            out.append(f'\n> ⚠️ 最高版 {top_text} 只有 {top_count} 台，可能是測試機或預先發佈版；請向使用者確認真正的正式最新版，再重新判讀「落後」。')
    else:
        out.append('（沒有任何版本紀錄）')

    out.append('\n## 3. 需要關注的機台\n')

    def section(title, items, cols, note=None):
        out.append(f'### {title}（{len(items)} 台）\n')
        if not items:
            out.append('無。\n')
            return
        out.append('| ' + ' | '.join(h for h, _ in cols) + ' |')
        out.append('|' + '---|' * len(cols))
        for d in items:
            out.append('| ' + ' | '.join(str(d[k]) for _, k in cols) + ' |')
        if note:
            out.append(f'\n{note}')
        out.append('')

    section('3.1 完全沒有 Ragdoll 版本紀錄', no_version, [('機台', 'name'), ('模式', 'mode'), ('推播', 'push')])

    # 落後清單依版本分組、每組一行：機台數多時表格會很長，分組後仍能完整列出而不佔篇幅。
    out.append(f'### 3.2 落後目前最高版 {top_text} 的機台（{len(behind)} 台，依版本分組）\n')
    if not behind:
        out.append('無。\n')
    else:
        grouped = defaultdict(list)
        for d in behind:
            grouped[d['version']].append(d)
        for ver in sorted(grouped, key=version_key, reverse=True):
            names = '、'.join(
                f'{d["name"]}（{d["ageDays"]} 天前最後上報）' if d['stale'] else d['name']
                for d in grouped[ver]
            )
            out.append(f'- **{ver}**（{len(grouped[ver])} 台）：{names}')
        out.append('')

    section(f'3.3 未上報（最後上報早於 {cutoff.strftime("%Y-%m-%d")} UTC）', sorted(stale, key=lambda d: -d['ageDays']),
            [('機台', 'name'), ('模式', 'mode'), ('版本', 'version'), ('最後上報', 'lastEnterAt'), ('距今天數', 'ageDays')],
            '這些機台的「版本」是它最後一次上報 Ragdoll 時的版本，現況可能已不同（關機、換機或改跑其他平台）。')
    overlap = len([d for d in no_push if not d['version']])
    section('3.4 未登入推播 ID', no_push, [('機台', 'name'), ('模式', 'mode'), ('狀況', 'push'), ('版本', 'version')],
            f'其中 {overlap} 台同時沒有版本紀錄（見 3.1），通常是尚未安裝或尚未啟用 Ragdoll。' if overlap else None)
    section('3.5 疑似降版（目前版本低於時間窗內出現過的更高版本）', rolled,
            [('機台', 'name'), ('目前版本', 'version'), ('最後上報', 'lastEnterAt')])
    section('3.6 裝置紀錄重複', dup_devices, [('機台', 'name'), ('裝置紀錄筆數', 'deviceRows')],
            '同一台機台有多筆裝置紀錄（常見於換機後舊紀錄未清），不影響「有沒有登入」的判定，但推播會重複送到舊裝置。')

    out.append('### 3.7 不在機台清單內卻仍有資料\n')
    out.append('通常是已停用（INACTIVE）或已封存的機台；若是 INACTIVE 卻仍在上報版本，請確認 `posconfig.status` 是否設錯。\n')
    out.append(f'- 有版本上報：{len(orphan_versions)} 台' + (f'（{", ".join(orphan_versions[:20])}{" …" if len(orphan_versions) > 20 else ""}）' if orphan_versions else ''))
    out.append(f'- 有裝置紀錄：{len(orphan_devices)} 台' + (f'（{", ".join(orphan_devices[:20])}{" …" if len(orphan_devices) > 20 else ""}）' if orphan_devices else ''))

    if no_version:
        out.append('\n## 4. 補查版本用的正規式\n')
        out.append('把下列字串貼進 `posversionhash` 查詢的 `configName like`，並放寬 `lastEnterAt` 時間窗：\n')
        out.append('`^(' + '|'.join(d['name'] for d in no_version) + ')$`')

    print('\n'.join(out))

    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(details[0].keys()) if details else ['name'])
            writer.writeheader()
            for d in details:
                writer.writerow({k: str(v).lower() if isinstance(v, bool) else v for k, v in d.items()})


if __name__ == '__main__':
    main()
