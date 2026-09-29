# Equity Lifetime Explorer

**Price History · Corporate Actions · Liquidity · Dividends**

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
- Three lazily selected workspaces: **Price & Ownership**, **Volume & Liquidity**, and **Dividends & Total Return**.
- Corporate-action ledger, validation audit, provider provenance, and graceful missing-data states.
- Event-preserving display downsampling while calculations and CSV exports retain every daily observation.
- In-memory standalone HTML, CSV, and complete ZIP downloads; no persistent server storage is assumed.
- Dark and light Plotly themes with native Streamlit controls.

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

### Dividends and total return

Provider dividend values may be retrospectively normalized for later stock
splits. Growth calculations retain one provider/current-share-equivalent basis,
and historical yield uses a compatible split-adjusted price denominator. The
current partial calendar year is excluded from structural CAGRs and streaks.
Adjusted Close is described as a pre-tax, pre-fee total-return proxy only when
the provider genuinely supplied it.

## Local installation

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

Ordinary tests are deterministic and offline. Live Yahoo checks are marked
`integration` and are excluded from CI by default.

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
src/charts/               Three Plotly workspaces and display optimization
src/exports.py            In-memory HTML, CSV, and ZIP generation
tests/                    Deterministic financial and export tests
```

See [MIGRATION_AUDIT.md](MIGRATION_AUDIT.md) for the Colab v5 feature mapping.

## Streamlit Community Cloud deployment

1. Push this directory to a public GitHub repository.
2. In Streamlit Community Cloud, choose the repository and branch.
3. Set the entry point to `app.py`.
4. Deploy. No secrets, database, Docker image, or background service is required.

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
