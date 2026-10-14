#!/usr/bin/env python3
"""彙整指定時間範圍內，自己在所有分支上的 git 活動，直接分成「當天新提交」「搬動的舊提交」「自己按下的合併」。

為什麼要自己分類：git log 的 --since/--until 比的是 commit 時間（committer date），
rebase 或 cherry-pick 過的舊 commit 作者時間（author date）還停在好幾天前，卻會因為 commit 時間落在範圍內而混進來，
肉眼讀 log 很容易把「搬動」誤認成「當天寫的」。這裡一律以作者時間判斷是不是當天新作。

用法（在程式庫內、或隔離 worktree 內執行都可以，worktree 與主 checkout 共用 refs）：
    python3 git_in_range.py --start 2026-10-13T00:00:00+08:00 --end 2026-10-14T00:00:00+08:00
    python3 git_in_range.py --start ... --end ... --repo /path/to/repo --author PeacePan

為什麼寫成腳本：隔離 worktree 的 session 會拒絕含 $(...) 的 git 指令（例如 --author="$(git config user.name)"），
改由腳本自己讀 user.name 就沒有這個問題。
"""
import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SEP = '\x1f'
LOG_FORMAT = SEP.join(['%H', '%aI', '%cI', '%P', '%s'])
CARD_PATTERN = re.compile(r'RD-\d+')
PR_MERGE_PATTERN = re.compile(r'^Merge pull request #(\d+) from [^/]+/(.+)$')
BRANCH_MERGE_PATTERN = re.compile(r"^Merge branch '(.+?)'(?: of \S+)?(?: into (.+))?$")


def run_git(repo: str, *args: str) -> str:
    result = subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f'git {" ".join(args)} 失敗：{result.stderr.strip()}')
    return result.stdout


def cards_of(text: str) -> list:
    return sorted(set(CARD_PATTERN.findall(text)))


def span_text(moments: list) -> str:
    ordered = sorted(moments)
    return f'{ordered[0]:%H:%M}' if len(ordered) == 1 else f'{ordered[0]:%H:%M}–{ordered[-1]:%H:%M}'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', required=True, help='範圍起點（含），ISO 8601，需帶時區')
    parser.add_argument('--end', required=True, help='範圍終點（不含），ISO 8601，需帶時區')
    parser.add_argument('--repo', default='.', help='程式庫路徑，預設為目前目錄')
    parser.add_argument('--author', help='作者名稱，預設讀該程式庫的 user.name')
    args = parser.parse_args()

    start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
    author = args.author or run_git(args.repo, 'config', 'user.name').strip()
    # commit 時間可能比作者時間晚（事後 rebase），所以終點多抓一天，再用作者時間回頭篩
    until = (end + timedelta(days=1)).isoformat()
    raw = run_git(args.repo, 'log', '--all', f'--author={author}', f'--since={start.isoformat()}',
                  f'--until={until}', f'--pretty=format:{LOG_FORMAT}')

    new_work = {}
    moved = {}
    pr_merges = []
    cascade = []
    release_prs = []
    branch_merges = []
    for line in raw.splitlines():
        sha, author_iso, commit_iso, parents, subject = line.split(SEP, 4)
        authored = datetime.fromisoformat(author_iso).astimezone(start.tzinfo)
        committed = datetime.fromisoformat(commit_iso).astimezone(start.tzinfo)
        authored_in_range = start <= authored < end
        is_merge = len(parents.split()) > 1
        if is_merge:
            if not authored_in_range:
                continue
            pr_match = PR_MERGE_PATTERN.match(subject)
            branch_match = BRANCH_MERGE_PATTERN.match(subject)
            if pr_match:
                number, branch = pr_match.groups()
                entry = (authored, number, branch)
                if branch.startswith(('update-release/', 'update-staging/')):
                    cascade.append(entry)
                elif branch.startswith('release/'):
                    release_prs.append(entry)
                else:
                    pr_merges.append(entry)
            elif branch_match:
                branch_merges.append((authored, branch_match.group(1), branch_match.group(2) or '（目前分支）'))
            continue
        # 同一份修改在不同分支會有不同 SHA，作者時間與標題相同就視為同一筆
        key = (author_iso, subject)
        if authored_in_range:
            new_work[key] = (authored, subject)
        elif start <= committed < end:
            moved[subject] = (authored, subject)

    def group_by_card(entries: dict) -> dict:
        groups = defaultdict(list)
        for authored, subject in entries.values():
            cards = cards_of(subject)
            groups[cards[0] if cards else '（標題無卡號）'].append((authored, subject))
        return groups

    print(f'範圍 {args.start} ～ {args.end}｜作者 {author}｜程式庫 {args.repo}')
    new_groups = group_by_card(new_work)
    print(f'\n【當天新提交】作者時間在範圍內，去重後共 {len(new_work)} 個')
    for card, items in sorted(new_groups.items(), key=lambda kv: min(a for a, _ in kv[1])):
        latest = max(items)[1]
        print(f'  {card}｜{len(items)} 個｜{span_text([a for a, _ in items])}｜最新：{latest[:70]}')

    moved_groups = group_by_card(moved)
    print(f'\n【搬動的舊提交】commit 時間在範圍內、作者時間更早（rebase／cherry-pick，不算當天新作），共 {len(moved)} 個')
    for card, items in sorted(moved_groups.items()):
        oldest = min(a for a, _ in items)
        # 標題沒帶卡號時，附一則標題當線索，才知道是哪項工作被搬動
        sample = f'｜例：{items[0][1][:40]}' if card.startswith('（') else ''
        print(f'  {card}｜{len(items)} 個｜最早作者時間 {oldest:%m/%d %H:%M}{sample}')

    print(f'\n【自己按下的 PR 合併】{len(pr_merges)} 個（不含版更連動與 release PR）')
    for moment, number, branch in sorted(pr_merges):
        train = '（班車 PR，非自己的功能 PR）' if branch.startswith('train/') else ''
        print(f'  {moment:%H:%M} PR #{number} {branch}{train}')
    print(f'【版更連動 PR】{len(cascade)} 個（update-release／update-staging）：'
          + '、'.join(f'#{number}' for _, number, _ in sorted(cascade)))
    print(f'【release PR】{len(release_prs)} 個：'
          + '、'.join(f'#{number} {branch}' for _, number, branch in sorted(release_prs)))
    print(f'【分支合併】{len(branch_merges)} 個（解衝突或直接併入）')
    for moment, source, target in sorted(branch_merges):
        print(f'  {moment:%H:%M} {source} → {target}')

    every_text = ' '.join([s for _, s in new_work.values()] + list(moved)
                          + [b for _, _, b in pr_merges] + [s for _, s, _ in branch_merges])
    print(f'\n卡號（供 Jira 查詢）：{", ".join(cards_of(every_text))}')


if __name__ == '__main__':
    main()
