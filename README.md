# Equity Lifetime Explorer

**Price History · Corporate Actions · Liquidity · Dividends · SEC Financial Fundamentals**

Equity Lifetime Explorer is a public-ready Streamlit research application for
studying a security's complete Yahoo Finance history. It reconstructs raw
as-traded prices, recorded share-changing actions, a mechanical ownership-
equivalent price series, liquidity measures, drawdowns, dividends, and a
provider-adjusted total-return proxy.

> Public Streamlit URL: _add after deployment_

> Screenshot: _add `assets/app-overview.png` after deployment_

## Features

- Dynamic Yahoo-style symbols including `BRK-B`, `SAP.DE`, `RELIANCE.NS`, and `7203.T`.
- Explicit **ANALYZE** action with a 12-hour Streamlit cache; theme and workspace changes do not redownload data.
- Four lazily selected workspaces: **Price & Ownership**, **Volume & Liquidity**, **Dividends & Total Return**, and **Financial Fundamentals**. The fourth workspace does not change the existing market calculations.
- Corporate-action ledger, validation audit, provider provenance, and graceful missing-data states.
- Event-preserving display downsampling while calculations and CSV exports retain every daily observation.
- In-memory standalone HTML, CSV, and complete ZIP downloads; no persistent server storage is assumed.
- Dark and light Plotly themes with native Streamlit controls.
- Generalized SEC EDGAR annual/quarterly statements for verified U.S. GAAP 10-K/10-Q corporate issuers, with exact ticker/CIK checks, filing/acceptance lineage, source hashes, quality flags and explicit missing-data states. The original MSFT/KO/AAPL/NVDA audited overrides are retained by issuer identity.
- Reported basic/diluted EPS, same-filing comparative EPS growth, conservative parent-attributable ROE, and an explicitly qualified operating-income-basis ROCE. Financial charts offer display-only **1Y / 3Y / 5Y / 10Y / MAX** horizons.

## Methodology

### Mechanical no-split equivalent

For reconstructed raw/as-traded prices:

```text
no_split_close(t) = raw_close(t) × cumulative_share_multiplier(t)
```

The multiplier contains included share-changing actions effective on or before
each date. The engine does not multiply the entire history by the final factor.
This is an ownership-equivalent reconstruction, not a prediction of the market
price that would have prevailed without splits.

### Volume

Share volume is the provider observation. The 20-session and 50-session averages
use prior completed trading sessions. Relative Volume is current volume divided
by the prior 20-session average. Dollar Volume is raw as-traded close multiplied
by share volume; it is an approximation, not exact exchange turnover.
The latest RVOL is marked preliminary during a recognized open exchange session.
Because the provider supplies no daily-bar finality flag, same-day pre/post-close
or unmapped sessions are marked unverified rather than presented as completed.

### Dividends and total return

Provider dividend values may be retrospectively normalized for later stock
splits. Growth calculations retain one provider/current-share-equivalent basis,
and historical yield uses a compatible split-adjusted price denominator. The
current partial calendar year is excluded from structural CAGRs and streaks.
Adjusted Close is described as a pre-tax, pre-fee total-return proxy only when
the provider genuinely supplied it.

### Release A Financial Fundamentals

The financial layer uses the SEC's public [Company Facts and submissions APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). Release A.1 adds explicit standard `us-gaap` mappings for eligible corporate issuers outside the original four-company pilot. These generalized mappings are **not issuer-specifically audited**; their scope is identified in the UI and reports. Normalized observations retain accession, fiscal dates, filing and acceptance timestamps, original unit, exact decimal value, revision status, source concept, mapping basis/priority and selection lineage. Historical statements are **latest-disclosed**, not point-in-time as-known-at-date valuation inputs. The full observation ledger and selection decisions are exportable.

Annual and standalone quarterly views keep duration flows distinct from instant balance-sheet facts. Compatible cumulative monetary flows may be subtracted to derive a standalone quarter; EPS is never derived this way. PPE capital spending is a positive cash outflow; ordinary free cash flow is operating cash flow less verified PPE spending, excluding acquisitions. Missing inputs are not treated as zero. Revenue, operating income, **parent-attributable** net income, EPS, cash flows, cash, reported long-term debt, margins and compatible growth rates are surfaced only when supported. Reported long-term debt is **not** a complete debt total, so total debt and net debt are deliberately withheld. No historical valuation multiples are calculated in Release A.

Coverage is limited to compatible USD/U.S. GAAP 10-K/10-Q facts; IFRS and foreign-private-issuer 20-F/6-K reporting require a separate module. NVDA's recent broader productive-asset-spending disclosure remains separate from PPE capital spending, so latest PPE-basis FCF remains unavailable. Company Facts omits custom company-specific tags, and generalized coverage is frequently partial. An unavailable SEC module does not prevent the original market workspaces from working. See [Release A.1 coverage and methodology](RELEASE_A1_GENERALIZED_COVERAGE.md) for the expanded live matrix and unsupported cases, [Release A hardening](RELEASE_A_HARDENING.md) for retained pilot methods, and the [production validation record](RELEASE_A_PRODUCTION_VALIDATION.md) for prior deployment checks.

An optional, default-off chart overlay uses the existing split-adjusted
current-share price (without dividend reinvestment) at the latest trading close
on or before each fiscal-period end. It aligns periods for visual comparison;
financial results were disclosed later and were not known at fiscal year-end.
Market Data Quality and SEC Financial Data Quality are reported separately,
without a combined confidence score. HTML tables abbreviate monetary amounts
for reading, while CSV exports retain original numeric precision.

## Local installation

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

For live SEC retrieval, configure a truthful operator contact privately at runtime, for example through the `SEC_USER_AGENT` environment variable or Streamlit's private `secrets.toml`. Use an application/organization name and contact email in the User-Agent value, following the [SEC's access guidance](https://www.sec.gov/about/privacy-information). Do not commit your email, `.env`, or `.streamlit/secrets.toml`. If this setting is absent, Financial Fundamentals shows an unavailable state; the original Yahoo workspaces remain usable. The SEC client limits its requests to two per second per process, retries transient transport errors, and treats access restrictions explicitly.

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

Ordinary tests are deterministic and offline. Live Yahoo checks are marked
`integration` and are excluded from CI by default.
The live SEC pilot and generalized issuer matrix are opt-in: set `RUN_SEC_INTEGRATION=1` and a private
`SEC_USER_AGENT`, then run `pytest -q tests/test_integration_sec.py`.
For reproducible per-metric coverage evidence, run `python -m scripts.validate_sec_coverage`
with the same private environment configuration. No contact is included in the evidence.

## Repository architecture

```text
app.py                    Streamlit entry point and stateful UI
src/providers/            Provider abstraction and Yahoo adapter
src/corporate_actions.py  Action normalization and reconciliation
src/reconstruction.py     Raw restoration and no-split mathematics
src/analytics.py          Lifetime return and drawdown analytics
src/volume.py             Liquidity analytics
src/dividends.py          Dividend and total-return analytics
src/validation.py         Audit checks and quality assessment
src/charts/               Plotly workspaces and display optimization
src/exports.py            In-memory HTML, CSV, and ZIP generation
src/providers/sec.py      Identified SEC API client and exact issuer resolution
src/financials/           Concept mapping, fiscal normalization, vintages, analytics, quality
src/research_service.py   Independent SEC orchestration; market AnalysisResult unchanged
src/financial_exports.py  SEC specialist HTML and provenance-rich CSV exports
tests/                    Deterministic financial and export tests
```

See [MIGRATION_AUDIT.md](MIGRATION_AUDIT.md) for the Colab v5 feature mapping.

## Streamlit Community Cloud deployment

1. Push this directory to a public GitHub repository.
2. In Streamlit Community Cloud, choose the repository and branch.
3. Set the entry point to `app.py`.
4. For Release A SEC access, configure `SEC_USER_AGENT` privately in Streamlit
   secrets before deployment. Do not commit the operator contact or include it
   in public exports.

The local provider cache uses the operating system's temporary directory and is
only an optimization. The application does not depend on filesystem persistence.

## Data source and limitations

Yahoo Finance through `yfinance` is the primary provider. Free-provider history
can be delayed, incomplete, or retrospectively adjusted. Corporate-action
classification is especially limited for older and non-US bonus issues, rights,
reorganizations, and predecessor securities. No currency conversion is applied.

High volume does not reveal participant identity or establish accumulation or
distribution. Total-return outputs do not model taxes, fees, or withholding.

## Disclaimer

For informational and research purposes only. Market data may be delayed,
incomplete or retrospectively adjusted by the provider. Mechanical no-split
values are ownership-equivalent reconstructions and are not estimates of the
price that would necessarily have prevailed without corporate actions.

## License

MIT. See [LICENSE](LICENSE).

## Release A.2 development status

The isolated `feature/global-financials-release-a2` branch contains an initial
source-routing policy, separate exact IFRS registry and bounded ESEF extraction
foundation. These are not yet integrated into the production workspace or
exports. See [source feasibility and outstanding release gates](RELEASE_A2_SOURCE_FEASIBILITY.md).
Do not interpret passing foundation tests as completion of the global-source
release. Its optional public ESEF extraction check is enabled with
`RUN_ESEF_INTEGRATION=1 pytest -q tests/test_integration_esef.py`.
