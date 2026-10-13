#!/usr/bin/env python3
"""決定晨會工作報告的日期範圍與檔名，輸出 JSON。

規則：
- 晨會日（預設今天，台北時間）為週二～週五：回顧前一個日曆日。
- 晨會日為週一：回顧上週五 00:00 到週日 24:00（週五、週六、週日）。
- 晨會日為週六／週日：沒有晨會，仍回顧前一天，並在 note 提醒。

用法：
    python3 resolve_dates.py                    # 以今天為晨會日
    python3 resolve_dates.py --date 2026-10-13  # 指定晨會日
"""
import argparse
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']
TITLE_PREFIX = '晨會工作總結_'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='晨會日 YYYY-MM-DD，預設今天')
    parser.add_argument('--tz', default='Asia/Taipei')
    args = parser.parse_args()

    tz = ZoneInfo(args.tz)
    standup: date = date.fromisoformat(args.date) if args.date else datetime.now(tz).date()
    weekday = standup.weekday()

    # 週一回顧週五～週日（3 天），其餘回顧前一天
    back_days = 3 if weekday == 0 else 1
    work_dates = [standup - timedelta(days=n) for n in range(back_days, 0, -1)]

    start = datetime.combine(work_dates[0], time.min, tzinfo=tz)
    end = datetime.combine(standup, time.min, tzinfo=tz)

    note = ''
    if weekday >= 5:
        note = '晨會日是週末，通常沒有晨會；仍回顧前一天，請向使用者確認是否需要'

    print(json.dumps({
        'standupDate': standup.isoformat(),
        'standupWeekday': WEEKDAYS[weekday],
        'workDates': [d.isoformat() for d in work_dates],
        'workWeekdays': [WEEKDAYS[d.weekday()] for d in work_dates],
        'workStart': start.isoformat(),
        'workEnd': end.isoformat(),
        'workStartUtc': start.astimezone(ZoneInfo('UTC')).isoformat(),
        'workEndUtc': end.astimezone(ZoneInfo('UTC')).isoformat(),
        'gitSince': start.strftime('%Y-%m-%d %H:%M'),
        'gitUntil': end.strftime('%Y-%m-%d %H:%M'),
        'githubUpdatedFrom': (work_dates[0] - timedelta(days=1)).isoformat(),
        'title': f'{TITLE_PREFIX}{standup.isoformat()}',
        'titlePrefix': TITLE_PREFIX,
        'tz': args.tz,
        'note': note,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
