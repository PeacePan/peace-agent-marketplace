#!/usr/bin/env python3
"""用一次 GitHub GraphQL 查詢，列出範圍內「自己的 PR 動態」與「自己審查別人 PR 的紀錄」。

為什麼不用 MCP 逐筆查：判斷「某個審查是不是範圍內才送出的」要對每個 PR 各讀一次審查清單
（且 get_reviews 會連審查本文整份回傳，很吃 context）；GraphQL 一次帶回 PR 狀態、合併者與審查時間，
再由這裡依範圍篩選，並把 UTC 轉成範圍的時區，避免晚上的動作差一天。

需要已登入的 gh CLI（唯讀查詢）。用法：
    python3 github_in_range.py --start 2026-10-13T00:00:00+08:00 --end 2026-10-14T00:00:00+08:00
    python3 github_in_range.py --start ... --end ... --repo petpetgo/petpetgo

輸出判讀：
    自己的 PR：只列範圍內建立、合併、關閉或有更新的；「合併者」不是自己代表不是自己按的合併。
    審查他人 PR：只列自己的審查 submittedAt 落在範圍內的；機器人作者的 PR 略過。
"""
import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta

QUERY = '''
query($own: String!, $rev: String!) {
  own: search(query: $own, type: ISSUE, first: 100) {
    pageInfo { hasNextPage }
    nodes { ... on PullRequest {
      number title state isDraft merged mergedAt createdAt closedAt updatedAt reviewDecision
      baseRefName mergedBy { login }
    } }
  }
  rev: search(query: $rev, type: ISSUE, first: 100) {
    pageInfo { hasNextPage }
    nodes { ... on PullRequest {
      number title state merged author { login __typename }
      reviews(first: 100) { nodes { author { login } state submittedAt } }
    } }
  }
}
'''


def gh(*args: str) -> str:
    result = subprocess.run(['gh', *args], capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f'gh {" ".join(args[:2])} 失敗：{result.stderr.strip()}')
    return result.stdout


def parse(iso: str, tz):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(tz) if iso else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', required=True, help='範圍起點（含），ISO 8601，需帶時區')
    parser.add_argument('--end', required=True, help='範圍終點（不含），ISO 8601，需帶時區')
    parser.add_argument('--repo', default='petpetgo/petpetgo', help='owner/repo')
    args = parser.parse_args()

    start, end = datetime.fromisoformat(args.start), datetime.fromisoformat(args.end)
    tz = start.tzinfo
    me = gh('api', 'user', '--jq', '.login').strip()
    # 搜尋用 updated 先粗篩，起點多抓一天，再用實際時間戳精確篩
    since = (start - timedelta(days=1)).strftime('%Y-%m-%d')
    base = f'repo:{args.repo} is:pr updated:>={since}'
    data = json.loads(gh('api', 'graphql', '-f', f'query={QUERY}',
                         '-f', f'own={base} author:{me}',
                         '-f', f'rev={base} reviewed-by:{me} -author:{me}'))['data']

    def in_range(moment) -> bool:
        return moment is not None and start <= moment < end

    print(f'範圍 {args.start} ～ {args.end}｜帳號 {me}｜{args.repo}')
    if data['own']['pageInfo']['hasNextPage'] or data['rev']['pageInfo']['hasNextPage']:
        print('⚠ 結果超過 100 筆，已被截斷，請縮小範圍')

    print('\n【自己的 PR】')
    skipped = 0
    for pr in sorted(data['own']['nodes'], key=lambda p: p['number']):
        created, merged, closed, updated = (parse(pr[key], tz) for key in ('createdAt', 'mergedAt', 'closedAt', 'updatedAt'))
        events = []
        if in_range(created):
            events.append(f'建立 {created:%H:%M}')
        if in_range(merged):
            events.append(f'合併 {merged:%H:%M}（合併者 {pr["mergedBy"]["login"] if pr["mergedBy"] else "未知"}）')
        elif in_range(closed) and not pr['merged']:
            events.append(f'關閉未合併 {closed:%H:%M}')
        if not events and pr['state'] == 'OPEN' and in_range(updated):
            events.append(f'有更新 {updated:%H:%M}')
        if not events:
            skipped += 1
            continue
        state = '已合併' if pr['merged'] else {'OPEN': '開放中', 'CLOSED': '已關閉'}[pr['state']]
        extra = '，草稿' if pr['isDraft'] else ''
        decision = f'｜審查結果 {pr["reviewDecision"]}' if pr['reviewDecision'] and pr['state'] == 'OPEN' else ''
        print(f'  #{pr["number"]}｜{state}{extra}｜{"、".join(events)}{decision}｜base {pr["baseRefName"]}｜{pr["title"][:60]}')
    print(f'  （另有 {skipped} 個與範圍無關，已略過）')

    print('\n【審查他人 PR】只列自己的審查在範圍內送出的')
    for pr in sorted(data['rev']['nodes'], key=lambda p: p['number']):
        author = pr['author'] or {}
        if author.get('__typename') == 'Bot':
            continue
        mine = [(parse(r['submittedAt'], tz), r['state']) for r in pr['reviews']['nodes']
                if r['author'] and r['author']['login'] == me and r['submittedAt']]
        mine = [(moment, state) for moment, state in mine if in_range(moment)]
        if not mine:
            continue
        counts = Counter(state for _, state in mine)
        summary = '、'.join(f'{state}×{count}' for state, count in counts.items())
        final = max(mine)
        state = '已合併' if pr['merged'] else {'OPEN': '開放中', 'CLOSED': '已關閉'}[pr['state']]
        print(f'  #{pr["number"]}｜作者 {author.get("login", "未知")}｜{state}｜最後一筆 {final[0]:%H:%M} {final[1]}｜{summary}｜{pr["title"][:50]}')


if __name__ == '__main__':
    main()
