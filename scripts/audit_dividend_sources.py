"""Reproduce raw Yahoo date reconciliation; stdout JSON, no secrets or files.

python -m scripts.audit_dividend_sources ITC.NS
Contains the pre-fix UTC/exact-date path for evidence, never for application use.
"""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from src.providers.yahoo import _normalize_history_index, _merge_dedicated_action_series


def _rows(series):
    return [{"timestamp": str(date), "value": float(value)} for date, value in series[series.ne(0)].items()]


def audit(ticker, raw_json=False):
    obj = yf.Ticker(ticker)
    raw = obj.history(period="max", interval="1d", auto_adjust=False, actions=True, repair=True)
    if raw.empty:
        raise LookupError("Provider history unavailable")
    dividend = obj.dividends
    splits = obj.splits
    timezone_name = obj.history_metadata.get("exchangeTimezoneName") or str(raw.index.tz)
    normalized, _ = _normalize_history_index(raw, timezone_name)
    fixed, notes = _merge_dedicated_action_series(normalized, obj, timezone_name)
    # Exact original defect; both endpoints are truncated to UTC calendar day.
    old = raw.copy()
    old.index = pd.to_datetime(old.index, utc=True).tz_convert(None).normalize()
    old = old.groupby(level=0).last()
    for series, column in ((dividend,"Dividends"),(splits,"Stock Splits")):
        dedicated = series.copy()
        dedicated.index = pd.to_datetime(dedicated.index,utc=True).tz_convert(None).normalize()
        dedicated = dedicated[dedicated.ne(0)].groupby(level=0).last()
        old = old.reindex(old.index.union(dedicated.index).sort_values())
        for date, amount in dedicated.items():
            if pd.isna(old.loc[date,column]) or old.loc[date,column] == 0:
                old.loc[date,column] = amount
    evidence = {"ticker": ticker,"retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
        "yfinance_version":yf.__version__,"exchange_timezone":timezone_name,
        "history_dividends":_rows(raw.Dividends),"dedicated_dividends":_rows(dividend),
        "history_splits":_rows(raw['Stock Splits']),"dedicated_splits":_rows(splits),
        "baseline_annual_all_action_rows":old.Dividends.groupby(old.index.year).sum().to_dict(),
        "baseline_annual_price_rows":old.loc[old.Close.notna(),'Dividends'].groupby(old.loc[old.Close.notna()].index.year).sum().to_dict(),
        "corrected_annual":fixed.Dividends.groupby(fixed.index.year).sum().to_dict(),
        "latest_observation":str(normalized.index.max().date()),
        "latest_close":float(normalized.Close.iloc[-1]),"reconciliation_notes":notes,
        "audit":fixed.attrs['action_audit']}
    raw_evidence = json.dumps({key:evidence[key] for key in ('history_dividends','dedicated_dividends','history_splits','dedicated_splits')},sort_keys=True)
    evidence['raw_event_sha256'] = hashlib.sha256(raw_evidence.encode()).hexdigest()
    if raw_json:
        chart = obj._data.get_raw_json(f'https://query2.finance.yahoo.com/v8/finance/chart/{ticker}',
            params={'period1':0,'period2':int(time.time()),'interval':'1d','events':'div,splits'})['chart']['result'][0]
        evidence['underlying_chart_events'] = chart.get('events',{})
        evidence['underlying_exchange_timezone'] = chart['meta'].get('exchangeTimezoneName')
        # Private yfinance transport API is diagnostic-only; no cookie/header,
        # request-identification value or other configuration is serialized.
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ticker')
    parser.add_argument('--raw-json', action='store_true', help='Include actual public chart event IDs (one additional provider request)')
    args = parser.parse_args()
    print(json.dumps(audit(args.ticker,args.raw_json),indent=2))
