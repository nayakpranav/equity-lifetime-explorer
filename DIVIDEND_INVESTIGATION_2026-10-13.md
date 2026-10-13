# Dividend-data investigation — 13 October 2026

## Scope and baseline

GitHub `main` is `08946a7f6cf4526ab14c4e06302a42ac7919298a`.
Isolated correction branch: `bugfix/dividend-session-reconciliation`, based
directly on that production baseline. The unfinished A.2 branch remains
`feature/global-financials-release-a2` at
`fdfdb024464ac845122d63dccba7677e4cd621b5`; no A.2 files were imported,
modified, discarded or merged. Historical A/A.1 branches were also preserved.
This correction must not deploy or merge without the owner's authorization.

The uploaded dividend report was parsed, including its Plotly data rather than
just the visible summary. Report SHA-256:
`d38fb9bb17d6d4bcdcb4ffdb56506f842bb774825223feb7c34e0eaa3eb89a0a`.
Its retrieval timestamp is `2026-10-13T07:45:20.234369+00:00`.
It shows 2025 dividends 28.70 / four sessions and 2026 YTD 21.00 / three
sessions. The TTM trace has May25=28.70, May26=36.70, May28=21.00 and no
May27 observation. HIGH was an internal market-data assessment, not independent
issuer confirmation. Original deterministic baseline: **93 passed**.

## Reproduced root cause — not an assumed adjustment factor

Live investigation used yfinance 1.7.0 with max daily history, `auto_adjust=False`,
`actions=True`, `repair=True`, dedicated dividends/splits and actual chart JSON
event IDs. Exchange timezone is Asia/Kolkata.

| View of the same 2025 interim event | Timestamp | Original UTC calendar truncation |
|---|---|---|
| Daily history | 2025-02-12 00:00 +05:30 | February 11 |
| Dedicated dividends | 2025-02-12 09:15 +05:30 | February 12 |

Both amounts are 6.50. Exact-date reconciliation treated the dedicated row as
missing and inserted another event on the next date. Actual chart JSON has only
one event ID `1739331900` for this payment. The other disputed raw IDs are
`1748403900` (2025-05-28, 7.85), `1770176700` (2026-02-04, 6.50), and
`1779853500` (2026-05-27, 8.00).

The pre-fix path reproduced 28.70 for 2025. In 2026, the merged action rows sum
to 29.00, but the dividend analytics originally discarded an inserted event row
without Close. The price-row path reproduces the report's exact 21.00, not 29.00.
This agrees with the report's absent May27 point: one extra 6.50 was counted,
while the inserted duplicate 8.00 lacked a price. A deterministic gap fixture
also reproduces this path. No amount was divided blindly by two.

The same defect duplicated the three split-equivalent records. Their actual
ratios are 10:1 (2005-09-21), 2:1 (2010-08-03), and 3:2 (2016-07-01).
The correct product is 30, not the duplicated product 900. The 2016 record is
an issuer-declared 1-for-2 bonus; the existing engine treats it as split-equivalent.
Correcting these action inputs necessarily corrects affected ownership/raw-price
outputs. **No reconstruction or return formula was changed.** U.S. cases whose
UTC/local dates already matched retain their historical reconstruction inputs.

Reproduction command (stdout JSON, no configuration/headers serialized):

```bash
python -m scripts.audit_dividend_sources ITC.NS --raw-json
```

Executed snapshot: `2026-10-13T08:33:52.676872+00:00`, raw event digest
`36e6f2ccc3fc8bdefa7d55a2b3120f3d680312395ae274efff921e2d95fb6c02`.
The compact observed-event fixture is in
`tests/fixtures/itc_dividend_observations.json`. It contains 37 dividends and
three split records, with raw timestamp conventions and sample chart event IDs.

## Generalized correction

- Convert aware timestamps to the verified exchange timezone, then remove
  timezone information. Naive session labels are not interpreted as UTC.
  DST and local New Year boundaries are covered. Unknown timezone is flagged.
- Two Yahoo views agreeing on a local session/aggregate amount count once.
  Adjacent equal-amount events stay distinct. Different same-date cash
  components may sum (final plus special). Ambiguous repeated records and
  source disagreements are withheld from dedicated fallback, retaining history
  and a warning instead of averaging, scaling or blindly summing sources.
- Raw history/dedicated timestamps, values, normalized dates and decisions
  remain in `AnalysisResult.action_audit`, the UI and complete ZIP audit CSV.
- Legitimate dividends lacking a trading close remain in canonical annual/TTM
  event calculations. Price/yield for that event date is missing, not invented.
  Existing 365-day windows, CAGR, completed-year exclusions, frequency rules,
  split-consistent yield and Adjusted Close total-return formulas are unchanged.
- Both provider-file and Streamlit result caches have an explicit new action
  data version. Hot-reloaded legacy session results/prepared downloads are also
  invalidated with a request to Analyze again, rather than serving old values.
  Old cache files are not destructively deleted.

## Independent evidence and corrected ITC results

The reviewed benchmark registry is **validation-only**, not an override or
an ITC-specific multiplier. Exact listing, currency, interval and share basis
are checked. Subsequent genuine splits translate reference units, never rewrite
provider observations. A split inside an aggregate reference period withholds
that comparison pending event-level evidence. Missing external references are
explicit INFO states; source conflicts remain warnings/errors.

| Ex-date calendar year | Correct amount (INR/current-share basis) | Positive ex-date sessions |
|---|---|---|
| 2020 | 10.15 | 1 |
| 2021 | 10.75 | 2 |
| 2022 | 11.50 | 2 |
| 2023 | 15.50 | 2 |
| 2024 | 13.75 | 2 |
| 2025 | 14.35 | 2 |
| 2026 reviewed YTD through October 13 | 14.50 | 2 |

2023 preserves interim 6.00 and final 6.75 plus special 2.75 on one ex-date;
Yahoo correctly aggregates the latter as 9.50. There are two ex-date sessions,
not two declared dividend components. Calendar dates are not company fiscal
year labels or actual payment dates; in these reviewed cases the interim/final
payments for the cited fiscal year were ex-dated in the same calendar year.

Corrected metric snapshot from actual provider result retrieved
`2026-10-13T08:30:51.640205+00:00`, latest market observation October 13:

- TTM dividend 14.50; latest observed raw price 259.3500061035156 INR;
  TTM yield 5.590900196166776%. This is a contemporaneous/intraday price-based
  yield, not an issuer-declared yield or a hardcoded current-price expectation.
- Latest completed annual growth: 4.363636%; 3Y CAGR: 7.659251%;
  5Y CAGR: 7.170973%; 10Y CAGR: 13.163484% using provider-rounded 2015
  current-share-equivalent dividend basis 4.166667. The declared 2015 dividend 6.25 and subsequent bonus
  independently reconcile that historical dividend basis.
- Full provider history: 37 positive ex-date sessions; inferred frequency
  Semiannual; 2025 CAGR endpoint. Current YTD 14.50 versus prior-year same
  period 14.35. Eight reviewed independent intervals, including 2015, pass.
- Historical observations outside those benchmark intervals remain provider
  observations, not universally independently verified financial facts.

Primary evidence:

- [ITC 2026 approved/paid dividends and record dates](https://itcportal.com/investors/general-information.html)
- [ITC 2025 exchange disclosure, including prior-year amounts](https://www.itcportal.com/about-itc/shareholder-value/pdf/lodr-22may25e.pdf)
- [NSE corporate actions: final/special same-date disclosure](https://www.nseindia.com/companies-listing/corporate-filings-actions?symbol=ITC&tabIndex=sme)
- [ITC 2023 final/special announcement](https://itcportal.com/media-centre/press-releases/media-statement---financial-results-for-the-quarter-ended-31st-m.html)
- [ITC 2022 issuer FAQ](https://www.itcportal.com/about-itc/shareholder-value/key-financials/q1fy23results-faq.pdf)
- [ITC 2021 issuer announcement](https://itcportal.com/media-centre/press-releases/media-statement---financial-results-for-the-quarter-and-year-end.html)
- [ITC 2020 issuer announcement](https://itcportal.com/media-centre/press-releases/financial-results-for-the-quarter-and-year-ended-31st-march--202.html)
- [ITC 2015 declared amount](https://itcportal.com/media-centre/press-releases/financial-results-for-the-year-ended-31st-march--2015-.html)
- [ITC 2016 bonus terms](https://www.itcportal.com/about-itc/shareholder-value/pdf/postal-ballot-2016.pdf)
- [Costco SEC disclosure confirming its genuine 15.00 special dividend](https://www.sec.gov/Archives/edgar/data/909832/000090983224000017/cost-20240218.htm)

## Regression and release gate

The existing full deterministic suite and opt-in SEC/Yahoo suite are retained.
New cases cover observed ITC amounts, TTM/yield/CAGRs/frequency/counts, local
calendar/DST/year boundaries, same-date final/special components, adjacent equal
payments, conflicts, ambiguous duplicates, missing price observations, external
mismatches, reference currency/share basis, stale cache identity, visible UI/HTML
warnings, and split/reverse-split/bonus-equivalent reconciliation.

Live matrix adds ITC.NS, INFY.NS, TCS.NS, HDFCBANK.NS, COST, MC.PA and ASML.AS.
The retained matrix covers NVDA/GOOG/AAPL/MSFT/KO/BRK-B/SAP.DE/RELIANCE.NS and
AVGO/BRK-B exports, plus the original SEC pilot/generalized issuer matrices.
New checks compare reconstructed columns with authoritative history-only local
inputs; special dividends remain present. Specialist/Combined HTML, annual and
historical CSV, selected ZIP and complete packages remain on-demand. Complete
packages now include the audit; selected output behavior/filenames remain stable.

No financial-fundamentals concept mapping, ratio, quarterly normalization,
financial-source routing or A.2 implementation was changed. No production merge,
deployment, secret modification, reboot, cache deletion or Git history rewrite.
Final test/CI results and pull-request reference are recorded at the review
checkpoint; this document does not authorize deployment.

Local Python 3.11.17 results:

- Complete enabled suite: **142 passed**, including all **29 live** SEC/Yahoo
  integrations, with no skipped tests or unavailable live checks in that run.
- Subsequent UI-only hot-reload guard adds one regression; final deterministic
  suite: **114 passed**, with the 29 integration tests explicitly deselected.
  The live retrieval/calculation code is unchanged by that final UI guard;
  those executed live results are reused, not claimed as re-executed.
- Compile/import, local headless Streamlit startup and health endpoint passed.
- Scope comparison confirms reconstruction, corporate-action mathematics,
  volume, lifetime analytics and all financial-fundamentals source files are
  unchanged. Verified input corrections necessarily alter affected outputs.
- Public-artifact scan passed: no private SEC contact, credentials, local paths,
  environment/secrets files or caches in the candidate commit.
- An intermediate Windows pytest temp-directory ownership error was resolved
  using a unique test-only base directory. A no-dividend UI fixture was updated
  to identify a current-version result; a separate test rejects legacy sessions.
  No source-validation warning was suppressed to satisfy tests.

Limitations: Yahoo views are not independent sources; verified external reference
coverage is deliberately limited, not a universal official dividend feed.
Undisclosed/custom date conventions and ambiguous same-session facts require
review. The raw-json diagnostic uses a private yfinance transport API tested
with version 1.7.0; it is not a production dependency. Quotes/history and
provider repairs can change retrospectively. No dividend declaration is inferred
from price movements or from doubling/halving patterns.
