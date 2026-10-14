#!/usr/bin/env python3
"""建立 Google 文件之前，檢查報告 HTML 有沒有踩到固定的雷。

為什麼要在建立前檢查：Drive 的 update_file 只能改標題與位置，建好之後想改內容只能用 Google Docs 的
replaceAllText 逐段更正（見 SKILL.md），成本比建立前先掃一遍高得多。

用法：
    python3 check_report.py report.html

檢查項目（有 NG 會以非 0 結束）：
    NG  殘留 {{…}} 或 HTML 註解、五個章節標題缺漏、口頭稿帶卡號／PR 號、口頭稿超過 280 字、簡體字、手機號碼或簽章網址
    注意  口頭稿 251～280 字、疑似英文句子（技術名詞與函式名不算，只提醒人看一眼）
"""
import re
import sys
from pathlib import Path

HEADINGS = ['一、1 分鐘口頭稿', '二、整體摘要', '三、工作明細', '四、站會可提的待確認事項', '五、資料來源與限制']
SIMPLIFIED = set('这个们为来时动发资样种对实现线关开应会门问题经过还进与让说请读写验证认记统设计网络总结单页业务见类规则阅车员买卖费货质级区编组织终')
ID_PATTERN = re.compile(r'RD-\d+|#\d{4,5}|PR\s*#?\d+')
PHONE_PATTERN = re.compile(r'09\d{2}-?\d{3}-?\d{3}')
SIGNED_URL_PATTERN = re.compile(r'X-Amz-Signature|X-Goog-Signature|[?&]token=')
ENGLISH_SENTENCE = re.compile(r'(?:[A-Za-z]{2,}[ ,]+){4,}[A-Za-z]{2,}')


def strip_tags(html: str) -> str:
    return re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', html))


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit('用法：python3 check_report.py report.html')
    html = Path(sys.argv[1]).read_text(encoding='utf-8')
    problems, notes = [], []

    if '{{' in html or '}}' in html:
        problems.append('殘留 {{…}} 未替換')
    if '<!--' in html:
        problems.append('殘留 HTML 註解')
    missing = [heading for heading in HEADINGS if heading not in html]
    if missing:
        problems.append(f'缺少章節標題：{"、".join(missing)}')

    oral_match = re.search(r'一、1 分鐘口頭稿</h2>(.*?)</table>', html, re.S)
    if oral_match:
        oral = strip_tags(oral_match.group(1))
        length = len(oral)
        print(f'口頭稿 {length} 字')
        if length > 280:
            problems.append(f'口頭稿 {length} 字，超過約 250 字的上限（280 字以內才放行）')
        elif length > 250:
            notes.append(f'口頭稿 {length} 字，略超過 250 字，能再砍就砍')
        ids = ID_PATTERN.findall(oral)
        if ids:
            problems.append(f'口頭稿出現編號：{"、".join(ids)}（口頭稿一律用白話名稱，編號只放明細表最右欄）')
    else:
        problems.append('找不到口頭稿區塊')

    simplified = sorted({char for char in html if char in SIMPLIFIED})
    if simplified:
        problems.append(f'疑似簡體字：{"".join(simplified)}')
    if PHONE_PATTERN.search(html):
        problems.append('出現手機號碼，須去識別化')
    if SIGNED_URL_PATTERN.search(html):
        problems.append('出現簽章網址或 token，不可放進報告')

    text = re.sub(r'<[^>]+>', ' ', html)
    sentences = ENGLISH_SENTENCE.findall(text)
    if sentences:
        notes.append(f'疑似英文句子，請人工確認是否只是技術名詞：{" ｜ ".join(s.strip() for s in sentences[:3])}')

    for note in notes:
        print(f'注意：{note}')
    for problem in problems:
        print(f'NG：{problem}')
    print('結果：' + ('不通過' if problems else '通過'))
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
