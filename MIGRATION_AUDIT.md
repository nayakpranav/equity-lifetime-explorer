# Colab v5 migration audit

The production engine was mechanically extracted from the validated
`Equity_Lifetime_Explorer_Colab_v5.ipynb` whose SHA-256 is
`3cfa3b92e7c49a4d0eb4b79146e9f8479936ef2a4a02a83e0c44d2ad81c8ea52`.

| v5 capability | Production location | Status |
|---|---|---|
| Yahoo maximum-history retrieval and ticker normalization | `src/providers/yahoo.py` | Preserved |
| Corporate-action normalization and reconciliation | `src/corporate_actions.py` | Preserved |
| Provider Close-basis detection and raw restoration | `src/reconstruction.py` | Preserved |
| Progressive no-split reconstruction | `src/reconstruction.py` | Preserved |
| Lifetime, CAGR and drawdown analytics | `src/analytics.py` | Preserved |
| Volume metrics and events | `src/volume.py` | Preserved |
| Dividend and total-return analytics | `src/dividends.py` | Preserved |
| Validation and quality assessment | `src/validation.py` | Preserved |
| Currency-aware formatting | `src/formatting.py` | Preserved |
| Three Plotly reports and dark/light palettes | `src/charts/` | Preserved, with page chrome moved to Streamlit |
| Event-preserving display downsampling | `src/charts/common.py` | Extended for production performance |
| HTML, CSV and ZIP outputs | `src/exports.py` | Migrated to in-memory generation |
| Dynamic ticker UI and cached result | `app.py` | Migrated from ipywidgets to Streamlit |

Notebook-only `ipywidgets`, Colab forms, output containers, package installation,
and `google.colab.files.download` were intentionally removed. Financial formulas
were not redesigned. Production charts operate on an event-preserving display
copy; the canonical full-resolution `AnalysisResult` remains the source for all
calculations, validation, and CSV exports.

One compatibility-only spelling change uses `pd.Timedelta(365, unit="D")` in
place of `pd.Timedelta(days=365)`. Both represent exactly 365 days; the explicit
unit avoids a NumPy deprecation warning and does not change the 52-week result.
