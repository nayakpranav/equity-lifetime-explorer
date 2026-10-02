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
