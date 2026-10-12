#!/usr/bin/env python3
"""Ragdoll 門市刷卡機（台新 ECR 400B）問題回報包診斷。

用途：拿到門市的問題回報包（production_issue-*）後，一次跑完「發病點、失敗型態、封包鑑識、
帳務對帳、走哪條路徑、代理程式是否正常、PC 序列埠是否健康」，並給出「硬體線路 vs 程式」的初判。

設計原則：
- 唯讀。SQLite 以 immutable 唯讀開啟；不執行任何來自資料的內容。
- 不印卡號。out.dat／DB 內的卡號欄位只統計長度與格式，絕不輸出內容。
- 僅用標準庫，Python 3.9+。建議以 `python3 -I` 執行（資料來自不可信的下載檔）。

用法：
    python3 -I triage.py <回報包目錄> [--agent-logs <代理程式 log 目錄>] [--onset YYYY-MM-DD]
                         [--control-ok] [--no-sw-change] [--json]
    python3 -I triage.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

# ---------------------------------------------------------------------------
# 常數
# ---------------------------------------------------------------------------

STX, ETX, ACK = 0x02, 0x03, 0x06
FRAME_LEN = 403  # STX + 400 bytes 資料 + ETX + LRC
TZ_TW = timezone(timedelta(hours=8))
CONF_LEVELS = ['低', '中', '中高', '高']

# 回應碼（規格書 TSB 400B v1.32 §2.10-G）
RESPONSE_CODES = {
    '0000': 'Approved', '0001': 'Error', '0002': 'Call Bank', '0003': 'Timeout',
    '0004': 'Fall Back', '0006': 'Authorization Failed', '0007': 'Amount Error',
    '0008': 'CONTACTLESS Error',
}

# 屬於「通訊／線路層」的失敗型態（刷卡機沒有給出可讀的結果）
LINK_FAIL = {'SILENT', 'ACK_ONLY', 'ACK_THEN_BAD', 'GARBLED_NO_ACK', 'NOISE_ONLY', 'LINK_ERR_AFTER_VALID_FRAME'}

OUTCOME_HELP = {
    'APPROVED': '收到完整且 LRC 正確的結果框，回應碼 0000',
    'TERMINAL_REPLY': '刷卡機有回完整結果但回應碼非 0000（拒絕／取消／操作問題），不是線路故障',
    'SILENT': '完全沒收到任何位元組（ECR 常記 [16] 或 [14]）',
    'ACK_ONLY': '只收到刷卡機的 ACK，之後沒有結果（等待逾時）',
    'ACK_THEN_BAD': '收到 ACK（刷卡機已收下請求），但結果在傳回途中損壞，找不到有效框',
    'GARBLED_NO_ACK': '沒收到 ACK，卻收到一串無法解析的資料（亂碼）',
    'NOISE_ONLY': '只收到 1～16 bytes 的零星雜訊',
    'LINK_ERR_AFTER_VALID_FRAME': '已收到有效框，但 ECR 仍回報通訊錯誤（多段流程中途失敗）',
}

RE_TS = re.compile(rb'^(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d) ')
RE_CHUNK = re.compile(rb'Receive Data\s+\[(\d+)\]: ([0-9A-Fa-f]*)')
RE_ERR = re.compile(rb'\[(\d{2})\]:\s*(.*)$')
RE_REQ = re.compile(rb'Send Message\s+\[400\]: (\d{2})\s+(\d{12})')
RE_SEND_ALL = re.compile(rb'Send AllData\s+\[403\]: ([0-9A-Fa-f]+)')
# 請求封包每筆都會變的欄位（調閱編號、金額、日期時間、櫃號機號時戳）；遮蔽後才能比對「格式有沒有變」
MASK_RANGES = ((4, 10), (33, 45), (45, 57), (114, 132))
ECR_ERR_PREFIX = '中介程式執行錯誤'.encode('cp950')  # ECR.exe 自己記錄的錯誤行


# ---------------------------------------------------------------------------
# 工具函式
# ---------------------------------------------------------------------------

def md_table(headers, rows):
    """產生 Markdown 表格；rows 為二維陣列。"""
    out = ['| ' + ' | '.join(str(h) for h in headers) + ' |', '|' + '|'.join('---' for _ in headers) + '|']
    for r in rows:
        out.append('| ' + ' | '.join(str(c) for c in r) + ' |')
    return '\n'.join(out)


def pct(n, d):
    return f'{(n / d * 100):.0f}%' if d else '-'


def lrc_ok(frame):
    """LRC＝資料與 ETX 的 XOR（STX 不含），放在框的最後一個位元組。"""
    if len(frame) != FRAME_LEN or frame[0] != STX or frame[401] != ETX:
        return False
    x = 0
    for c in frame[1:402]:
        x ^= c
    return x == frame[402]


def open_ro(path):
    """以 immutable 唯讀開啟 SQLite，不會建立 journal／wal。"""
    uri = 'file:' + quote(os.path.abspath(path)) + '?mode=ro&immutable=1'
    return sqlite3.connect(uri, uri=True)


def table_exists(con, name):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def table_columns(con, name):
    return {r[1] for r in con.execute(f'PRAGMA table_info({name})')}


def safe_run(fn, *args, what=''):
    """回報包常不完整或檔案損壞：單一分析失敗只讓該章節略過並說明原因，不讓整份診斷中斷。"""
    try:
        return fn(*args)
    except (sqlite3.Error, OSError, ValueError, KeyError, UnicodeError) as e:
        return {'present': False, 'reason': f'{what}分析失敗（{type(e).__name__}：{e}），檔案可能損壞或格式與預期不符'}


def parse_onset_arg(text):
    """--onset 接受 YYYY-MM-DD 或 YYYY-MM-DD HH:MM；格式錯誤丟 ValueError。"""
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f'--onset 格式需為 YYYY-MM-DD 或 YYYY-MM-DD HH:MM：{text}')


def level_up(level, n=1):
    i = CONF_LEVELS.index(level)
    return CONF_LEVELS[max(0, min(len(CONF_LEVELS) - 1, i + n))]


# ---------------------------------------------------------------------------
# 1. ECR log
# ---------------------------------------------------------------------------

class Block:
    """ECR.exe 一次執行（START～END）。"""

    def __init__(self, start):
        self.start = start
        self.end = None
        self.trans_type = None
        self.amount_cents = None
        self.retries = 0
        self.err_code = None
        self.err_label = ''
        self.chunks = []
        self.nak = 0          # ECR 送給刷卡機的 NAK 次數（要求重送損壞的結果）
        self.req_hex = None   # 送出的請求封包（403 bytes 的 hex）

    # 以下欄位由 analyze() 填入
    outcome = ''
    ack = 0
    total = 0
    hi_ratio = 0.0
    valid_prefix = 0
    frames = 0
    resp_code = ''
    detail_code = ''
    receipt = ''

    @property
    def link_fail(self):
        return self.outcome in LINK_FAIL


def analyze_stream(stream):
    """把一次執行收到的原始位元組分類。回傳 dict。"""
    s = stream
    ack = 0
    while s[:1] == b'\x06':
        ack += 1
        s = s[1:]
    n = len(s)
    frames = []
    i = 0
    while i < n:
        if s[i] == STX and i + FRAME_LEN <= n and lrc_ok(s[i:i + FRAME_LEN]):
            frames.append(s[i:i + FRAME_LEN])
            i += FRAME_LEN
        else:
            i += 1
    hi = sum(1 for c in s if c >= 0x80)
    first_stx = s.find(b'\x02')
    valid_prefix = 0
    if first_stx >= 0:
        k = first_stx + 1
        while k < n and 0x20 <= s[k] < 0x7f:
            k += 1
        valid_prefix = k - first_stx
    out = {
        'ack': ack, 'remaining': n, 'frames': len(frames), 'hi_ratio': (hi / n) if n else 0.0,
        'valid_prefix': valid_prefix, 'resp_code': '', 'detail_code': '', 'finished': '', 'receipt': '',
    }
    if frames:
        data = frames[-1][1:401].decode('latin-1')
        out['resp_code'] = data[78:82]
        out['detail_code'] = data[29:33].strip()
        out['finished'] = data[259:260]
        out['receipt'] = data[4:10].strip()
    return out


def classify(block, a):
    """依位元組分析與 ECR 錯誤碼決定結果型態。"""
    if a['frames']:
        if block.err_code:
            return 'LINK_ERR_AFTER_VALID_FRAME'
        if a['finished'] == 'N':
            return 'LINK_ERR_AFTER_VALID_FRAME'
        return 'APPROVED' if a['resp_code'] == '0000' else 'TERMINAL_REPLY'
    full_ack = a['ack'] >= 2  # 規格書：ACK 回兩次（0606）；單一個 0x06 可能只是雜訊
    if a['ack'] == 0 and a['remaining'] == 0:
        return 'SILENT'
    if a['remaining'] == 0:
        return 'ACK_ONLY' if full_ack else 'NOISE_ONLY'
    if full_ack:
        return 'ACK_THEN_BAD'
    return 'NOISE_ONLY' if a['remaining'] <= 16 else 'GARBLED_NO_ACK'  # 含「只有單一個 0x06 後接亂碼」


def parse_ecr_logs(log_dir):
    """解析 ecr/log/*.log（Big5＋hex）。回傳 (依時間排序的 Block 清單, 檔案數, 區塊完整性統計)。

    完整性：每次 ECR.exe 執行應是乾淨的 START…END。前一區塊沒有 END 就又開始新區塊（overlaps），
    或區塊外還有帶時間戳的殘留輸出（orphans），是殭屍 ECR.exe 或兩個程序同時使用 COM1 的跡象。
    """
    blocks = []
    integrity = {'overlaps': 0, 'orphans': 0, 'unfinished': 0}
    files = sorted(glob.glob(os.path.join(log_dir, '*.log')))
    for path in files:
        raw = open(path, 'rb').read()
        cur = None
        for line in raw.split(b'\n'):
            line = line.rstrip(b'\r')
            m = RE_TS.match(line)
            if m and b'START====' in line:
                if cur is not None:
                    integrity['overlaps'] += 1
                    blocks.append(cur)
                cur = Block(datetime.strptime(m.group(1).decode(), '%Y/%m/%d %H:%M:%S'))
                continue
            if cur is None:
                if m:
                    integrity['orphans'] += 1
                continue
            if m and b'END=====' in line:
                cur.end = datetime.strptime(m.group(1).decode(), '%Y/%m/%d %H:%M:%S')
                blocks.append(cur)
                cur = None
                continue
            if cur.amount_cents is None:
                r = RE_REQ.search(line)
                if r:
                    cur.trans_type = r.group(1).decode()
                    cur.amount_cents = int(r.group(2))
            if cur.req_hex is None:
                sa = RE_SEND_ALL.search(line)
                if sa:
                    cur.req_hex = sa.group(1).decode()
            if b'Send Message' in line and b'<Nak>' in line:
                cur.nak += 1
            if b'Send request again' in line:
                cur.retries += 1
            c = RE_CHUNK.search(line)
            if c:
                cur.chunks.append(bytes.fromhex(c.group(2).decode()))
                continue
            if ECR_ERR_PREFIX in line:
                e = RE_ERR.search(line)
                if e and cur.err_code is None:
                    cur.err_code = e.group(1).decode()
                    cur.err_label = e.group(2).decode('cp950', errors='replace').strip()
        if cur is not None:
            integrity['unfinished'] += 1  # 檔尾沒有 END：可能是回報當下剛好還在執行，不計為異常
            blocks.append(cur)
    blocks.sort(key=lambda b: b.start)
    for b in blocks:
        a = analyze_stream(b''.join(b.chunks))
        b.ack, b.total, b.hi_ratio = a['ack'], a['remaining'], a['hi_ratio']
        b.valid_prefix, b.frames = a['valid_prefix'], a['frames']
        b.resp_code, b.detail_code, b.receipt = a['resp_code'], a['detail_code'], a['receipt']
        b.outcome = classify(b, a)
    return blocks, len(files), integrity


def request_template(req_hex):
    """請求封包遮蔽掉每筆都會變的欄位後的樣板，用來確認發病前後「送出的格式有沒有變」。"""
    try:
        raw = bytes.fromhex(req_hex)
    except ValueError:
        return None
    if len(raw) != FRAME_LEN:
        return None
    data = list(raw[1:401].decode('latin-1'))
    for a, b in MASK_RANGES:
        data[a:b] = ['#'] * (b - a)
    return ''.join(data)


def detect_onset(blocks, forced=None):
    """用逐日失敗率找「從好變壞」的發病日；回傳 dict 或 None。"""
    if not blocks:
        return None
    days = sorted({b.start.date() for b in blocks})
    stats = {d: [0, 0] for d in days}
    for b in blocks:
        stats[b.start.date()][0] += 1
        stats[b.start.date()][1] += 1 if b.link_fail else 0
    cand = None
    forced_dt = parse_onset_arg(forced) if forced else None
    if forced_dt:
        cand = forced_dt.date()
    else:
        for idx, d in enumerate(days):
            post_calls = sum(stats[x][0] for x in days[idx:])
            post_fail = sum(stats[x][1] for x in days[idx:])
            prev = days[max(0, idx - 14):idx]
            if post_calls < 5 or not prev:
                continue
            pc = sum(stats[x][0] for x in prev)
            pf = sum(stats[x][1] for x in prev)
            day_rate = stats[d][1] / stats[d][0]
            if post_fail / post_calls >= 0.5 and (pf / pc if pc else 0) <= 0.1 and day_rate >= 0.3:
                cand = d
                break
    if cand is None:
        return None
    floor = forced_dt if forced_dt else datetime.combine(cand, datetime.min.time())
    first_fail = next((b for b in blocks if b.start >= floor and b.link_fail), None)
    last_ok = None
    if first_fail:
        for b in blocks:
            if b.start < first_fail.start and not b.link_fail:
                last_ok = b
    pre = [b for b in blocks if b.start.date() < cand]
    post = [b for b in blocks if b.start.date() >= cand]
    pre_days = len({b.start.date() for b in pre})
    return {
        'date': cand, 'first_fail': first_fail, 'last_ok': last_ok,
        'pre_calls': len(pre), 'pre_fail': sum(1 for b in pre if b.link_fail),
        'pre_days': pre_days,
        'post_calls': len(post), 'post_fail': sum(1 for b in post if b.link_fail),
        'post_approved': sum(1 for b in post if b.outcome == 'APPROVED'),
    }


def analyze_ecr(report_dir, forced_onset):
    log_dir = os.path.join(report_dir, 'ecr', 'log')
    if not os.path.isdir(log_dir):
        return {'present': False, 'reason': f'找不到 {log_dir}（機台可能不走 ECR.exe，或回報包缺 ecr 資料夾）'}
    blocks, nfiles, integrity = parse_ecr_logs(log_dir)
    if not blocks:
        return {'present': False, 'reason': 'ecr/log 內沒有任何 START 區塊'}
    onset = detect_onset(blocks, forced_onset)
    daily = defaultdict(lambda: Counter())
    for b in blocks:
        d = b.start.date().isoformat()
        daily[d]['calls'] += 1
        daily[d]['approved'] += b.outcome == 'APPROVED'
        daily[d]['terminal'] += b.outcome == 'TERMINAL_REPLY'
        daily[d]['link'] += b.link_fail
    since = onset['date'] if onset else None
    if since is not None:
        scope = [b for b in blocks if b.start.date() >= since]
    else:
        last_day = blocks[-1].start.date()
        scope = [b for b in blocks if b.start.date() > last_day - timedelta(days=14)]
    mix = Counter(b.outcome for b in scope)
    codes = Counter(f'[{b.err_code}] {b.err_label}' for b in scope if b.err_code)
    # 封包鑑識（只看有位元組的失敗）
    bad = [b for b in scope if b.link_fail and (b.total > 0 or b.ack > 0)]
    excess = [b for b in bad if b.total > FRAME_LEN]
    noise = [b for b in scope if b.outcome == 'NOISE_ONLY']
    garbled = [b for b in scope if b.outcome == 'GARBLED_NO_ACK']
    ack_bad = [b for b in scope if b.outcome == 'ACK_THEN_BAD']
    clean_between = 0
    for i, b in enumerate(scope):
        if b.outcome != 'APPROVED':
            continue
        near = []
        if i > 0:
            near.append(scope[i - 1])
        if i + 1 < len(scope):
            near.append(scope[i + 1])
        if any(x.link_fail and abs((x.start - b.start).total_seconds()) <= 1800 for x in near):
            clean_between += 1
    if since is None:
        signature = '未偵測到發病點，無法做發病後型態判讀'
    elif excess or noise:
        signature = '間歇性接觸不良／線路雜訊型（出現多於 403 bytes 的垃圾或零星雜訊）'
    elif clean_between == 0 and garbled and not any(b.outcome == 'APPROVED' for b in scope):
        signature = '靜態速率／格式不符型（全數亂碼，沒有任何乾淨的框）→ 請核對兩端的 baud／同位／資料位元設定'
    elif ack_bad or garbled:
        signature = '接收端丟位元組型（只有縮短的框，沒有多餘垃圾）→ 查 PC 負載或轉接器驅動'
    else:
        signature = '以靜默無回應為主，無法由封包型態判讀'
    # 請求封包樣板：發病前後送出的格式有沒有變（遮蔽調閱編號、金額、日期時間、櫃機號時戳）
    tpl_pre, tpl_post = Counter(), Counter()
    for b in blocks:
        t = request_template(b.req_hex) if b.req_hex else None
        if t is None:
            continue
        post = bool(onset) and b.start.date() >= onset['date']
        (tpl_post if post else tpl_pre)[t] += 1
    post_only = [k for k in tpl_post if k not in tpl_pre]
    templates = {'pre_n': sum(tpl_pre.values()), 'post_n': sum(tpl_post.values()),
                 'pre_distinct': len(tpl_pre), 'post_distinct': len(tpl_post),
                 'post_only': sum(tpl_post[k] for k in post_only), 'post_only_types': len(post_only)}
    # ECR 送給刷卡機的 NAK（要求重送損壞的結果）：發病前後各幾次
    nak_pre = sum(b.nak for b in blocks if not onset or b.start.date() < onset['date'])
    nak_post = sum(b.nak for b in blocks if onset and b.start.date() >= onset['date'])
    # 重試風險：刷卡機已收下請求（ACK）但結果損壞，隨後同金額重試核准——中間有沒有多佔用一個調閱編號？
    approved = [b for b in blocks if b.outcome == 'APPROVED' and b.receipt.isdigit()]
    retry_checks = []
    for f in scope:
        if not f.link_fail or f.ack < 2 or f.amount_cents is None:
            continue
        nxt = next((a for a in scope if a.start > f.start and a.outcome == 'APPROVED' and a.receipt.isdigit()
                    and a.amount_cents == f.amount_cents and (a.start - f.start) <= timedelta(minutes=10)), None)
        prev_ok = None
        for p in approved:
            if p.start < f.start:
                prev_ok = p
            else:
                break
        if nxt and prev_ok:
            retry_checks.append({'failed_at': f.start, 'approved_at': nxt.start, 'amount': f.amount_cents / 100,
                                 'prev_receipt': int(prev_ok.receipt), 'new_receipt': int(nxt.receipt),
                                 'gap': int(nxt.receipt) - int(prev_ok.receipt) - 1})
    return {
        'present': True, 'blocks': blocks, 'files': nfiles, 'onset': onset, 'daily': daily,
        'scope_mix': mix, 'scope_codes': codes, 'bad': bad, 'excess': excess, 'noise': noise,
        'garbled': garbled, 'ack_bad': ack_bad, 'clean_between': clean_between, 'signature': signature,
        'scope_calls': len(scope), 'integrity': integrity, 'templates': templates,
        'nak_pre': nak_pre, 'nak_post': nak_post, 'retry_checks': retry_checks,
    }


# ---------------------------------------------------------------------------
# 2. 歸檔 out.dat
# ---------------------------------------------------------------------------

def decode_outdat(raw):
    """回傳 (種類, 回應碼, 細項碼)。種類：OK／TEMPLATE／TERMINAL_REPLY／UNKNOWN。"""
    if len(raw) != 400:
        return 'UNKNOWN', '', ''
    s = raw.decode('latin-1')
    code, detail = s[78:82], s[29:33].strip()
    if re.match(r'^\d\d', s) and code == '0000':
        return 'OK', code, detail
    if s[:78].strip() == '' and s[82:].strip() == '':
        return 'TEMPLATE', code, detail
    return 'TERMINAL_REPLY', code, detail


def scan_outdat(report_dir):
    base = os.path.join(report_dir, 'ecr', 'transmitted')
    if not os.path.isdir(base):
        return {'present': False}
    kinds = Counter()
    per_day = defaultdict(Counter)
    for path in sorted(glob.glob(os.path.join(base, '*', '*', '*_out.dat'))):
        day = os.path.basename(os.path.dirname(path))
        kind, code, detail = decode_outdat(open(path, 'rb').read())
        key = f'{kind}:{code}' if kind != 'OK' else 'OK'
        if kind == 'TERMINAL_REPLY' and detail:
            key += f'（細項 {detail}）'
        kinds[key] += 1
        per_day[day][key] += 1
    return {'present': True, 'kinds': kinds, 'per_day': per_day}


# ---------------------------------------------------------------------------
# 3. 本機帳務對帳
# ---------------------------------------------------------------------------

def analyze_payments(report_dir, onset_date, blocks):
    path = os.path.join(report_dir, 'offline-mutable.snapshot.db')
    if not os.path.isfile(path):
        return {'present': False, 'reason': '找不到 offline-mutable.snapshot.db'}
    con = open_ro(path)
    try:
        if not table_exists(con, 'offline_sale_lines_payments'):
            return {'present': False, 'reason': '資料庫沒有 offline_sale_lines_payments'}
        pcols = table_columns(con, 'offline_sale_lines_payments')
        want = ['created_at', 'type', 'amount', 'receipt_no', 'reconcile_info', 'offline_sale_name']
        if any(c not in pcols for c in want):
            return {'present': False, 'reason': f'付款表欄位與預期不符：缺 {[c for c in want if c not in pcols]}'}
        rows = con.execute(
            "SELECT created_at, type, amount, receipt_no, reconcile_info FROM offline_sale_lines_payments "
            "WHERE type IN ('CREDIT','CREDIT_OFFLINE') ORDER BY created_at").fetchall()
    finally:
        con.close()
    recs = []
    for created, typ, amount, receipt, recon in rows:
        t = datetime.fromtimestamp(created / 1000, TZ_TW).replace(tzinfo=None)
        recs.append({'t': t, 'type': typ, 'amount': amount or 0, 'receipt': (receipt or '').strip(), 'recon': recon or ''})
    daily = defaultdict(lambda: {'ok': 0, 'off': 0, 'off_amt': 0})
    for r in recs:
        d = r['t'].date().isoformat()
        if r['type'] == 'CREDIT':
            daily[d]['ok'] += 1
        else:
            daily[d]['off'] += 1
            daily[d]['off_amt'] += r['amount']
    offs = [r for r in recs if r['type'] == 'CREDIT_OFFLINE']
    oks = [r for r in recs if r['type'] == 'CREDIT']
    # 調閱編號缺口對手 KEY 筆數
    recon_rows = []
    prev = None
    for r in oks:
        if not r['receipt'].isdigit():
            continue
        cur = int(r['receipt'])
        if prev is not None and cur > prev[0]:
            gap = cur - prev[0] - 1
            between = [o for o in offs if prev[1] < o['t'] < r['t']]
            if gap or between:
                recon_rows.append({'from': prev[0], 'to': cur, 'gap': gap, 'offline': len(between),
                                   'span': f"{prev[1]:%m/%d %H:%M} → {r['t']:%m/%d %H:%M}"})
        prev = (cur, r['t'])
    est_receipt = None
    if prev:
        after = [o for o in offs if o['t'] > prev[1]]
        est_receipt = {'last_receipt': prev[0], 'last_time': prev[1], 'offline_after': len(after),
                       'estimate': prev[0] + len(after)}
    # 卡號格式統計（不輸出內容）
    digits_only = masked_like = other = 0
    for o in offs:
        v = o['recon']
        if v and v.isdigit() and len(v) >= 12:
            digits_only += 1
        elif v and re.search(r'[Xx*]', v):
            masked_like += 1
        elif v:
            other += 1
    dup = Counter((o['recon'], o['amount']) for o in offs if o['recon'])
    dup_groups = [k for k, v in dup.items() if v > 1]
    # 每筆手 KEY 前 10 分鐘內，有沒有一次「金額相符的失敗 ECR 呼叫」（手 KEY 的前因）
    fails = [b for b in (blocks or []) if b.link_fail and b.amount_cents is not None]
    matched = 0
    unmatched = []
    for o in offs:
        hit = any(b.start <= o['t'] and (o['t'] - (b.end or b.start)) <= timedelta(minutes=10)
                  and b.amount_cents == o['amount'] * 100 for b in fails)
        if hit:
            matched += 1
        else:
            unmatched.append({'at': o['t'], 'amount': o['amount']})
    # 刷卡機核准、金額相同、5 分鐘內仍手 KEY，且這筆核准沒有對應的 CREDIT 入帳（疑似 POS 顯示／流程問題）
    abo = []
    for b in (blocks or []):
        if b.outcome != 'APPROVED' or b.amount_cents is None:
            continue
        end = b.end or b.start
        if any(r['amount'] * 100 == b.amount_cents and abs((r['t'] - end).total_seconds()) <= 180 for r in oks):
            continue  # 這筆核准已正常入帳，不算
        for o in offs:
            if o['amount'] * 100 == b.amount_cents and timedelta(0) <= (o['t'] - end) <= timedelta(minutes=5):
                abo.append({'approved_at': end, 'offline_at': o['t'], 'amount': o['amount']})
                break
    first_off = offs[0]['t'] if offs else None
    return {
        'present': True, 'daily': daily, 'offline_total': len(offs), 'offline_amount': sum(o['amount'] for o in offs),
        'ok_total': len(oks), 'first_offline': first_off, 'recon_rows': recon_rows, 'est_receipt': est_receipt,
        'pan_digits_only': digits_only, 'pan_masked_like': masked_like, 'pan_other': other,
        'dup_groups': len(dup_groups), 'approved_but_offline': len(abo), 'approved_but_offline_rows': abo[:10],
        'offline_matched': matched, 'offline_unmatched': unmatched[:10], 'offline_unmatched_n': len(unmatched),
        'onset_date': onset_date,
    }


# ---------------------------------------------------------------------------
# 4. 種子名單：走代理程式還是直連
# ---------------------------------------------------------------------------

def analyze_pilot(report_dir):
    out = {'present': False}
    sj = os.path.join(report_dir, 'ragdoll-store.json')
    store = {}
    if os.path.isfile(sj):
        try:
            store = json.load(open(sj, encoding='utf-8'))
        except (ValueError, OSError):
            store = {}
    cfg = store.get('POS_CONFIG_NAME', '')
    reader = store.get('CREDIT_CARD_READER_TYPE', '')
    captured = None
    mj = os.path.join(report_dir, 'metadata.json')
    if os.path.isfile(mj):
        try:
            meta = json.load(open(mj, encoding='utf-8'))
            captured = datetime.fromisoformat(meta['capturedAt'].replace('Z', '+00:00'))
            out['version'] = meta.get('posVersion')
            out['store'] = meta.get('storeName')
            out['config'] = meta.get('configName')
        except (ValueError, KeyError, OSError):
            captured = None
    out.update({'config_name': cfg, 'reader_type': reader})
    ro = os.path.join(report_dir, 'offline-readonly.snapshot.db')
    if not os.path.isfile(ro):
        out['reason'] = '找不到 offline-readonly.snapshot.db'
        return out
    con = open_ro(ro)
    try:
        if not table_exists(con, 'pos_pilot'):
            out['reason'] = '資料庫沒有 pos_pilot'
            return out
        pilots = con.execute('SELECT name, start_at, end_at, version FROM pos_pilot ORDER BY name').fetchall()
        feats = defaultdict(list)
        for n, k in con.execute('SELECT pos_pilot_name, keyword FROM pos_pilot_lines_features'):
            feats[n].append(k)
        stores = defaultdict(set)
        for n, s, c in con.execute('SELECT pos_pilot_name, store_name, config_name FROM pos_pilot_lines_stores'):
            stores[n].add(f'{s}{c}')
    finally:
        con.close()
    now_ms = int(captured.timestamp() * 1000) if captured else int(datetime.now().timestamp() * 1000)
    matches = []
    for name, s, e, ver in pilots:
        if cfg and cfg in stores[name] and 'POSAgentDotNet' in feats[name]:
            matches.append({'name': name, 'start': datetime.fromtimestamp(s / 1000, TZ_TW).replace(tzinfo=None) if s else None,
                            'end': datetime.fromtimestamp(e / 1000, TZ_TW).replace(tzinfo=None) if e else None,
                            'in_window': bool(s and e and s <= now_ms < e), 'version_limit': ver or ''})
    enabled = any(m['in_window'] for m in matches) and reader != 'TSB'
    out.update({'present': True, 'matches': matches, 'enabled': enabled, 'pilot_total': len(pilots)})
    return out


# ---------------------------------------------------------------------------
# 5. 代理程式 log（選用）
# ---------------------------------------------------------------------------

RE_AGENT = re.compile(r'^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\.\d+ \+08:00 \[(\w+)\] (.*)$')
RE_AGENT_OUT = re.compile(r'台新交易 out\.dat 讀取完成（(\d+) bytes）: ([0-9A-Fa-f]+)')


def normalize_msg(msg):
    msg = re.sub(r'[0-9A-Fa-f]{40,}', '<HEX>', msg)
    return re.sub(r'\d+', 'N', msg)[:100]


def analyze_agent(agent_dir, onset_date):
    files = sorted(glob.glob(os.path.join(agent_dir, 'posagentdotnet-*.log')))
    if not files:
        return {'present': False, 'reason': f'{agent_dir} 內沒有 posagentdotnet-*.log'}
    pre, post = Counter(), Counter()
    per_day = defaultdict(Counter)
    versions = []
    events = []
    in_count = out_count = 0
    faulted = []
    for path in files:
        day = re.search(r'(\d{8})', os.path.basename(path)).group(1)
        day_iso = f'{day[:4]}-{day[4:6]}-{day[6:]}'
        for line in open(path, 'rb').read().decode('utf-8', 'replace').splitlines():
            m = RE_AGENT.match(line)
            if not m:
                continue
            d, t, lvl, msg = m.groups()
            key = (lvl, normalize_msg(msg))
            if onset_date and d >= onset_date.isoformat():
                post[key] += 1
            else:
                pre[key] += 1
            v = re.search(r'服務版本 (\S+?)[，,]', msg)
            if v:
                versions.append((d, t, v.group(1)))
            if 'Application is shutting down' in msg or 'POSAgentDotNet 已啟動' in msg:
                events.append((d, t, '停止' if 'shutting' in msg else '啟動'))
            if re.search(r'DeviceFaulted|刷卡功能已暫停|無法確認刷卡程式', msg):
                faulted.append((d, t, msg[:80]))
            if '台新交易 in.dat 已寫入' in msg:
                in_count += 1
            o = RE_AGENT_OUT.search(msg)
            if o:
                out_count += 1
                kind, code, detail = decode_outdat(bytes.fromhex(o.group(2)))
                per_day[day_iso][kind if kind != 'TEMPLATE' else f'TEMPLATE:{code}'] += 1
    new_types = [(k, v) for k, v in post.items() if k not in pre] if onset_date else []
    gone_types = [(k, v) for k, v in pre.items() if k not in post and v >= 5] if onset_date else []
    warn_types = sorted(((k, pre[k], post[k]) for k in set(pre) | set(post) if k[0] in ('WRN', 'ERR', 'FTL')),
                        key=lambda x: (-(x[1] + x[2]), x[0]))
    ver_changes = []
    last = None
    for d, t, v in versions:
        if v != last:
            ver_changes.append((d, t, v))
            last = v
    return {
        'present': True, 'files': len(files), 'versions': ver_changes, 'events': events,
        'per_day': per_day, 'new_types': new_types, 'gone_types': gone_types, 'warn_types': warn_types,
        'in_count': in_count, 'out_count': out_count, 'faulted': faulted,
    }


# ---------------------------------------------------------------------------
# 6. COM3 發票機探針（選用）
# ---------------------------------------------------------------------------

RE_PRN = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+) \+08:00 預檢 (.*)$')


def analyze_com3(agent_dir, onset_date):
    files = sorted(glob.glob(os.path.join(agent_dir, 'printer-serialdata-*.log')))
    if not files:
        return {'present': False}
    fmt = '%Y-%m-%d %H:%M:%S.%f'
    per_day = defaultdict(lambda: {'probe': 0, 'noresp': 0, 'lat': []})
    for path in files:
        day = re.search(r'(\d{8})', os.path.basename(path)).group(1)
        day_iso = f'{day[:4]}-{day[4:6]}-{day[6:]}'
        pending = None
        for line in open(path, 'rb').read().decode('utf-8', 'replace').splitlines():
            m = RE_PRN.match(line)
            if not m:
                continue
            ts = datetime.strptime(m.group(1), fmt)
            rest = m.group(2)
            if rest.startswith('0x10 0x04'):
                if pending is not None:
                    per_day[day_iso]['noresp'] += 1
                pending = ts
                per_day[day_iso]['probe'] += 1
            elif rest.startswith('回應') and pending is not None:
                per_day[day_iso]['lat'].append((ts - pending).total_seconds() * 1000)
                pending = None
    allp = sum(v['probe'] for v in per_day.values())
    nores = sum(v['noresp'] for v in per_day.values())
    lat = [x for v in per_day.values() for x in v['lat']]
    post_lat = [x for d, v in per_day.items() if onset_date and d >= onset_date.isoformat() for x in v['lat']]
    post_no = sum(v['noresp'] for d, v in per_day.items() if onset_date and d >= onset_date.isoformat())
    return {
        'present': True, 'per_day': per_day, 'probes': allp, 'noresp': nores,
        'median': statistics.median(lat) if lat else None,
        'slow': sum(1 for x in lat if x > 50),
        'post_max': max(post_lat) if post_lat else None, 'post_noresp': post_no,
        'post_probes': len(post_lat),
    }


# ---------------------------------------------------------------------------
# 7. 初判
# ---------------------------------------------------------------------------

def decide(R, flags):
    """彙整各項證據，給出初判、信心、理由與待人工確認項。"""
    ecr, pay, pilot, agent, com3 = R['ecr'], R['payments'], R['pilot'], R['agent'], R['com3']
    reasons, unknowns, nexts = [], [], []
    if not ecr.get('present'):
        return {'label': 'INCONCLUSIVE', 'title': '無法判定（缺 ECR log）', 'confidence': '低',
                'reasons': [ecr.get('reason', 'ECR log 不存在')],
                'unknowns': ['沒有 ECR log 就看不到刷卡機與 PC 之間的通訊，無法分辨線路與程式'],
                'next': ['請門市重新送出問題回報包（含 C:\\OMO\\assets\\ecr），或確認該機台是否改走其他刷卡機類型']}
    onset = ecr['onset']
    # 判斷「與其他事件相差幾天」時，用首次失敗的日期（比只看發病日更精確）
    onset_day = (onset['first_fail'].start.date() if onset and onset['first_fail'] else onset['date']) if onset else None
    mix = ecr['scope_mix']
    scope = ecr['scope_calls']
    link = sum(v for k, v in mix.items() if k in LINK_FAIL)
    term = mix.get('TERMINAL_REPLY', 0)
    link_rate = link / scope if scope else 0
    # 情況 A：ECR 沒有通訊問題，但帳務有多筆手 KEY 緊接在核准之後
    if link_rate < 0.2 and not onset and pay.get('present') and pay.get('approved_but_offline', 0) >= 3:
        return {'label': 'SOFTWARE_SUSPECT', 'title': '疑似程式／流程問題（刷卡機核准了，但仍有手 KEY）',
                'confidence': '中',
                'reasons': [f"ECR 通訊失敗率僅 {pct(link, scope)}，但有 {pay['approved_but_offline']} 筆金額相同的手 KEY 發生在 ECR 核准後 5 分鐘內，且該核准沒有入帳"],
                'unknowns': ['需查 Ragdoll 端在收到核准後為何顯示失敗（逾時、狀態判斷、代理程式回應）'],
                'next': ['對照 Ragdoll main log 與代理程式 log 同一時間的呼叫與回應']}
    # 情況 B：刷卡機有完整回覆但被拒絕／取消（不是線路問題）
    if term >= 3 and term > link and (onset or term / scope >= 0.15):
        return {'label': 'TERMINAL_SIDE', 'title': '刷卡機有回覆但交易被拒或取消（非線路問題）', 'confidence': '中',
                'reasons': [f'有完整回覆但回應碼非 0000 共 {term} 次（{pct(term, scope)}），多於通訊失敗 {link} 次'],
                'unknowns': ['需讀細項碼（ECR_Error_Code，位置 30～33）判斷是操作、授權還是卡片問題'],
                'next': ['解碼歸檔 out.dat 的細項碼並對照規格書 §2.10-J']}
    # 情況 B0：ECR 沒有持續性通訊故障
    if link_rate < 0.2 and not onset:
        return {'label': 'NO_ISSUE_IN_LOGS', 'title': 'ECR log 未見持續性通訊故障', 'confidence': '中',
                'reasons': [f'最近 14 天 ECR 通訊失敗率 {pct(link, scope)}，未偵測到發病點'],
                'unknowns': ['問題可能發生在 ECR log 涵蓋期間之外，或不在通訊層'],
                'next': ['確認回報包涵蓋的日期是否包含門市描述的故障時段', '查銀行端／刷卡機設定／店員操作']}
    # 情況 C：以通訊失敗為主
    level = '中'
    if link_rate >= 0.5:
        reasons.append(f'發病後通訊類失敗率 {pct(link, scope)}（{link}／{scope}）：刷卡機的結果沒有完整回到 POS')
    else:
        reasons.append(f'通訊類失敗率 {pct(link, scope)}（{link}／{scope}），屬間歇性')
    if onset:
        ff = onset['first_fail']
        lo = onset['last_ok']
        if ff and lo:
            reasons.append(f"發病點：最後一次正常 {lo.start:%m/%d %H:%M}，首次失敗 {ff.start:%m/%d %H:%M}")
        reasons.append(f"發病前基準：{onset['pre_fail']}／{onset['pre_calls']} 次失敗（{onset['pre_days']} 天有資料）")
    if ecr['ack_bad']:
        reasons.append(f"有 {len(ecr['ack_bad'])} 次「已收到刷卡機 ACK、結果卻損壞」＝請求有送達、回程損壞")
    sig = ecr['signature']
    if ecr['excess'] or ecr['noise'] or ecr['clean_between']:
        level = level_up(level)
        reasons.append(f'封包鑑識：{sig}')
        if ecr['clean_between']:
            reasons.append(f"乾淨的成功框夾在損壞封包之間 {ecr['clean_between']} 次，不是靜態設定不符")
    else:
        reasons.append(f'封包鑑識：{sig}')
    label = 'LINK'
    title = '硬體／線路（序列通訊層）'
    # 軟體疑慮修正項
    soft = []
    ig, tp = ecr['integrity'], ecr['templates']
    if ig['overlaps'] or ig['orphans']:
        soft.append(f"ECR log 區塊不完整：重疊或未結束 {ig['overlaps']} 個、區塊外殘留 {ig['orphans']} 行（可能有殭屍 ECR.exe 或兩個程序同時使用 COM1）")
    else:
        reasons.append(f"ECR log 區塊完整：{len(ecr['blocks'])} 個區塊無重疊、無區塊外殘留（無殭屍 ECR.exe 跡象）")
    if onset and tp['post_only']:
        soft.append(f"發病後有 {tp['post_only']} 次請求的封包樣板在發病前從未出現（送出的格式或內容變了）")
    elif onset and tp['pre_n'] and tp['post_n']:
        reasons.append('請求封包樣板發病前後一致（遮蔽調閱編號、金額、日期時間、櫃機號時戳後）：POS 送出去的內容沒變')
    if onset and ecr['nak_post']:
        reasons.append(f"ECR 發病後送出 NAK {ecr['nak_post']} 次（發病前 {ecr['nak_pre']} 次）：刷卡機的結果損壞，ECR 要求重送")
    rc = ecr['retry_checks']
    if rc:
        if all(r['gap'] == 0 for r in rc):
            reasons.append(f'{len(rc)} 次「刷卡機已收下請求、結果損壞、隨後同金額重試核准」的案例，調閱編號皆連號：失敗那次沒有佔用編號，無重複扣款跡象')
        else:
            unknowns.append(f"{sum(1 for r in rc if r['gap'] > 0)} 次「刷卡機已收下請求、結果損壞、隨後同金額重試核准」的調閱編號出現缺口，需以結帳單確認是否重複扣款")
    if agent.get('present'):
        healthy = True
        if agent['faulted']:
            healthy = False
            soft.append('代理程式出現暫停刷卡的閂鎖錯誤（DeviceFaulted）')
        new_bad = [k for k, v in agent['new_types'] if k[0] in ('WRN', 'ERR', 'FTL')]
        if new_bad:
            soft.append(f"代理程式在發病後出現 {len(new_bad)} 種新的警告／錯誤訊息類型")
            healthy = False
        if onset and agent['versions']:
            changes = agent['versions'][1:]
            if any(abs((datetime.strptime(d, '%Y-%m-%d').date() - onset_day).days) <= 3 for d, t, v in changes):
                soft.append('代理程式版本在發病前後 3 天內有變更')
                healthy = False
        if abs(agent['in_count'] - agent['out_count']) > 2:
            soft.append(f"代理程式 in.dat 寫入 {agent['in_count']} 次、out.dat 讀回 {agent['out_count']} 次，數量不一致")
            healthy = False
        if healthy:
            level = level_up(level)
            reasons.append('代理程式 log：發病後沒有新的警告／錯誤訊息、無版本變更、每次寫 in.dat 都有讀回 out.dat、無閂鎖錯誤')
    else:
        unknowns.append('未提供代理程式 log，無法確認代理程式端是否正常（建議向維運索取 C:\\ProgramData\\POSAgentDotNet\\logs）')
    if pilot.get('present') and pilot.get('enabled'):
        for m in pilot['matches']:
            if m['in_window'] and onset and m['start'] and abs((onset_day - m['start'].date()).days) <= 3:
                soft.append(f"種子名單 {m['name']}（改走代理程式）生效於 {m['start']:%m/%d %H:%M}，與發病日相差 3 天內")
    if com3.get('present'):
        if com3['noresp'] == 0 and (com3['post_max'] is None or com3['post_max'] < 100):
            reasons.append(f"COM3 發票機探針 {com3['probes']} 次 0 次無回應（發病後最大延遲 {com3['post_max']:.0f} ms）：PC 整體序列系統健康" if com3['post_max'] is not None
                           else f"COM3 發票機探針 {com3['probes']} 次 0 次無回應：PC 整體序列系統健康")
        else:
            soft.append(f"COM3 探針出現 {com3['noresp']} 次無回應或發病後延遲偏高，PC 序列系統可能不健康")
    else:
        unknowns.append('未提供 printer-serialdata log，無法用 COM3 驗證 PC 序列系統是否健康')
    if soft:
        label = 'SOFTWARE_SUSPECT'
        title = '有程式或系統層疑點，需先排除'
        level = '低' if len(soft) >= 2 else '中'
        reasons.extend(f'疑點：{s}' for s in soft)
    # 信心上限、使用者宣告與待確認項
    conf_table = None
    if label == 'LINK':
        # 「高」需要三項都到位：程式變更已排除、同店對照機台正常、代理程式 log 已檢視且無異常
        # 前兩項是使用者以旗標宣告的，腳本無法驗證，所以會明列在依據裡，報告要附上實際證據
        all_confirmed = flags['no_sw_change'] and flags['control_ok'] and agent.get('present')
        if all_confirmed:
            level = level_up(level)
        cap = '高' if all_confirmed else '中高'
        if CONF_LEVELS.index(level) > CONF_LEVELS.index(cap):
            level = cap
        declared = [t for ok, t in ((flags['no_sw_change'], '發病點前後無程式／版本變更（Step 3）'),
                                    (flags['control_ok'], '同店對照機台同期正常（Step 4）')) if ok]
        if declared:
            reasons.append('使用者宣告：' + '、'.join(declared) + '（腳本無法驗證，請在報告附上實際證據）')
        if not flags['no_sw_change']:
            unknowns.append('尚未確認「發病點前後沒有 Ragdoll／代理程式的版本或程式變更」（git tag 日期與模組 diff，見 SKILL Step 3）')
        if not flags['control_ok']:
            unknowns.append('尚未確認「同店其他機台同期正常」（中台對照，見 SKILL Step 4）')
        if not all_confirmed:
            nexts.append('完成上述人工確認後，帶 --no-sw-change --control-ok（並提供 --agent-logs）重跑可升為「高」')
        nexts.append('派人現場：重插傳輸線兩端、兩台重開機、用同店正常機台的線／刷卡機對調測試（定位線材／接頭／COM 埠／刷卡機）')
        layer = '高' if (link_rate >= 0.5 and onset) else '中'
        conf_table = [
            ('故障層在序列通訊層（ECR.exe 與刷卡機之間）', layer,
             f'發病後通訊類失敗率 {pct(link, scope)}；' + ('已確認請求有送達（ACK 後結果損壞）' if ecr['ack_bad'] else '尚無「ACK 後損壞」的直接證據')),
            ('Ragdoll／POSAgentDotNet／PC 系統層與故障無關', level, '以「未發現證據」表述，不是「排除」；潛伏性假設見報告 §6.1'),
            ('具體是線材、接頭、轉接頭、COM1 埠硬體或刷卡機該埠', '未知', '症狀相同，資料無法區分，需現場對調測試'),
        ]
    else:
        nexts.append('逐項處理上列疑點後再下結論；若疑點排除，回到「硬體／線路」判讀')
    if pay.get('present') and pay.get('pan_digits_only', 0) > 0:
        unknowns.append(f"另：手 KEY 離線刷卡中有 {pay['pan_digits_only']} 筆卡號欄位為未遮罩純數字（資安議題，與故障原因無關，見 SKILL 附帶風險）")
    return {'label': label, 'title': title, 'confidence': level, 'reasons': reasons, 'unknowns': unknowns,
            'next': nexts, 'conf_table': conf_table}


# ---------------------------------------------------------------------------
# 輸出
# ---------------------------------------------------------------------------

def render(R):
    L = []
    meta = R['pilot']
    head = f"# 刷卡機問題回報包診斷：{meta.get('store', '?')}／{meta.get('config') or meta.get('config_name') or '?'}"
    L.append(head)
    L.append('')
    L.append(f"- 回報包：`{R['report_dir']}`")
    L.append(f"- POS 版本：{meta.get('version', '?')}；刷卡機類型：{meta.get('reader_type', '?')}"
             + ('' if meta.get('reader_type') == 'TSB_ECR' else '（**非 TSB_ECR：本腳本只涵蓋台新 400B／ECR 路徑，僅部分章節適用**）'))
    V = R['verdict']
    L.append('')
    L.append(f"## 初判：{V['title']}（信心：{V['confidence']}）")
    L.append('')
    L.append('**依據**')
    for r in V['reasons']:
        L.append(f'- {r}')
    if V.get('conf_table'):
        L.append('')
        L.append('**信心表**')
        L.append(md_table(['判斷', '信心', '說明'], [list(r) for r in V['conf_table']]))
    if V['unknowns']:
        L.append('')
        L.append('**尚待確認 / 未知**')
        for u in V['unknowns']:
            L.append(f'- {u}')
    if V['next']:
        L.append('')
        L.append('**建議下一步**')
        for n in V['next']:
            L.append(f'- {n}')
    ecr = R['ecr']
    L.append('')
    L.append('---')
    L.append('')
    L.append('## 1. ECR 通訊紀錄')
    if not ecr.get('present'):
        L.append(f"略過：{ecr.get('reason')}")
    else:
        blocks = ecr['blocks']
        L.append(f"- {ecr['files']} 個 log 檔、{len(blocks)} 次 ECR 執行，期間 {blocks[0].start:%Y-%m-%d} ～ {blocks[-1].start:%Y-%m-%d}")
        on = ecr['onset']
        if on:
            ff, lo = on['first_fail'], on['last_ok']
            if lo and ff:
                L.append(f"- **發病日 {on['date']}**；最後正常 {lo.start:%Y-%m-%d %H:%M:%S}，首次失敗 {ff.start:%Y-%m-%d %H:%M:%S}")
            else:
                L.append(f"- **發病日 {on['date']}**（log 起點即異常，沒有「最後正常」可對照）")
            L.append(f"- 發病前 {on['pre_fail']}／{on['pre_calls']} 次失敗（{pct(on['pre_fail'], on['pre_calls'])}）；"
                     f"發病後 {on['post_fail']}／{on['post_calls']} 次失敗（{pct(on['post_fail'], on['post_calls'])}），成功 {on['post_approved']} 次")
        else:
            L.append('- 未偵測到「從好變壞」的發病點（可能一直異常、一直正常，或失敗率不到門檻）')
        days = sorted(ecr['daily'])
        shown = days[-45:]
        rows = [[d, ecr['daily'][d]['calls'], ecr['daily'][d]['approved'], ecr['daily'][d]['terminal'], ecr['daily'][d]['link'],
                 pct(ecr['daily'][d]['link'], ecr['daily'][d]['calls'])] for d in shown]
        L.append('')
        L.append('### 1.1 逐日結果' + ('（僅列最後 45 天）' if len(days) > 45 else ''))
        L.append(md_table(['日期', '呼叫', '成功', '刷卡機有回但非核准', '通訊類失敗', '失敗率'], rows))
        L.append('')
        L.append('### 1.2 失敗型態（發病後；未偵測到發病點時為最近 14 天）')
        mixrows = [[k, v, OUTCOME_HELP.get(k, '')] for k, v in ecr['scope_mix'].most_common()]
        L.append(md_table(['型態', '次數', '說明'], mixrows))
        if ecr['scope_codes']:
            L.append('')
            L.append('ECR.exe 自己記錄的錯誤：' + '；'.join(f'{k}×{v}' for k, v in ecr['scope_codes'].most_common()))
        L.append('')
        L.append('### 1.3 損壞封包鑑識')
        L.append(f"- 判讀：**{ecr['signature']}**")
        L.append(f"- 多於 403 bytes 的損壞串 {len(ecr['excess'])} 次；零星雜訊（≤16 bytes）{len(ecr['noise'])} 次；"
                 f"收到 ACK 但結果損壞 {len(ecr['ack_bad'])} 次；乾淨成功框夾在損壞之間 {ecr['clean_between']} 次")
        bad = ecr['bad'][:40]
        if bad:
            L.append('')
            L.append(md_table(['時間', '型態', '總位元組', 'ACK', '高位元組%', '有效前綴', 'ECR 錯誤'],
                              [[f'{b.start:%m/%d %H:%M:%S}', b.outcome, b.total, b.ack, pct(b.hi_ratio, 1), b.valid_prefix,
                                f'[{b.err_code}]' if b.err_code else '-'] for b in bad]))
            if len(ecr['bad']) > 40:
                L.append(f"（共 {len(ecr['bad'])} 筆，僅列前 40）")
    if ecr.get('present'):
        ig, tp = ecr['integrity'], ecr['templates']
        L.append('')
        L.append('### 1.4 區塊完整性、請求樣板與 NAK')
        L.append(f"- 區塊完整性：重疊或未結束 {ig['overlaps']}、區塊外殘留 {ig['orphans']}（檔尾未結束 {ig['unfinished']}）"
                 + ('' if not (ig['overlaps'] or ig['orphans']) else '　← **異常：可能有殭屍 ECR.exe 或兩個程序同時使用 COM1**'))
        if tp['pre_n'] or tp['post_n']:
            L.append(f"- 請求封包樣板（遮蔽調閱編號、金額、日期時間、櫃機號時戳）：發病前 {tp['pre_n']} 次共 {tp['pre_distinct']} 種；"
                     f"發病後 {tp['post_n']} 次共 {tp['post_distinct']} 種；發病後新出現的樣板 {tp['post_only_types']} 種（{tp['post_only']} 次）")
        L.append(f"- ECR 送出 NAK（要求重送損壞的結果）：發病前 {ecr['nak_pre']} 次、發病後 {ecr['nak_post']} 次")
        rc = ecr['retry_checks']
        if rc:
            L.append('')
            L.append('**重試風險檢查**（刷卡機已收下請求 ACK 但結果損壞，隨後同金額重試核准；看中間有沒有多佔用調閱編號）')
            L.append(md_table(['失敗時間', '重試核准', '金額', '前一筆成功編號', '重試編號', '缺口', '判讀'],
                              [[f'{r["failed_at"]:%m/%d %H:%M:%S}', f'{r["approved_at"]:%m/%d %H:%M:%S}', f'{r["amount"]:,.0f}',
                                r['prev_receipt'], r['new_receipt'], r['gap'],
                                '連號：失敗那次沒有佔用編號，無重複扣款跡象' if r['gap'] == 0
                                else '**有編號被佔用：可能是這次失敗已產生交易（重複扣款風險）或其他單的手 KEY，請對結帳單核實**'] for r in rc[:15]]))
    od = R['outdat']
    L.append('')
    L.append('## 2. 歸檔 out.dat（ecr/transmitted）')
    if not od.get('present'):
        L.append('略過：沒有 transmitted 資料夾')
    else:
        L.append(md_table(['種類', '檔案數'], [[k, v] for k, v in od['kinds'].most_common()]))
        L.append('')
        L.append('說明：`TEMPLATE:0001`／`TEMPLATE:0003` ＝整份只剩回應碼、細項碼（位置 30～33）為空，是中介在沒收到完整回覆時寫的固定範本；'
                 '`TERMINAL_REPLY` 才是刷卡機自己回報的結果（欄位有內容，常帶細項碼，例如 02XX＝主機授權失敗、03XX＝操作逾時、04XX＝使用者取消）。')
    pay = R['payments']
    L.append('')
    L.append('## 3. 本機帳務對帳（offline-mutable）')
    if not pay.get('present'):
        L.append(f"略過：{pay.get('reason')}")
    else:
        L.append(f"- 正常刷卡 {pay['ok_total']} 筆；手 KEY 離線刷卡 **{pay['offline_total']} 筆，NT$ {pay['offline_amount']:,}**"
                 + (f"；首筆手 KEY {pay['first_offline']:%Y-%m-%d %H:%M}" if pay['first_offline'] else ''))
        days = sorted(pay['daily'])[-30:]
        L.append('')
        L.append(md_table(['日期', '正常刷卡', '手 KEY', '手 KEY 金額'],
                          [[d, pay['daily'][d]['ok'], pay['daily'][d]['off'], f"{pay['daily'][d]['off_amt']:,}"] for d in days]))
        if pay['recon_rows']:
            L.append('')
            L.append('**調閱編號缺口 vs 手 KEY 筆數**（缺口＝刷卡機有交易但 POS 沒記到；兩者相等代表每筆手 KEY 都對應一筆刷卡機交易）')
            L.append(md_table(['成功編號', '下一筆成功', '缺口', '期間手 KEY', '是否吻合', '時間'],
                              [[r['from'], r['to'], r['gap'], r['offline'], recon_state(r), r['span']]
                               for r in pay['recon_rows'][:30]]))
            L.append('')
            L.append('說明：發病前「缺口大於手 KEY」多半是取消或被拒絕的交易也會佔用調閱編號，屬正常；'
                     '發病後若「手 KEY 多於缺口」，代表有手 KEY 的單並沒有對應的刷卡機交易（可能沒有真的刷卡，需查證）。')
        er = pay['est_receipt']
        if er:
            L.append('')
            L.append(f"- 最後一筆成功調閱編號 {er['last_receipt']}（{er['last_time']:%m/%d %H:%M}），之後 {er['offline_after']} 筆手 KEY；"
                     f"刷卡機目前編號預估約 **{er['estimate']}**（假設每筆手 KEY 對應一次刷卡機交易、無取消或重刷；請拿刷卡機結帳單核對）")
        L.append(f"- 同卡同金額重複輸入：{pay['dup_groups']} 組")
        if pay['offline_total']:
            L.append(f"- 手 KEY 的前因：{pay['offline_matched']}／{pay['offline_total']} 筆在前 10 分鐘內有金額相符的失敗 ECR 呼叫"
                     + (f"；{pay['offline_unmatched_n']} 筆找不到（可能是指定金額分次付款、沒先刷就直接手 KEY，或 ECR log 未涵蓋）" if pay['offline_unmatched_n'] else ''))
            if pay['offline_unmatched']:
                L.append(md_table(['找不到前因的手 KEY 時間', '金額'], [[f"{u['at']:%m/%d %H:%M:%S}", f"{u['amount']:,}"] for u in pay['offline_unmatched']]))
        L.append(f"- ECR 核准、金額相同、5 分鐘內仍手 KEY，且該核准沒有入帳：{pay['approved_but_offline']} 筆"
                 + ('（正常應為 0；≥3 筆會被判為疑似程式／流程問題）' if pay['approved_but_offline'] else ''))
        if pay['approved_but_offline_rows']:
            L.append(md_table(['ECR 核准時間', '手 KEY 時間', '金額'],
                              [[f"{r['approved_at']:%m/%d %H:%M:%S}", f"{r['offline_at']:%m/%d %H:%M:%S}", f"{r['amount']:,}"]
                               for r in pay['approved_but_offline_rows']]))
        L.append(f"- 手 KEY 的卡號欄位：未遮罩純數字 {pay['pan_digits_only']} 筆、含遮罩字元 {pay['pan_masked_like']} 筆、其他 {pay['pan_other']} 筆（不輸出內容）")
    pl = R['pilot']
    L.append('')
    L.append('## 4. 走哪條路徑（種子名單）')
    if not pl.get('present'):
        L.append(f"略過：{pl.get('reason', '資料不足')}")
    else:
        path = 'POSAgentDotNet 代理程式 → ECR.exe' if pl['enabled'] else 'Ragdoll 直連 → ECR.exe（未命中種子名單或機型不支援）'
        L.append(f"- 機台 `{pl['config_name']}`，刷卡機類型 `{pl['reader_type']}` → **{path}**")
        for m in pl['matches']:
            L.append(f"- 名單 `{m['name']}`：{m['start']:%Y-%m-%d %H:%M} ～ {m['end']:%Y-%m-%d}，{'生效中' if m['in_window'] else '不在有效期間'}"
                     + (f"，版本限制 {m['version_limit']}" if m['version_limit'] else ''))
        if not pl['matches']:
            L.append(f"- 本機同步的 {pl['pilot_total']} 筆種子名單中沒有命中此機台的 POSAgentDotNet 記錄")
    ag = R['agent']
    L.append('')
    L.append('## 5. 代理程式 log（POSAgentDotNet）')
    if not ag.get('present'):
        L.append('略過：未提供或找不到 `--agent-logs`')
    else:
        L.append(f"- {ag['files']} 個 log 檔；版本時間軸：" + '；'.join(f'{d} {t} 起 {v}' for d, t, v in ag['versions'][:6]))
        L.append(f"- 服務啟停事件 {len(ag['events'])} 次：" + '；'.join(f'{d} {t}{e}' for d, t, e in ag['events'][:12]))
        L.append(f"- in.dat 寫入 {ag['in_count']} 次、out.dat 讀回 {ag['out_count']} 次；暫停刷卡閂鎖錯誤 {len(ag['faulted'])} 次")
        rows = []
        for d in sorted(ag['per_day']):
            c = ag['per_day'][d]
            if any(k != 'OK' for k in c):
                rows.append([d, '、'.join(f'{k}×{v}' for k, v in sorted(c.items()))])
        if rows:
            L.append('')
            L.append('有失敗的日子（out.dat 解碼結果）：')
            L.append(md_table(['日期', '結果'], rows[-20:]))
        L.append('')
        L.append(f"- 發病後新增的訊息類型：{len(ag['new_types'])} 種；發病後消失的類型：{len(ag['gone_types'])} 種")
        for (lvl, msg), n in ag['new_types'][:8]:
            L.append(f'  - 新增 [{lvl}] {msg}（{n} 次）')
        if ag['warn_types']:
            L.append('')
            L.append('WRN／ERR 類型（前期次數／後期次數）：')
            for (lvl, msg), a, b in ag['warn_types'][:8]:
                note = '　（例行：Ragdoll 每次開機會呼叫 /release，不是故障觸發點）' if '外部要求釋放' in msg else ''
                L.append(f'  - [{lvl}] {msg}：{a}／{b}{note}')
    c3 = R['com3']
    L.append('')
    L.append('## 6. COM3 發票機探針（PC 序列系統健康檢查）')
    if not c3.get('present'):
        L.append('略過：沒有 printer-serialdata log')
    else:
        L.append(f"- 探測 {c3['probes']} 次，無回應 {c3['noresp']} 次，延遲中位數 {c3['median']:.1f} ms，>50ms 共 {c3['slow']} 次；"
                 + (f"發病後 {c3['post_probes']} 次探測最大延遲 {c3['post_max']:.0f} ms、無回應 {c3['post_noresp']} 次" if c3['post_max'] is not None else '未指定發病日，未分段'))
        L.append('- 限制：COM3 與刷卡機的 COM1 可能是不同轉接器，只能代表 CPU、作業系統、USB 主機等共用部分健康。')
    L.append('')
    L.append('---')
    L.append('')
    L.append('本報告由 triage.py 產生，僅為初判；請依 SKILL.md 的 Step 3（排除程式變更）與 Step 4（中台對照組）完成人工確認。')
    return '\n'.join(L)


def recon_state(r):
    if r['gap'] == r['offline']:
        return '是'
    return '缺口大於手 KEY（可能是取消／拒絕）' if r['gap'] > r['offline'] else '**手 KEY 多於缺口（需查證）**'


def to_jsonable(R):
    """JSON 輸出：只放摘要，不放原始位元組。"""
    ecr = R['ecr']
    ej = {'present': ecr.get('present')}
    if ecr.get('present'):
        on = ecr['onset']
        ej.update({
            'calls': len(ecr['blocks']), 'scope_calls': ecr['scope_calls'], 'mix': dict(ecr['scope_mix']),
            'signature': ecr['signature'], 'clean_between': ecr['clean_between'],
            'onset': ({'date': str(on['date']), 'first_fail': str(on['first_fail'].start) if on['first_fail'] else None,
                       'last_ok': str(on['last_ok'].start) if on['last_ok'] else None,
                       'pre_fail': on['pre_fail'], 'pre_calls': on['pre_calls'],
                       'post_fail': on['post_fail'], 'post_calls': on['post_calls']} if on else None),
        })
    pay = R['payments']
    pj = {k: v for k, v in pay.items() if k in ('present', 'offline_total', 'offline_amount', 'ok_total', 'pan_digits_only',
                                                  'dup_groups', 'approved_but_offline')}
    return {'report_dir': R['report_dir'], 'verdict': R['verdict'], 'ecr': ej, 'payments': pj,
            'pilot': {k: v for k, v in R['pilot'].items() if k in ('present', 'enabled', 'config_name', 'reader_type')}}


# ---------------------------------------------------------------------------
# 自我測試（合成資料，不需要真實回報包）
# ---------------------------------------------------------------------------

def _make_frame(data400):
    body = data400.encode('latin-1')
    assert len(body) == 400
    lrc = 0
    for c in body + b'\x03':
        lrc ^= c
    return b'\x02' + body + b'\x03' + bytes([lrc])


def _data(code='0000', receipt='000123', amount='000000012300'):
    """依規格書欄位位置組一份 400 bytes 的回應資料。"""
    buf = [' '] * 400
    for off, val in ((0, '11'), (4, receipt), (10, 'XXXXXX1234'), (33, amount), (45, '261001'),
                     (51, '123000'), (57, '123456789'), (78, code), (82, '12345678'), (259, 'Y')):
        buf[off:off + len(val)] = list(val)
    return ''.join(buf)


def _req_data(alt=False, amount='000000012300'):
    """請求封包資料；alt=True 模擬發病後格式被改動（在遮蔽範圍外多一個字元）。"""
    buf = [' '] * 400
    for off, val in ((0, '11'), (33, amount), (114, '090111791262950696')):
        buf[off:off + len(val)] = list(val)
    if alt:
        buf[200] = 'Z'
    return ''.join(buf)


def _chunks(ts, raw):
    return [f'{ts} Receive Data    [{len(raw[i:i + 8]):03d}]: {raw[i:i + 8].hex().upper()}' for i in range(0, len(raw), 8)]


def _write_logs(specs):
    """specs＝[(月/日, 時:分, 種類[, 選項])]。
    種類：ok／decline／silent／ackbad／garbled／noise／noend（沒有 END 的區塊）。
    選項：amount（12 位金額字串）、receipt（6 位調閱編號）、req='alt'（請求樣板被改）。回傳回報包暫存目錄。"""
    tmp = tempfile.mkdtemp(prefix='triage-selftest-')
    logdir = os.path.join(tmp, 'ecr', 'log')
    os.makedirs(logdir)
    lines = []
    for spec in specs:
        day, hhmm, kind = spec[:3]
        opts = spec[3] if len(spec) > 3 else {}
        amount = opts.get('amount', '000000012300')
        receipt = opts.get('receipt', '000123')
        req_hex = _make_frame(_req_data(opts.get('req') == 'alt', amount)).hex().upper()
        ok = _make_frame(_data('0000', receipt, amount))
        ts = f'2026/{day} {hhmm}:00'
        lines += [f'{ts} ============START===========', f'{ts} Send AllData    [403]: {req_hex}',
                  f'{ts} Send Message    [400]: 11   {amount}',
                  f'{ts} ErrRec Message  [61]: 3>4']  # 長度欄長得像錯誤碼，不得被誤判
        if kind == 'ok':
            lines += _chunks(ts, b'\x06\x06') + _chunks(ts, ok)
        elif kind == 'decline':
            lines += _chunks(ts, b'\x06\x06') + _chunks(ts, _make_frame(_data('0002', receipt, amount)))
        elif kind in ('silent', 'noend'):
            lines += [f'{ts} Send request again!', f'{ts} ' + '中介程式執行錯誤 [16]: 超過傳送的錯誤次數']
        elif kind == 'ackbad':
            lines += _chunks(ts, b'\x06\x06') + _chunks(ts, ok[:100] + b'\xb0\xf0' * 200)  # 100 + 400 > 403＝多出垃圾
            lines += [f'{ts} Send Message    [002]: <Nak><Nak>', f'{ts} ' + '中介程式執行錯誤 [17]: 超過接收的錯誤次數']
        elif kind == 'garbled':
            lines += _chunks(ts, b'\xf0\xb0\xe0\xfe' * 75)
            lines.append(f'{ts} ' + '中介程式執行錯誤 [17]: 超過接收的錯誤次數')
        elif kind == 'noise':
            lines += _chunks(ts, b'\xfe\xff')
            lines.append(f'{ts} ' + '中介程式執行錯誤 [17]: 超過接收的錯誤次數')
        if kind != 'noend':
            lines.append(f'{ts} ============END=============')
    with open(os.path.join(logdir, '001_20260920.log'), 'wb') as f:
        f.write('\n'.join(lines).encode('cp950', errors='replace'))
    return tmp


def _mkdb(rows):
    """建一個只含付款表的合成本機資料庫。rows＝[(本地時間 datetime, 型態, 金額, 調閱編號)]。"""
    tmp = tempfile.mkdtemp(prefix='triage-selftest-')
    con = sqlite3.connect(os.path.join(tmp, 'offline-mutable.snapshot.db'))
    con.execute('CREATE TABLE offline_sale_lines_payments (created_at INTEGER, type TEXT, amount INTEGER, '
                'receipt_no TEXT, reconcile_info TEXT, offline_sale_name TEXT)')
    for t, typ, amount, receipt in rows:
        con.execute('INSERT INTO offline_sale_lines_payments VALUES (?,?,?,?,?,?)',
                    (int(t.replace(tzinfo=TZ_TW).timestamp() * 1000), typ, amount, receipt,
                     'XXXXXX1234' if typ == 'CREDIT_OFFLINE' else '', 'S1'))
    con.commit()
    con.close()
    return tmp


def _healthy_days(first=10, last=19):
    out = []
    for d in range(first, last + 1):
        out += [(f'09/{d}', '10:00', 'ok'), (f'09/{d}', '15:00', 'ok')]
    return out


def _verdict(specs, agent=None, pay=None, flags=None):
    tmp = _write_logs(specs)
    R = {'ecr': analyze_ecr(tmp, None), 'payments': pay or {'present': False}, 'pilot': {'present': False},
         'agent': agent or {'present': False}, 'com3': {'present': False}}
    return R, decide(R, flags or {'control_ok': False, 'no_sw_change': False})


def selftest():
    # 基礎：分類、發病點、LRC、out.dat 解碼
    specs = _healthy_days() + [('09/20', h, 'silent') for h in ('10:00', '11:00', '12:00')] + [
        ('09/20', '13:00', 'ackbad'), ('09/21', '10:00', 'silent'), ('09/21', '11:00', 'ok'),
        ('09/21', '12:00', 'ackbad'), ('09/22', '10:00', 'silent'), ('09/22', '11:00', 'silent')]
    R, v = _verdict(specs)
    blocks = R['ecr']['blocks']
    got = Counter(b.outcome for b in blocks)
    assert got['APPROVED'] == 21 and got['SILENT'] == 6 and got['ACK_THEN_BAD'] == 2, got
    assert {b.err_code for b in blocks if b.err_code} == {'16', '17'}, 'ErrRec 長度欄被誤判成錯誤碼'
    on = R['ecr']['onset']
    assert on and str(on['date']) == '2026-09-20', on
    assert on['first_fail'].start.strftime('%m/%d %H:%M') == '09/20 10:00'
    assert R['ecr']['nak_post'] == 2 and R['ecr']['nak_pre'] == 0, (R['ecr']['nak_pre'], R['ecr']['nak_post'])
    assert R['ecr']['integrity'] == {'overlaps': 0, 'orphans': 0, 'unfinished': 0}, R['ecr']['integrity']
    assert R['ecr']['templates']['post_only'] == 0 and R['ecr']['templates']['pre_n'] == 20
    frame = _make_frame(_data())
    assert lrc_ok(frame) and not lrc_ok(frame[:-1] + b'\x00')
    assert analyze_stream(b'\x06\x06' + frame)['resp_code'] == '0000'
    assert analyze_stream(b'\x06\x06' + frame)['receipt'] == '000123'
    assert analyze_stream(b'\x06' + b'\xf0' * 30)['ack'] == 1  # 單一個 0x06 不算完整 ACK
    kind, code, _ = decode_outdat((' ' * 78 + '0001' + ' ' * 318).encode())
    assert (kind, code) == ('TEMPLATE', '0001'), (kind, code)
    assert parse_onset_arg('2026-10-01 12:42') == datetime(2026, 10, 1, 12, 42)
    assert parse_onset_arg('2026-10-01') == datetime(2026, 10, 1)

    # 情境 1：線路故障（含 ACK 後損壞、多出垃圾的封包鑑識）→ LINK；信心上限由人工確認項與代理程式 log 決定
    assert v['label'] == 'LINK' and v['confidence'] == '中高', v
    assert any('git tag' in u for u in v['unknowns']) and any('中台' in u for u in v['unknowns']), v['unknowns']
    assert v['conf_table'] and v['conf_table'][0][1] == '高' and v['conf_table'][2][1] == '未知', v['conf_table']
    _, v2 = _verdict(specs, flags={'control_ok': True, 'no_sw_change': True})
    assert v2['confidence'] == '中高', ('兩個旗標都帶但沒有代理程式 log，不得升為「高」', v2)
    assert any('使用者宣告' in r for r in v2['reasons']), v2['reasons']
    assert not any('重跑' in n for n in v2['next'] if '帶 --no-sw-change' in n and v2['confidence'] == '高'), v2['next']
    healthy_agent = {'present': True, 'faulted': [], 'new_types': [], 'versions': [], 'in_count': 10, 'out_count': 10}
    _, v3 = _verdict(specs, agent=healthy_agent, flags={'control_ok': True, 'no_sw_change': True})
    assert v3['label'] == 'LINK' and v3['confidence'] == '高', v3
    assert not any('重跑可升為' in n for n in v3['next']), ('旗標與代理程式 log 都到位後不該再建議重跑', v3['next'])
    _, v4 = _verdict(specs, agent=healthy_agent)  # 代理程式正常但缺人工確認 → 仍封頂中高
    assert v4['confidence'] == '中高', v4

    # 情境 2：健康機台（只有零星拒絕）→ 不得判成線路故障
    _, v = _verdict(_healthy_days() + [('09/20', '10:00', 'decline')])
    assert v['label'] == 'NO_ISSUE_IN_LOGS', v

    # 情境 3：刷卡機大量回覆拒絕 → TERMINAL_SIDE，不是線路
    _, v = _verdict(_healthy_days() + [('09/20', f'{h}:00', 'decline') for h in range(10, 16)])
    assert v['label'] == 'TERMINAL_SIDE', v

    # 情境 4：發病後全是亂碼、沒有任何乾淨的框 → 判讀為「靜態速率／格式不符型」
    R, v = _verdict(_healthy_days() + [('09/20', f'{h}:00', 'garbled') for h in range(10, 16)])
    assert R['ecr']['signature'].startswith('靜態速率'), R['ecr']['signature']

    # 情境 5：線路故障，但代理程式發病後出現新的錯誤訊息類型 → 必須改判為有程式疑點
    agent = {'present': True, 'faulted': [], 'new_types': [(('ERR', '台新交易失敗'), 3)], 'versions': [],
             'in_count': 10, 'out_count': 10}
    _, v = _verdict(specs, agent=agent)
    assert v['label'] == 'SOFTWARE_SUSPECT', v

    # 情境 6：ECR 全部核准，但帳務有多筆「金額相同、緊接在核准之後、且該核准沒有入帳」的手 KEY → 疑似程式／流程問題
    pay = {'present': True, 'approved_but_offline': 5, 'pan_digits_only': 0}
    _, v = _verdict(_healthy_days(), pay=pay)
    assert v['label'] == 'SOFTWARE_SUSPECT', v

    # 情境 7：沒有 ECR log → 無法判定
    R = {'ecr': analyze_ecr(tempfile.mkdtemp(prefix='triage-selftest-'), None), 'payments': {'present': False},
         'pilot': {'present': False}, 'agent': {'present': False}, 'com3': {'present': False}}
    assert decide(R, {'control_ok': False, 'no_sw_change': False})['label'] == 'INCONCLUSIVE'

    # 情境 8：資料損壞時只略過該章節，不得整份中斷
    bad = tempfile.mkdtemp(prefix='triage-selftest-')
    with open(os.path.join(bad, 'offline-mutable.snapshot.db'), 'wb') as f:
        f.write(os.urandom(2000))
    r = safe_run(analyze_payments, bad, None, None, what='帳務')
    assert r['present'] is False and '帳務分析失敗' in r['reason'], r
    with open(os.path.join(bad, 'offline-readonly.snapshot.db'), 'wb') as f:
        f.write(os.urandom(2000))
    r = safe_run(analyze_pilot, bad, what='種子名單')
    assert r['present'] is False, r

    # 情境 9：區塊沒有 END 又開始新區塊（殭屍 ECR.exe 或雙程序的跡象）→ 即使通訊失敗明顯，也要改判有程式／系統疑點
    R, v = _verdict([('09/10', '09:00', 'noend')] + specs)
    assert R['ecr']['integrity']['overlaps'] == 1, R['ecr']['integrity']
    assert v['label'] == 'SOFTWARE_SUSPECT', v

    # 情境 10：發病後請求封包樣板在發病前從未出現（送出的格式變了）→ 改判有程式疑點
    R, v = _verdict(_healthy_days() + [('09/20', f'{h}:00', 'silent', {'req': 'alt'}) for h in range(10, 16)])
    assert R['ecr']['templates']['post_only'] == 6, R['ecr']['templates']
    assert v['label'] == 'SOFTWARE_SUSPECT' and any('封包樣板' in r for r in v['reasons']), v

    # 情境 11：重試風險——ACK 後損壞、同金額重試核准；調閱編號連號＝沒佔用，出現缺口＝需對結帳單
    seq = [('09/10', '10:00', 'ok', {'receipt': '000010', 'amount': '000000010000'}),
           ('09/10', '11:00', 'ackbad', {'amount': '000000045600'}),
           ('09/10', '11:01', 'ok', {'receipt': '000011', 'amount': '000000045600'}),
           ('09/10', '12:00', 'ok', {'receipt': '000020', 'amount': '000000010000'}),
           ('09/10', '13:00', 'ackbad', {'amount': '000000078900'}),
           ('09/10', '13:01', 'ok', {'receipt': '000022', 'amount': '000000078900'})]
    R, _ = _verdict(seq)
    assert [r['gap'] for r in R['ecr']['retry_checks']] == [0, 1], R['ecr']['retry_checks']

    # 情境 12：「核准後手 KEY」必須金額相同、且該核准沒有入帳才算；先前版本會把「另一筆」誤報成疑點
    tmp = _write_logs([('09/10', '10:00', 'ok', {'amount': '000000012300'})])
    blocks, _, _ = parse_ecr_logs(os.path.join(tmp, 'ecr', 'log'))
    t0 = datetime(2026, 9, 10, 10, 0, 0)
    r = analyze_payments(_mkdb([(t0 + timedelta(minutes=2), 'CREDIT_OFFLINE', 123, '')]), None, blocks)
    assert r['approved_but_offline'] == 1, r['approved_but_offline']  # 核准了卻沒入帳、又手 KEY 同金額 → 疑點
    r = analyze_payments(_mkdb([(t0 + timedelta(seconds=30), 'CREDIT', 123, '000123'),
                                (t0 + timedelta(minutes=2), 'CREDIT_OFFLINE', 123, '')]), None, blocks)
    assert r['approved_but_offline'] == 0, r['approved_but_offline']  # 核准已正常入帳 → 不是疑點
    r = analyze_payments(_mkdb([(t0 + timedelta(minutes=2), 'CREDIT_OFFLINE', 352, '')]), None, blocks)
    assert r['approved_but_offline'] == 0, r['approved_but_offline']  # 金額不同（是另一筆）→ 不是疑點
    print('selftest 通過：分類、發病點、LRC、out.dat 解碼，以及 12 個判定、穩健性與帳務比對情境皆符合預期')


# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description='Ragdoll 刷卡機（台新 ECR）問題回報包診斷')
    ap.add_argument('report_dir', nargs='?', help='問題回報包目錄（production_issue-*）')
    ap.add_argument('--agent-logs', help='POSAgentDotNet log 目錄（含 posagentdotnet-*.log、printer-serialdata-*.log）')
    ap.add_argument('--onset', help='手動指定發病日 YYYY-MM-DD，或精確到 YYYY-MM-DD HH:MM（覆蓋自動偵測）')
    ap.add_argument('--control-ok', action='store_true', help='已用中台確認同店其他機台同期正常（Step 4）')
    ap.add_argument('--no-sw-change', action='store_true', help='已確認發病前後沒有程式／版本變更（Step 3）')
    ap.add_argument('--json', action='store_true', help='輸出 JSON 摘要而非 Markdown')
    ap.add_argument('--selftest', action='store_true', help='跑內建自我測試後結束')
    args = ap.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    if not args.report_dir or not os.path.isdir(args.report_dir):
        ap.error('請指定存在的回報包目錄')
    if args.onset:
        try:
            parse_onset_arg(args.onset)
        except ValueError as e:
            ap.error(str(e))
    rd = os.path.abspath(args.report_dir)
    ecr = safe_run(analyze_ecr, rd, args.onset, what='ECR log ')
    onset_date = ecr['onset']['date'] if ecr.get('present') and ecr['onset'] else None
    blocks = ecr.get('blocks') if ecr.get('present') else None
    R = {
        'report_dir': rd, 'ecr': ecr, 'outdat': safe_run(scan_outdat, rd, what='歸檔 out.dat '),
        'pilot': safe_run(analyze_pilot, rd, what='種子名單'),
        'payments': safe_run(analyze_payments, rd, onset_date, blocks, what='帳務'),
        'agent': safe_run(analyze_agent, args.agent_logs, onset_date, what='代理程式 log ') if args.agent_logs else {'present': False},
        'com3': safe_run(analyze_com3, args.agent_logs, onset_date, what='COM3 探針') if args.agent_logs else {'present': False},
    }
    R['verdict'] = decide(R, {'control_ok': args.control_ok, 'no_sw_change': args.no_sw_change})
    if args.json:
        print(json.dumps(to_jsonable(R), ensure_ascii=False, indent=2, default=str))
    else:
        print(render(R))
    return 0


if __name__ == '__main__':
    sys.exit(main())
