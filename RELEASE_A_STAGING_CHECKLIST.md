# Release A staging checklist

This checklist is for a **separate** Streamlit Community Cloud app deployed
from `feature/financial-fundamentals-release-a`. Do not edit the existing
`main` app's GitHub coordinates, secrets or deployment settings. Do not merge
or deploy Release B.

## Deployment settings

| Setting | Staging value |
| --- | --- |
| Workspace | `nayakpranav` |
| Repository | `nayakpranav/equity-lifetime-explorer` |
| Branch | `feature/financial-fundamentals-release-a` |
| Entrypoint | `app.py` at repository root |
| Dependencies | Root `requirements.txt` |
| Theme/configuration | Root `.streamlit/config.toml` |
| Separate review app | `https://equity-lifetime-explorer-release-a-review.streamlit.app/` |
| Python | 3.11 |

The separate review app has been created from the feature branch; the original
`equity-lifetime-explorer.streamlit.app` production app remains on `main`.
Community Cloud did not permit a custom subdomain containing `staging`, hence
the distinct `release-a-review` URL above.

Configure `SEC_USER_AGENT` **only in the review app's private Secrets
settings**, using a truthful application name and operator contact. The app
also reads a process environment variable of that name for local checks. Do
not put contact information in Git, a public URL, a screenshot or a test log.
If this setting is absent, Financial Fundamentals should show an unavailable
state while market workspaces remain usable.

## Before inviting reviewers

- [ ] Feature-branch GitHub Actions `tests` workflow is green for the draft PR.
- [ ] Staging app URL is distinct from the existing production app URL.
- [ ] App starts without a secrets or import error. `main` deployment remains
      on `main` and unchanged.
- [ ] Analyze MSFT, KO, AAPL and NVDA. Inspect annual and quarterly statements,
      EPS/YoY, parent ROE, qualified ROCE, cash-flow and balance-sheet charts,
      1Y/3Y/5Y/10Y/MAX horizons, KPI cards, source lineage and quality table.
- [ ] KO's mapped revenue starts in FY2016. Earlier gaps are unavailable,
      **not** zero or interpolated. Latest debt remains a partial measure;
      neither total debt nor net debt is asserted.
- [ ] NVDA's latest PPE-based FCF card says **Not available**. Its broader
      productive-asset-spending series is separately labelled, not substituted
      into PPE FCF.
- [ ] Analyze SAP.DE or another unsupported SEC issuer. Financial Fundamentals
      shows an explicit unavailable state; Price, Volume and Dividends still work.
- [ ] Change workspace, theme, statement frequency and chart horizon without
      another Yahoo/SEC retrieval. Use Force fresh retrieval only deliberately.
- [ ] In Download Center, prepare Financial Fundamentals HTML, annual and
      quarterly CSVs, ratios/provenance/quality CSVs, selected ZIP, Combined
      Research HTML and Complete Analysis ZIP from a real pilot result.
- [ ] Inspect the exported HTML in both CDN and portable modes. Verify one
      Plotly JavaScript load and all applicable chart/table sections.
- [ ] Temporarily test missing/blocked SEC operator access in a safe local or
      separate staging configuration; confirm market analysis remains available.
- [ ] Review the [Release A methodology and limits](RELEASE_A_HARDENING.md)
      with a financial reviewer before approving a merge.

## Review boundary

This branch contains historical financial statements and conservative
qualified ratios, **not** as-known-at-date financial history or historical
valuation multiples. Keep the PR as a draft until staging feedback and the
documented coverage limitations have been reviewed. Production `main` and its
Streamlit app must not change without explicit approval.

## Final hosted verification — 2026-10-02

The review app alone was rebooted with the operator's approval. Its startup log
showed a fresh checkout of `feature/financial-fundamentals-release-a`, and the
post-reboot UI exposed the new price-overlay, RVOL-status and quality-scope
features introduced by feature commit `f73fc34b9ceed5f9d73f4300a564337b031d15db`.
Community Cloud did not display the exact Git SHA in its runtime log; the
feature branch was at that SHA when rebooted. No production app control was
used. GitHub `main` remained at `07f9c8507c30437965ecf21022523e047b3e8db6`.

- Hosted MSFT analysis retrieved SEC Company Facts and submissions (CIK
  0000789019). Annual and quarterly statements, USD KPI formatting, EPS,
  parent ROE, ROCE, cash-flow and balance-sheet charts rendered. The 5Y chart
  horizon filtered quarterly traces without changing the latest annual KPIs.
- The default-off split-adjusted price control added a secondary price trace
  to Revenue, Free Cash Flow and Reported EPS. The workspace explains that the
  close is aligned to fiscal-period end, not the later filing/acceptance date.
- Market Data Quality and Financial Data Quality were separate. The financial
  section showed SEC coverage, source lineage, retrieval time and methodology.
  Financial HTML table formatting, missing-value markers, CDN/portable modes
  and no-contact export checks were previously verified against generated
  reports by deterministic/live tests; no new calculation changes were made.
- The latest hosted MSFT RVOL was **status unverified**, not presented as a
  completed-session number: same-day post-close provider data had no finality
  flag. Completed and preliminary cases were covered by deterministic tests;
  a live preliminary session was not available during this after-close check.
- The Price, Volume and Dividend workspaces rendered after the SEC view.
  Download Center prepared Financial Fundamentals HTML and Combined Research
  HTML together as one selected-export ZIP (`2 selected exports packaged`).
- The existing deterministic suite (74 passed), opt-in live suite (15 passed),
  CDN/portable report audit and green GitHub Actions `tests` run for `f73fc34`
  were reused. Earlier hosted pilot checks covered KO, AAPL, NVDA and the
  unsupported-ticker unavailable state; these were not rerun without a code
  change. The review app's private SEC setting worked, and no operator contact
  was displayed in the hosted UI or found in prior public-export scans.

This verification is sufficient for final human review of Release A; it is
not an instruction to merge the draft PR or deploy production.
