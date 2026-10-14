#!/usr/bin/env python3
"""列出在指定時間範圍內「真的有訊息」的 Claude Code 對話紀錄，供整理當日工作使用。

為什麼不看檔案修改時間：同步、續接、批次觸碰都會改動 mtime，但那天沒有任何互動；
只有訊息本身的 timestamp 才能證明那個 session 在範圍內做過事。

用法：
    python3 sessions_in_range.py --start 2026-10-12T00:00:00+08:00 --end 2026-10-13T00:00:00+08:00
    python3 sessions_in_range.py --start ... --end ... --projects-dir ~/.claude-peace/projects

輸出每個 session：專案、範圍內訊息數、起訖時間、提及最多的卡號、範圍內的使用者提問（前幾則）、
`result:` 結論行（取最後幾行）與最後一則回覆。
subagent 的紀錄不列入（只看使用者實際對話的主 session）。

注意：不要用 --exclude-session 排除「目前的 session」。範圍內有訊息的才會列出，今天下指令的訊息不在範圍內；
但 /clear 之後的 session 編號不變，昨天的工作可能就在同一個 session 裡，排除會漏報。
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TS_PATTERN = re.compile(r'"timestamp":"([^"]+)"')
CARD_PATTERN = re.compile(r'RD-\d+')


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return '\n'.join(c.get('text', '') for c in (content or []) if isinstance(c, dict) and c.get('type') == 'text')


def to_utc_key(iso: str) -> str:
    """轉成 UTC 的 'YYYY-MM-DDTHH:MM:SS' 字串，方便不解析 JSON 就直接字串比較。"""
    parsed = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    return parsed.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')


def default_projects_dir() -> Path:
    config_dir = os.environ.get('CLAUDE_CONFIG_DIR')
    if config_dir:
        return Path(config_dir).expanduser() / 'projects'
    return Path.home() / '.claude' / 'projects'


def project_label(directory: str) -> str:
    return re.sub(r'^-Users-[^-]+-workspace-', '', directory) or directory


def scan(path: Path, start_key: str, end_key: str, local_tz):
    in_range = 0
    first = last = None
    prompts = []
    last_reply = None
    conclusions = []
    cards = Counter()
    with path.open('r', errors='replace') as handle:
        for line in handle:
            # 先用正則快速篩出「任一 timestamp 落在範圍內」的候選行，避免每行都解析 JSON
            if not any(start_key <= stamp[:19] < end_key for stamp in TS_PATTERN.findall(line)):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            # 檔案快照等紀錄的 timestamp 在巢狀欄位，最上層沒有就不算一筆訊息
            top_level = record.get('timestamp')
            if not isinstance(top_level, str) or not (start_key <= to_utc_key(top_level) < end_key):
                continue
            in_range += 1
            moment = datetime.fromisoformat(top_level.replace('Z', '+00:00')).astimezone(local_tz)
            first = first or moment
            last = moment
            if record.get('isSidechain'):
                continue
            kind = record.get('type')
            if kind == 'user' and not record.get('isMeta'):
                text = text_of(record.get('message', {}).get('content')).strip()
                if text and not text.startswith('<'):
                    cards.update(CARD_PATTERN.findall(text))
                    if len(prompts) < 5:
                        prompts.append(f"{moment:%H:%M} {text[:110]}".replace('\n', ' '))
            elif kind == 'assistant':
                text = text_of(record.get('message', {}).get('content')).strip()
                if text:
                    last_reply = text
                    cards.update(CARD_PATTERN.findall(text))
                    # 背景工作習慣以 result: 開頭的一行收尾，驗收結果、根因等結論多半在這裡；
                    # 最後一則回覆常只剩清理作業，結論要從每一次的 result: 行找
                    conclusions.extend(f'{moment:%H:%M} {line.strip()}' for line in text.splitlines() if line.startswith('result:'))
    return in_range, first, last, prompts, last_reply, conclusions, cards


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', required=True, help='範圍起點（含），ISO 8601，需帶時區')
    parser.add_argument('--end', required=True, help='範圍終點（不含），ISO 8601，需帶時區')
    parser.add_argument('--projects-dir', help='對話紀錄目錄，預設 $CLAUDE_CONFIG_DIR/projects 或 ~/.claude/projects')
    parser.add_argument('--exclude-session', action='append', default=[], help='要排除的 session id（前綴即可），可重複')
    parser.add_argument('--reply-chars', type=int, default=400, help='最後一則回覆最多印幾個字')
    parser.add_argument('--result-lines', type=int, default=4, help='每個 session 最多印幾行 result: 結論（取最後幾行）')
    parser.add_argument('--result-chars', type=int, default=260, help='每行 result: 結論最多印幾個字')
    args = parser.parse_args()

    projects_dir = Path(args.projects_dir).expanduser() if args.projects_dir else default_projects_dir()
    if not projects_dir.is_dir():
        sys.exit(f'找不到對話紀錄目錄：{projects_dir}')

    start_dt = datetime.fromisoformat(args.start)
    local_tz = start_dt.tzinfo or timezone.utc
    start_key, end_key = to_utc_key(args.start), to_utc_key(args.end)
    start_epoch = start_dt.timestamp()

    results = []
    for path in projects_dir.glob('*/*.jsonl'):
        if any(path.stem.startswith(prefix) for prefix in args.exclude_session):
            continue
        # 範圍內有訊息的檔案，最後寫入時間一定不早於範圍起點，先用 mtime 快速排除舊檔
        if path.stat().st_mtime < start_epoch:
            continue
        in_range, first, last, prompts, last_reply, conclusions, cards = scan(path, start_key, end_key, local_tz)
        if in_range:
            results.append((first, path, in_range, last, prompts, last_reply, conclusions, cards))

    results.sort(key=lambda item: item[0])
    print(f'範圍 {args.start} ～ {args.end}，共 {len(results)} 個 session 在範圍內有訊息')
    for first, path, in_range, last, prompts, last_reply, conclusions, cards in results:
        print(f'\n=== {project_label(path.parent.name)} / {path.stem[:8]} | 範圍內 {in_range} 筆 | {first:%m/%d %H:%M} ~ {last:%m/%d %H:%M}')
        if cards:
            print('   卡號：' + '、'.join(f'{card}×{count}' for card, count in cards.most_common(4)))
        for prompt in prompts:
            print(f'   > {prompt}')
        for conclusion in conclusions[-args.result_lines:]:
            print(f'   結論 {conclusion[:args.result_chars]}')
        if last_reply:
            print(f'   最後回覆：{last_reply[:args.reply_chars]}'.replace('\n', ' '))


if __name__ == '__main__':
    main()
