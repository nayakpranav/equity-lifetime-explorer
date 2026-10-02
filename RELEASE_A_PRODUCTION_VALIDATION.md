# Release A production validation — 2026-10-02

Release A was merged through [PR #1](https://github.com/nayakpranav/equity-lifetime-explorer/pull/1)
from `feature/financial-fundamentals-release-a` at
`2b9b3b13857bb59b2ed9be1d9231f1a51194f81b`. The production merge commit
is `434e5e3845316bf5efb73dd1a2fb42632ae3f9a8`; its first parent is the
previous production baseline `07f9c8507c30437965ecf21022523e047b3e8db6`.
The existing [production app](https://equity-lifetime-explorer.streamlit.app/)
deploys `main/app.py`. The separate
[review app](https://equity-lifetime-explorer-release-a-review.streamlit.app/)
and feature branch remain available.

## Release gates and production smoke

- PR head, base, mergeability and changed-file scope were checked before the
  merge. GitHub Actions `tests` passed on the validated feature head. The
  established baseline was 74 deterministic tests and 15 opt-in live
  SEC/Yahoo tests, plus compile/import, local startup and hosted staging checks.
- The production app automatically fetched the merge. Its in-place hot reload
  briefly logged import errors while files were being replaced; a fresh
  process provisioned, the page loaded cleanly, and subsequent live analyses
  succeeded. No reboot, corrective code change or rollback was required.
- Production MSFT retrieved SEC Company Facts and submissions. Annual and
  quarterly statements, revenue/profitability, operating cash flow, verified
  PPE-basis free cash flow, basic/diluted EPS and growth, parent ROE, qualified
  ROCE, balance-sheet charts, and the 5Y historical display filter rendered.
  The default-off split-adjusted price overlay appeared on Revenue, EPS and
  FCF when selected. The UI states that fiscal-period-end price alignment is
  **not** a financial-disclosure/availability date.
- Price & Ownership, Volume & Liquidity, and Dividends & Total Return rendered
  from the same production analysis. The Volume workspace labelled a
  pre-close cached bar **preliminary intraday RVOL**, with its partial-volume
  explanation. Completed and unverified classifications were covered by
  deterministic and staging checks. Market Data Quality and Financial Data
  Quality remained separate.
- Production KO retrieved SEC data; its pre-FY2016 mapped revenue cells were
  empty/unavailable, not zero. AAPL rendered SEC financials and qualified
  ratios. NVDA's latest PPE-based FCF card read **Not available**. SAP.DE
  showed an explicit unsupported SEC mapping while its EUR-denominated Price
  workspace remained functional.
- From a real SEC-populated MSFT result, Download Center generated a selected
  ZIP containing Financial Fundamentals HTML, Combined Research HTML and five
  financial CSVs. The Complete Analysis Package also prepared successfully.
  Earlier staging/live checks parsed CDN and portable HTML, CSV and ZIP
  contents, including formatted financial tables, missing markers, the chart
  sections and a single Plotly loader. Export generation remained on demand.
- The production app's private SEC operator setting worked. No contact value,
  credentials, local private paths, `.env`, or Streamlit secrets were found in
  tracked files. The operator contact was not displayed in the hosted UI or
  found in the previously inspected public exports.

## Interpretation and rollback boundary

SEC figures are **latest-disclosed** historical statements and qualified
ratios, not a complete point-in-time as-known-at-date reconstruction. Coverage
is limited to the audited pilot issuers and mapped U.S. `us-gaap` concepts.
KO has earlier revenue gaps; NVDA has unavailable recent PPE-based FCF.
Reported long-term debt is partial, so total debt/net debt are withheld.
Provider market history and same-day volume can be delayed or preliminary.
No historical valuation multiples or Release B functionality were deployed.

If a critical release-caused regression appears, first distinguish an app
defect from transient Yahoo/SEC access failure using production logs. Revert
the merge commit non-destructively (for this two-parent merge,
`git revert -m 1 434e5e3845316bf5efb73dd1a2fb42632ae3f9a8` on a reviewed
recovery branch/PR). Do not force-push or erase `main` history. No rollback
was needed for this release.
