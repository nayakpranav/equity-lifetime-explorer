"""Opt-in serial SEC coverage evidence; identification comes only from environment.

Run from the repository with: python -m scripts.validate_sec_coverage
Writes public, numerical coverage evidence, never raw headers or configuration.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

from src.models import CompanyMetadata
from src.research_service import run_fundamentals_analysis
from src.financial_exports import fundamentals_html

PILOTS = ("MSFT", "KO", "AAPL", "NVDA", "MELI", "CAT", "HD", "DE", "META", "JPM", "BRK.B", "SAP.DE")
METRICS = ("revenue", "gross_profit", "operating_income", "net_income_parent", "eps_basic", "eps_diluted",
           "ocf", "capex_ppe", "fcf", "cash_equivalents", "assets", "liabilities", "current_assets",
           "current_liabilities", "shareholders_equity", "reported_long_term_debt", "long_term_debt_noncurrent",
           "long_term_debt_current", "short_term_borrowings", "commercial_paper", "roe", "roce")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=PILOTS)
    parser.add_argument("--output", default="exports/sec-a1-coverage.csv")
    args = parser.parse_args()
    rows = []
    for ticker in args.tickers:
        metadata = CompanyMetadata(ticker, ticker, ticker, "US", "USD", security_type="EQUITY")
        result = run_fundamentals_analysis(metadata)
        print(f"{ticker}: {result.status}; annual={len(result.annual)}, quarterly={len(result.quarterly)}", flush=True)
        if result.available:
            report = fundamentals_html(result)
            assert report.count(b"https://cdn.plot.ly/") == 1
            assert b"<td>NaN</td>" not in report
        for frequency, frame in (("annual", result.annual), ("quarterly", result.quarterly)):
            for metric in METRICS:
                valid = frame.loc[frame[metric].notna()] if metric in frame else pd.DataFrame()
                rows.append({"ticker": ticker, "cik": result.identity.cik if result.identity else None,
                             "status": result.status, "frequency": frequency, "metric": metric,
                             "observations": len(valid), "first_period": valid.period_end.min() if not valid.empty else None,
                             "last_period": valid.period_end.max() if not valid.empty else None,
                             "source_tags": ", ".join(sorted(valid[f"{metric}_source_tag"].dropna().unique())) if not valid.empty and f"{metric}_source_tag" in valid else "",
                             "retrieved_at_utc": result.retrieved_at_utc, "reason": result.reason})
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)


if __name__ == "__main__":
    main()
