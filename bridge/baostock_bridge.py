#!/usr/bin/env python3
"""One JSON per invocation. No indicators or trading decisions; SDK diagnostics -> stderr."""
import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import socket
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

class ProviderError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)

def rows(result):
    if result.error_code != '0':
        raise ProviderError('PROVIDER_ERROR', f'{result.error_code}: {result.error_msg}')
    output = []
    while result.next():
        output.append(dict(zip(result.fields, result.get_row_data())))
    if result.error_code != '0':
        raise ProviderError('PROVIDER_ERROR', f'{result.error_code}: {result.error_msg}')
    return output

def parse_code(value):
    match = re.fullmatch(r'(\d{6})(?:\.(SH|SZ|BJ))?', value.strip().upper())
    if not match:
        raise ProviderError('INVALID_SECURITY', '请输入六位普通 A 股代码，可带 .SH/.SZ/.BJ')
    return match.groups()

def resolve(master, value):
    code, suffix = parse_code(value)
    candidates = [x for x in master if x['code'].split('.')[-1] == code and x.get('type') == '1'
                  and (suffix is None or x['code'].split('.')[0].upper() == suffix)]
    # Provider stock type includes B shares; documented ordinary A share boards only.
    candidates = [x for x in candidates if re.fullmatch(r'(sh\.(60|68)\d{4}|sz\.(00|30)\d{4}|bj\.\d{6})', x['code'])]
    if len(candidates) != 1:
        if suffix == 'BJ':
            raise ProviderError('MARKET_COVERAGE_UNAVAILABLE', 'BaoStock 主数据未提供可确认的北交所普通股身份/历史行情')
        raise ProviderError('INVALID_SECURITY', '供应商主数据未唯一匹配普通 A 股；未猜测交易所')
    record = candidates[0]
    exchange = record['code'].split('.')[0].upper()
    return dict(canonicalCode=f'{code}.{exchange}', sixDigitCode=code, name=record['code_name'],
                exchange=exchange, type='COMMON_A', listStatus='LISTED' if record['status']=='1' else 'DELISTED',
                ipoDate=record.get('ipoDate'), outDate=record.get('outDate'), providerCode=record['code'],
                provider='baostock', sourceRecord=record)

def master_data(bs, root):
    path = root / 'security-master.json'
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    if path.exists():
        cached = json.loads(path.read_text())
        if cached.get('date') == today:
            return cached['rows']
    data = rows(bs.query_stock_basic())
    if not data:
        raise ProviderError('EMPTY_MASTER', '证券主数据为空')
    root.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(date=today, rows=data), ensure_ascii=False))
    temp.replace(path)
    return data

def execute(bs, args):
    fetched = datetime.now(ZoneInfo('Asia/Shanghai'))
    master = master_data(bs, Path(args.cache))
    identity = resolve(master, args.code)
    common = dict(provider='baostock', providerVersion=importlib.metadata.version('baostock'),
                  fetchedAt=fetched.isoformat(), identity=identity)
    if args.command == 'resolve':
        return common
    # Java fixes the requested horizon from the report's submission time.
    end = min(fetched.date(), date.fromisoformat(args.end)) if args.end else fetched.date() - timedelta(days=1)
    policy = 'SESSION_AWARE_BAOSTOCK_R1' if args.end else 'PRIOR_SHANGHAI_DATE_ONLY'
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=730)
    code = identity['providerCode']
    fields = 'date,code,open,high,low,close,volume,amount,adjustflag,tradestatus'
    raw = rows(bs.query_history_k_data_plus(code, fields, start_date=str(start), end_date=str(end), frequency='d', adjustflag='3'))
    qfq = rows(bs.query_history_k_data_plus(code, fields, start_date=str(start), end_date=str(end), frequency='d', adjustflag='2'))
    calendar = rows(bs.query_trade_dates(start_date=str(start), end_date=str(fetched.date()+timedelta(days=40))))
    factors = rows(bs.query_adjust_factor(code, start_date=str(start), end_date=str(end)))
    common.update(raw=raw, qfq=qfq, calendar=calendar, adjustmentEvents=factors,
                  requestedStart=str(start), requestedEnd=str(end), finalityPolicy=policy,
                  adjustmentSemantics='SPARSE_PROVIDER_EVENTS_WITH_DERIVED_OHLC_RATIOS', requestedAt=fetched.isoformat())
    common['sourceHash'] = hashlib.sha256(json.dumps(common, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return common

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command', choices=['resolve','snapshot'])
    parser.add_argument('--code', required=True)
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--cache', default=str(Path(__file__).resolve().parents[1]/'data/bridge'))
    args=parser.parse_args()
    try:
        parse_code(args.code)
        # Public API responses can be slow; Java bounds the entire child to 180s.
        socket.setdefaulttimeout(60)
        with contextlib.redirect_stdout(sys.stderr):
            import baostock as bs
            login=bs.login()
            if login.error_code != '0':
                raise ProviderError('PROVIDER_UNAVAILABLE', f'BaoStock login: {login.error_code}')
            try:
                result=execute(bs,args)
            finally:
                bs.logout()
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except ProviderError as exc:
        print(json.dumps(dict(error=dict(code=exc.code,message=exc.message,stage='MARKET',retryable=exc.code not in ['INVALID_SECURITY','MARKET_COVERAGE_UNAVAILABLE'])),ensure_ascii=False))
        return 2
    except Exception as exc:
        print(json.dumps(dict(error=dict(code='PROVIDER_UNAVAILABLE',message=type(exc).__name__,stage='MARKET',retryable=True))))
        return 2
    return 0
if __name__=='__main__':
    sys.exit(main())
