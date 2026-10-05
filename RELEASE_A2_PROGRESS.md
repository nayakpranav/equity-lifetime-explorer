# Release A.2 — international integration checkpoint

Date: 2026-10-05. Continues checkpoint
`7efbd86cbd9b484e58d9814e88dc8d501e273bf3` on the same
`feature/global-financials-release-a2` branch. This is **not a completed release**.
No production change, new staging deployment, merge or Release B work.

## Implemented increment

- SEC IFRS extension reuses the existing identified, paced, cached SEC client.
  Exact ticker/submissions/Company Facts CIK checks remain mandatory. SAP.DE
  uses an explicit primary-source cross-listing relationship, not a fuzzy name.
- `ifrs-full` has its own exact concept registry and annual 20-F/20-F/A/
  40-F/40-F/A eligibility. Arbitrary 6-K facts are excluded. Native currency is
  obtained from annual financial disclosures; ambiguous currencies are rejected.
- Framework-specific parent-income/equity/operating-income concept guards reuse
  the unchanged ROE/ROCE formulas. EPS growth uses same-filing comparative pairs
  in the same currency, unit and taxonomy; acceptance dates remain required.
- ESEF reuses the foundation's bounded cached provider and strict OIM extractor.
  Verified listing references route MC.PA, NOKIA.HE and ASML.AS. The latest
  repository document and its own comparatives form one coherent snapshot;
  older reports are not silently used to fill holes with unverified vintages.
- Corrected a genuine selection defect: unknown filing dates previously failed
  equality grouping, permitting conflicts with missing dates to escape peer
  comparison. Such peers now conflict conservatively, with a regression test.
- Workspace, specialist/Combined HTML, provenance CSV and downloads use actual
  source/framework labels. Non-SEC CSV names no longer claim SEC provenance;
  existing SEC CSV names remain compatible. Native numerical precision and
  missing values are unchanged.
- Foreign share-price overlays are withheld for currency mismatches or
  unverified listing/share relationships. No FX or ADR conversion is introduced.

## Actual international coverage

Counts below are selected annual flow periods / balance-sheet dates, not raw
duplicate Company Facts or XBRL observation counts. Exact concept coverage is
partial and must not be read as a complete financial history.

| Issuer / source | Currency | Annual financial periods | Compatible fields observed | Explicit gaps |
|---|---|---|---|---|
| SAP.DE / SEC IFRS | EUR | 11: 2015–2025 | Revenue, gross profit, operating income, parent income, basic/diluted EPS, OCF (11 each); assets/liabilities/current balances/parent equity 2016–2025; cash 2014–2025 | PPE CapEx/FCF unavailable; latest ROE/ROCE withheld for revised-input review |
| NVO / SEC IFRS | DKK | 7: 2019–2025 | Revenue, gross profit, operating income, basic/diluted EPS, OCF (7 each); assets/liabilities/current balances/parent equity 2020–2025; cash 2018–2025 | Parent-income exact tag missing; PPE CapEx/FCF unavailable; price currency/share basis incompatible/unverified |
| LVMH MC.PA / ESEF France | EUR | 3: 2022–2024 | Revenue, gross profit, parent income, basic/diluted EPS, OCF and relevant balances (3 each) | Operating income, total liabilities and PPE CapEx not supplied by supported exact tags; FCF unavailable |
| Nokia NOKIA.HE / ESEF Finland | EUR | 3: 2023–2025 | Operating income, parent income, gross profit, EPS, OCF (3); assets/liabilities/current liabilities/parent equity 2024–2025; cash 2022–2025 | Revenue/current assets/PPE CapEx unavailable under exact registry; FCF unavailable |
| ASML.AS / ESEF Netherlands | EUR | 3: 2023–2025 | Operating income, gross profit, EPS, OCF (3); assets/current balances/parent equity 2024–2025; cash 2022–2025 | Revenue/parent income/total liabilities/PPE CapEx unavailable under exact registry; FCF unavailable |

No compatible standalone quarterly history is claimed by these annual routes.
ESEF publication, acceptance, audit and consolidation status remain unverified
where the repository does not establish them. EPS growth is withheld without
verified same-filing acceptance evidence. Latest ESEF report comparatives are
not a complete latest-disclosed historical or point-in-time reconstruction.

Identity references:

- [SAP primary listing information](https://www.sap.com/investors/en/stock/basic-data.html)
- [Nokia primary LEI/ISIN disclosure](https://www.nokia.com/newsroom/nokia-corporation-repurchase-of-own-shares-on-17052024/)
- [ASML primary listing/ISIN information](https://investor.asml.com/share-information)
- [ASML GLEIF legal-entity record](https://api.gleif.org/api/v1/lei-records/724500Y6DUVHQD6OXN27)
- [LVMH French regulator LEI/ISIN disclosure](https://bdif.amf-france.org/back/api/v1/documents/2026/2026DD1093285/8F37B3D1E1F4DF28166D9CCA020CC2E6F5926AFA219E596C7F82C68C14E04068.pdf)

## India acquisition findings — not implemented ingestion

Ordinary requests, without cookies, impersonation, login or evasion:

| Case | Evidence | Outcome / remaining work |
|---|---|---|
| ITC.NS | Official quarterly-results page lists consolidated and standalone XLS/XLSX | Ordinary request returned 406; source-file layout/identity/scale parsing not validated. Need legitimately supplied official workbook or accessible filing artifact. No automated coverage claimed. |
| TCS.NS | Official IR page identifies TCS Data Sheet | Ordinary request returned 403. No bypass attempted; no verified file ingested. |
| RELIANCE.NS | Official financial-reporting and 10-year consolidated highlights pages returned 200 | Public chart data available, but gross sales/services, profit for year and provider EPS cannot silently stand in for net accounting revenue, parent profit or basic/diluted EPS. Compatible consolidated financial-statement artifact ingestion remains outstanding. |
| HDFCBANK.NS | Official current investor page returned 200 and linked annual/quarterly PDFs | Identified legitimate artifacts, but reliable structured extraction/accounting-basis validation not completed. Industrial FCF/ROCE must remain excluded. |

[Screener terms](https://www.screener.in/guides/terms/) are accessible and restrict
copying, transfer/mirroring and public display. A 200 response is not permission
to republish its tables in this public app. Direct production scraping was not
enabled. Legitimate user-supplied company Excel export parsing remains to be
implemented/tested against an actual workbook with identity/basis evidence.

Screener public-page assessment found annual/quarter income, balance, cash flow,
and ratio tables with consolidated/standalone contexts and Rs. crore units.
Its displayed operating profit must not be assumed EBIT; total liabilities
includes equity and cannot map to canonical liabilities; unlabeled EPS cannot
be assumed basic or diluted; displayed FCF does not prove verified PPE payments.

The existing Yahoo client successfully retrieved structured income, balance
and cash-flow tables for all four Indian cases during feasibility checks. These
are short provider histories, not validated canonical coverage. Native-currency,
identity, accounting-definition, consolidation and publication-date validation
and a maintainable adapter are still required. The
[yfinance documentation](https://ranaroussi.github.io/yfinance/) explicitly
describes Yahoo API access as personal-use-only; public financial-table
redistribution permission was not established. No new automatic financial route
was enabled on the basis of technical access alone. Existing validated market
data functionality is unchanged.

Ordinary Finviz and Macrotrends access returned 403 during terms assessment;
neither was integrated or bypassed. An official/user-licensed import path is
still necessary. No one universal Indian provider is assumed.

## Validation

- Original 126 deterministic tests retained, with fixtures/caption expectations
  updated for intentionally supported SAP routing, native-currency guards and
  provider-neutral download labels. Eleven new deterministic cases cover IFRS,
  coherent ESEF, unknown-date conflicts, native EPS/ROE/ROCE and overlays.
  Final Python 3.11 deterministic count: 137 tests.
- Python 3.11.17 isolated environment; no new production dependency.
- Expanded opt-in integration suite: **28 passed**, including original SEC
  pilot/generalized issuers and Yahoo/export regressions, five new international
  provider/export cases and the existing ESEF extraction case.
- International tests use actual SEC/ESEF financial responses and deterministic
  market fixtures for financial report composition. Existing Yahoo integration
  tests separately exercise real market data. Do not claim hosted A.2 testing.
- Specialist/Combined HTML, precision-preserving annual/provenance CSV, selected
  ZIP and complete package passed for all five international cases. CDN loads
  one external Plotly script; portable embeds one library payload. An unused
  CDN URL inside Plotly source is not counted as an external script request.
- Local Streamlit startup and health endpoint passed on Python 3.11.

## Remaining release gates

1. India multi-provider orchestration and maintainable official/user-export
   parsers, secure upload UI, issuer/basis/audit/currency/fiscal validation.
2. Actual India normalized coverage evidence and parser/export tests for ITC,
   Reliance, TCS and a bank. No fabricated coverage or values.
3. Broader verified European listing discovery and reporting-basis evidence;
   current crosswalk is deliberately limited rather than fuzzy.
4. Final full integrated tests, CI, security review and normal PR merge only
   once all material A.2 gates pass.
5. Production deployment and required post-deployment international/India
   smoke tests. Production remains unchanged until gate completion.

Operator identity is runtime-only. No contact value, credential, source document,
generated cache or private filesystem path belongs in committed artifacts.
