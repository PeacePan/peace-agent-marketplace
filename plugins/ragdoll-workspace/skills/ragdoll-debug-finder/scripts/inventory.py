#!/usr/bin/env python3
"""Ragdoll 門市問題回報包盤點。

用途：解壓回報包（issue-report-*.tar.gz）後先跑一次，快速取得回報基本資料、門市原話、回報包完整度、
兩個 SQLite 快照有資料的表與最新寫入時間、各日誌範圍在回報時間點前後的 warn／error。
根因分析仍須人工閱讀原始檔，本腳本只負責「先看哪裡」。

設計原則：
- 唯讀。SQLite 以 mode=ro 開啟；不執行任何來自資料的內容。
- 只印表名、筆數、時間與被截斷的 warn／error 日誌行，不輸出表格內容（避免會員個資進入對話）。
- 僅用標準庫，Python 3.9+。建議以 `python3 -I` 執行（資料來自不可信的下載檔）。

用法：
    python3 -I inventory.py <回報包解壓目錄> [--window 分鐘數]

--window：日誌只列「回報開啟時間 - N 分鐘」到「送出時間 + 2 分鐘」之間的 warn／error，預設 30。
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ_TW = timezone(timedelta(hours=8))
LOG_LINE = re.compile(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(\w+)\]\s?(.*)$')
LOG_LEVELS_OF_INTEREST = ('warn', 'error')
MAX_LOG_LINES_PER_SCOPE = 8
MAX_LOG_LINE_CHARS = 180
# 回報包的固定檔案；缺任何一個都表示收集不完整（collectErrors 通常會同步記錄原因）
EXPECTED_FILES = [
    'metadata.json', 'description.txt', 'config.ini', 'ragdoll-store.json',
    'screenshot.png', 'storeSnapshot.json',
    'offline-mutable.snapshot.db', 'offline-readonly.snapshot.db',
]
# ragdoll-store.json 只摘錄診斷常用的鍵，其餘不印
STORE_KEYS = ['POS_STORE_NAME', 'POS_CONFIG_NAME', 'CREDIT_CARD_READER_TYPE', 'CHECKOUT_SUSPENSION']


def section(title: str) -> None:
    print(f'\n== {title} ==')


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def to_tw(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(TZ_TW)


def fmt(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def show_meta(root: Path):
    """回報基本資料與門市原話；回傳 (開啟時間, 送出時間)，供日誌篩選使用。"""
    section('回報基本資料')
    meta = read_json(root / 'metadata.json')
    if not isinstance(meta, dict):
        print('metadata.json 讀不到或格式錯誤：無法確認回報時間點，日誌區段將略過')
        return None, None
    saler = meta.get('saler') or {}
    captured = to_tw(meta['capturedAt']) if meta.get('capturedAt') else None
    submitted = to_tw(meta['submittedAt']) if meta.get('submittedAt') else None
    print(f"代碼(eventId 前 8 碼)：{str(meta.get('eventId', ''))[:8]}（完整：{meta.get('eventId')}）")
    print(f"環境：{meta.get('targetEnv')}　版本：{meta.get('posVersion')}　門市：{meta.get('storeName')}　機台：{meta.get('configName')}")
    print(f"回報人：{saler.get('name')} {saler.get('displayName')}")
    print(f"開啟回報(截圖)時間：{fmt(captured) if captured else '?'}（台灣時間）")
    print(f"送出時間：{fmt(submitted) if submitted else '?'}（台灣時間）")
    print(f"collectErrors：{meta.get('collectErrors') or '無'}")
    desc = root / 'description.txt'
    print('門市原話：' + (desc.read_text(encoding='utf-8', errors='replace').strip() if desc.exists() else '（缺 description.txt）'))
    return captured, submitted


def show_files(root: Path) -> None:
    section('回報包完整度')
    for name in EXPECTED_FILES:
        p = root / name
        print(f"{'✓' if p.exists() else '✗'} {name}" + (f'（{p.stat().st_size:,} bytes）' if p.exists() else '（缺）'))
    print(f"{'✓' if (root / 'ecr').is_dir() else '－'} ecr/（只有執行過台新刷卡的機台才會有）")
    store = read_json(root / 'ragdoll-store.json')
    if isinstance(store, dict):
        print('ragdoll-store.json：' + '、'.join(f'{k}={store.get(k)}' for k in STORE_KEYS if k in store))


def show_db(path: Path, compact: bool = False) -> None:
    """列出有資料的表、筆數與最新 created_at（毫秒時間戳，換算台灣時間）。

    compact=True 時只印一行「表名(筆數)」摘要，用於同步下來的唯讀主檔（表多、逐表時間對診斷幫助小）。
    """
    section(f'SQLite：{path.name}')
    if not path.exists():
        print('（缺檔）')
        return
    try:
        con = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)
    except sqlite3.Error as e:
        print(f'開啟失敗：{e}')
        return
    try:
        tables = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' and name not like '\\_\\_%' escape '\\' order by name")]
        shown = 0
        summary = []
        for t in tables:
            cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
            n = con.execute(f'select count(*) from "{t}"').fetchone()[0]
            if n == 0:
                continue
            shown += 1
            if compact:
                summary.append(f'{t}({n:,})')
                continue
            latest = ''
            if 'created_at' in cols:
                v = con.execute(f'select max(created_at) from "{t}"').fetchone()[0]
                if isinstance(v, (int, float)) and v > 0:
                    latest = f'　最新 created_at={fmt(datetime.fromtimestamp(v / 1000, TZ_TW))}'
            print(f'{t}: {n:,} 筆{latest}')
        if compact:
            print('有資料的表：' + '、'.join(summary))
        print(f'（共 {len(tables)} 張表，{shown} 張有資料；空表不列）')
    except sqlite3.Error as e:
        print(f'查詢失敗：{e}')
    finally:
        con.close()


def show_logs(root: Path, captured, submitted, window_min: int) -> None:
    """各日誌範圍的 warn／error 統計，以及回報時間點前後的 warn／error 行。"""
    section('日誌（logs/<範圍>/<日期>.log，時間為機台本地時間＝台灣時間）')
    logs = root / 'logs'
    if not logs.is_dir():
        print('（缺 logs/）')
        return
    start = (captured - timedelta(minutes=window_min)) if captured else None
    end = (submitted + timedelta(minutes=2)) if submitted else None
    for scope in sorted(p for p in logs.iterdir() if p.is_dir()):
        files = sorted(scope.glob('*.log'))
        total = flagged = 0
        near = []
        for f in files:
            for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
                total += 1
                m = LOG_LINE.match(line)
                if not m or m.group(2).lower() not in LOG_LEVELS_OF_INTEREST:
                    continue
                flagged += 1
                ts = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ_TW)
                if start and end and start <= ts <= end:
                    near.append(line[:MAX_LOG_LINE_CHARS])
        days = f'{files[0].stem}～{files[-1].stem}' if files else '無檔'
        print(f'[{scope.name}] {len(files)} 天（{days}）共 {total:,} 行，warn/error {flagged} 行，回報時間點前後 {len(near)} 行')
        for line in near[-MAX_LOG_LINES_PER_SCOPE:]:
            print(f'    {line}')


def main() -> int:
    ap = argparse.ArgumentParser(description='Ragdoll 門市問題回報包盤點（唯讀）')
    ap.add_argument('root', help='回報包解壓後的目錄')
    ap.add_argument('--window', type=int, default=30, help='日誌往前看幾分鐘（預設 30）')
    args = ap.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        print(f'找不到目錄：{root}', file=sys.stderr)
        return 2
    captured, submitted = show_meta(root)
    show_files(root)
    show_db(root / 'offline-mutable.snapshot.db')
    show_db(root / 'offline-readonly.snapshot.db', compact=True)
    show_logs(root, captured, submitted, args.window)
    return 0


if __name__ == '__main__':
    sys.exit(main())
