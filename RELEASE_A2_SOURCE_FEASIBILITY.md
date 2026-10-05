# Release A.2 source feasibility — development checkpoint

This is not a release acceptance or deployment approval. Production remains at
`08946a7f6cf4526ab14c4e06302a42ac7919298a`. Work is isolated on
`feature/global-financials-release-a2`; the existing research service, UI and
exports have not yet been switched to the new source policy.

## Evidence reviewed on 2026-10-05

| Route | Interface and identity | Access / reuse assessment | Current implementation status |
|---|---|---|---|
| SEC US GAAP | Existing exact ticker directory, submissions and Company Facts | Existing identified API client; private operator contact required; two requests/second | Production A.1 unchanged |
| SEC IFRS | Separate exact IFRS registry; 20-F/40-F annual forms only | Same SEC access obligations; no automatic 6-K compatibility assumption | Registry and routing policy only; ingestion not integrated |
| ESEF | Documented filings.xbrl.org JSON:API, exact LEI entity links and xBRL-JSON | Public API currently requires no authentication; repository says no data-use restrictions, subject to future limits. Conservative two requests/second, 12-hour cache, bounded responses/pagination; source attribution retained | Provider and strict extraction implemented; not yet wired to workspace/export |
| Indian official filings | Official issuer IR/structured filings and exact CIN/ISIN evidence | Public visibility alone is not sufficient evidence for automated collection or unrestricted redistribution. No production automated route approved | Upload route planned; parser/UI and live matrix remain outstanding |
| NSE website | Website / public pages | Terms explicitly prohibit systematic automated collection | Rejected for automated scraping |
| BSE / MCA / third-party aggregators | No appropriate automated financial-data permission established in this checkpoint | No bypass, cookie challenge circumvention or assumed license | Not enabled |

Primary references:

- [SEC developer APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [ESEF repository API](https://filings.xbrl.org/docs/api) and [scope / reuse notes](https://filings.xbrl.org/docs/about)
- [NSE terms of use](https://www.nseindia.com/static/nse-terms-of-use)
- [ITC official quarterly results](https://itcportal.com/investors/quarterly-results.html)
- [SAP stock and listing identifiers](https://www.sap.com/investors/en/stock/basic-data.html)
- [XBRL period semantics](https://www.xbrl.org/guidance/xbrl-json-tutorial/)
- [Arelle installation](https://arelle.readthedocs.io/en/latest/install.html)

The repository's ingestion date is not an issuer publication, filing or SEC
acceptance date. Unknown disclosure dates remain unknown. Native statement
currency is not inferred from the trading currency. No FX or ADR conversion is
performed. Entity-wide standard IFRS facts do not by themselves establish an
audited consolidated-versus-standalone basis; that qualification remains visible.

## Arelle evaluation

Arelle supports Python 3.11 and command-line processing and is Apache-2.0
licensed. It is not installed as a new application dependency at this checkpoint:
the documented ESEF service already supplies xBRL-JSON. A secure local XBRL/iXBRL
upload implementation still needs parser, taxonomy/network, package-size and
identity validation. Do not advertise arbitrary XBRL uploads as supported yet.

## Actual limited live evidence

Exact LEI `IOG4E947OATN0KJYSD45` resolves to LVMH in the repository. Four reports
were returned. The latest available report, ending 2024-12-31, yielded 36 mapped
observations across comparative years 2022–2024, including revenue, gross profit,
parent income, basic/diluted EPS, OCF, cash, assets, current assets/liabilities and
parent equity. Counts include duplicate observations retained for provenance;
they must not be mistaken for 36 selected, validated statement cells. Conflicting
duplicates are invalidated and equal duplicates enter analysis at most once.
Operating profit and compatible PPE CapEx were not manufactured from extensions.
This is one-source extraction evidence, not the required three-country matrix.

## Before-state reference

The complete reader-facing content of the supplied ITC Combined Research HTML
was inspected. Its Financial Fundamentals section reports a foreign/non-SEC
unavailable state; its market workspaces remain present. Report SHA-256:
`b7ff12be2410949e970b262e23e48bfcaf701b7f4195028e1ebd46693599ccd1`.
The report is not an official financial statement and cannot validate Ind-AS
financial values, fiscal periods, audit status or issuer concept mappings.

## Remaining mandatory gates — not passed

- SEC IFRS provider integration and live SAP / second FPI coverage.
- Verified listing-to-issuer resolution beyond source-level LEI validation.
- Three-country ESEF matrix, reporting basis and vintage reconciliation.
- Official Indian import parsing, identity/basis/audit validation and ITC,
  RELIANCE, TCS and bank fixtures/live evidence.
- Provider-neutral model/diagnostics, router orchestration and UI integration.
- Specialist/Combined HTML, CSV/ZIP integration and missing-data/overlay checks.
- Private local SEC test configuration (never commit the operator contact).
- Full expanded live matrix, Python 3.11 readiness, CI, deployment and hosted
  production smoke tests.

No PR merge or production deployment is permitted on the basis of this partial
checkpoint. Release B is out of scope.

## Local checkpoint checks

- Full suite with `RUN_ESEF_INTEGRATION=1`: 127 passed (126 deterministic, one
  public ESEF integration); 22 existing SEC/Yahoo live checks skipped because
  their opt-in prerequisites were not enabled.
- Source compile and imports passed.
- Temporary local Streamlit health check passed. The target-directory dependency
  install required `global.developmentMode=false` for the local startup command;
  no application configuration was changed.
- Local runtime was Python 3.12. Python 3.11 deployment readiness still requires
  the branch's CI and full integrated release gates.
- No new runtime dependency, operator contact, credential, generated cache,
  source-document payload or private filesystem path is part of this patch.
