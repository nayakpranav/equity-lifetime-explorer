# Release A hardening and Release B readiness

This document describes the isolated `feature/financial-fundamentals-release-a`
branch. It is **not** a production deployment or a historical valuation module.
SEC Company Facts is the statement source; Yahoo market data remains an
independent source for the existing three workspaces. Statement history is the
latest disclosed view, not a point-in-time reconstruction of what investors
knew on each historical date.

## Coverage audit

There is no 20-year statement limit. The earlier count of exactly 20 annual
periods per pilot included one opening, balance-sheet-only instant as though it
were a completed annual income/cash-flow statement. A completed annual row now
requires an annual duration fact. Historical balance instants remain in the
observation ledger. The current SEC Company Facts pilot snapshot yields:

| Issuer | Completed annual statements | Quarterly statement rows | Annual revenue | Parent net income / basic & diluted EPS | Annual operating cash flow | PPE capital spending |
| --- | --- | --- | --- | --- | --- | --- |
| MSFT | FY2008–FY2026 (19) | 76 | FY2009–FY2026 (18) | FY2008–FY2026 (19) | FY2008–FY2026 (17) | FY2008–FY2026 (19) |
| KO | FY2007–FY2025 (19) | 72 | FY2016–FY2025 (10) | FY2007–FY2025 (19) | FY2007–FY2025 (19) | FY2007–FY2025 (19) |
| AAPL | FY2007–FY2025 (19) | 72 | FY2007–FY2025 (19) | FY2007–FY2025 (19) | FY2007–FY2025 (18) | FY2013–FY2025 (13) |
| NVDA | FY2008–FY2026 (19) | 73 | FY2008–FY2026 (18) | FY2008–FY2026 (19) | FY2008–FY2026 (19) | FY2010–FY2012 (3) |

These are periods with selected valid facts, **not** evidence of a complete
statement in every column. The exported coverage table distinguishes dates
present in raw SEC units, normalized observations and selected valid periods.
For the annual concepts shown above, the pilot's raw mapped-tag period count
and selected-period count match; this does not imply every SEC fact or custom
issuer tag was mapped. The SEC can revise the snapshot, so the counts are
test-run observations rather than a guaranteed permanent range.

### Concept decisions and source evidence

| Source concept / evidence | Normalized use | Decision and limitation |
| --- | --- | --- |
| `us-gaap:NetIncomeLoss` in all four pilot Company Facts feeds | `net_income_parent` | SEC concept is net income attributable to parent. The earlier `net_income_consolidated` label was incorrect; the mapping is corrected. It is not automatically net income available to common shares after any preferred claims. |
| `us-gaap:EarningsPerShareBasic`, `us-gaap:EarningsPerShareDiluted` | `eps_basic`, `eps_diluted` | Keep reported per-share values and `USD/shares` units, accession, fiscal period and acceptance lineage. Never derive EPS by subtracting cumulative reports. |
| `us-gaap:StockholdersEquity` | parent equity for ROE | Parent-attributable equity must be present for adjacent fiscal year ends. Negative or zero equity prevents a valid ROE. |
| `us-gaap:OperatingIncomeLoss`, `us-gaap:Assets`, `us-gaap:LiabilitiesCurrent` | qualified ROCE | Operating income is an EBIT proxy; assets less current liabilities is the capital-employed definition. This is not universal across sectors. |
| MSFT `SalesRevenueNet` through 2015 and `RevenueFromContractWithCustomerExcludingAssessedTax` from 2016; AAPL corresponding transition after 2016; KO/NVDA `Revenues` | revenue | Explicit issuer/date mapping. The tags are not summed or used to fill unsupported years. |
| KO `LongTermDebt` | reported long-term debt only | The mapped standard tag stops before the latest 2025 annual report. `LongTermDebtAndCapitalLeaseObligations` includes leases and is **not** an equivalent substitute. No total-debt or net-debt series is claimed. |
| NVDA `PaymentsToAcquirePropertyPlantAndEquipment` | PPE capital spending | Mapped historical PPE observations do not extend into recent years. The latest PPE-basis FCF is withheld. |
| NVDA `PaymentsToAcquireProductiveAssets` | **separate** productive-asset spending | Broader reported payments include productive assets beyond PPE; not substituted into PPE FCF. Recent periods are shown under their own label. |

The [KO 2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/21344/000162828026010047/ko-20251231.htm)
discloses debt in its statements, but a verified equivalent standard Company
Facts concept for the required historical debt series has not been established.
The [NVDA FY2026 Form 10-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000021/nvda-20260125.htm)
labels its productive-asset payments as including property/equipment and
intangibles. That reported scope is broader than PPE alone. Acquisition cash
flows and total investing cash flow are never substituted for capital spending.

## Reconciliation and ratio methods

- Fiscal-period classification keeps annual durations, reported standalone
  quarters, cumulative year-to-date cash flows and balance-sheet instants
  separate. Compatible monetary YTD parents may produce a standalone quarter;
  source observation IDs and calculation parents are retained. EPS is never
  obtained by cumulative subtraction.
- Revised observations and conflicting facts retain accession and acceptance
  lineage. Direct-versus-derived quarterly differences remain warnings, with
  the direct reported amount preserved. `MIXED_DISCLOSURE_VINTAGES`,
  `REVISED_PARENT_REVIEW`, missing parent periods and unresolved reported versus
  compatible-cumulative differences are classified distinctly. A difference
  is not automatically labelled rounding or a restatement without evidence.
- Basic and diluted EPS YoY compares current/prior observations reported in
  the **same filing**, on that filing's share basis. Nonpositive prior or
  current EPS makes conventional percentage growth unavailable. Three- and
  five-year EPS CAGR chain-links contiguous, valid same-filing comparisons;
  raw EPS from different filings are not divided across unverified split
  bases. This does not make EPS itself a point-in-time, current-share series.
- Parent ROE = annual `NetIncomeLoss` / average adjacent beginning/ending
  `StockholdersEquity`. Currency, annual-period adjacency, exact source tags
  and revision conditions are checked. Missing/nonpositive equity or an
  unverified attribution withholds the ratio. Parent ROE may still differ
  from a common-shareholder ROE where preferred claims matter.
- Qualified ROCE = annual `OperatingIncomeLoss` / average adjacent
  (`Assets` − `LiabilitiesCurrent`). Both capital-employed endpoints must be
  positive, adjacent and compatible; an invalid or revised input withholds the
  ratio. Operating income is an EBIT proxy and the capital-employed definition
  may not suit financial institutions. The ratio is not shown as universally
  comparable across every security or accounting regime.
- The 1Y/3Y/5Y/10Y/MAX control filters **display only**. Fiscal year/quarter
  labels remain categorical and unambiguous. Company-level latest metrics and
  full-resolution CSV/HTML data are not recalculated by the visual horizon.

The pilot results contain valid annual EPS growth, parent ROE and qualified
ROCE for many—but not every—period. For MSFT/KO/AAPL/NVDA respectively, valid
parent ROE periods are 16/16/18/16 of 19 and valid qualified ROCE periods are
15/14/14/16 of 19. Missing opening balances, missing inputs and revision
reviews explain withheld periods; these counts can change with later SEC
revisions. High ROE, notably for issuers with equity reduced by repurchases,
requires interpretation beyond the arithmetic ratio.

## Operations, exports and scope

The SEC client requires a private, truthful `SEC_USER_AGENT`, checks exact
ticker/CIK identity, paces requests at two per second per process, uses bounded
timeouts/retries, stops clearly on HTTP 403/429 and joins older submissions
metadata for acceptance timestamps. The feature remains unavailable—not a
failure of Price, Volume or Dividends—if configuration, access or issuer
coverage fails. An explicit fresh Analyze clears the financial cache; chart
and horizon changes reuse the in-memory result. Operator contact details do
not belong in this repository, logs, exports or public documentation.

Financial specialist and combined HTML reuse the chart builders. Annual and
quarterly CSVs preserve reported EPS, source tags, units, selected observation
IDs and ratio statuses; the derived-ratios CSV distinguishes calculated
values and parent observation IDs. Coverage, source observation, selection,
quality and reconciliation exports remain available. Financial Quality CSV is
an additional export. HTML/ZIP generation remains on demand and in memory;
the combined report embeds/loads Plotly JavaScript once.

## Release B gate: **not yet approved**

| Proposed multiple | Readiness | Required gate before implementation |
| --- | --- | --- |
| Historical trailing P/E | Blocked by methodology | Point-in-time filing/acceptance policy; compatible historical raw-price versus reported EPS/share class/split basis; defensible TTM earnings and nonpositive-EPS handling. |
| Historical P/S | Conditionally ready | Valid historical revenue exists, but period-correct shares outstanding or market-cap series and public-availability timestamps are not yet established. Never use today's share count. |
| Historical P/FCF | Blocked by missing data and methodology | Period-correct shares/market cap, compatible TTM OCF and PPE spending, and consistent quarterly vintages. NVDA recent PPE spending is unavailable. |
| Historical PEG | Blocked by methodology | A historically available, trailing growth definition or archival expectation dataset; no look-ahead to later realized growth or today's analyst estimates. |
| Other valuation ratios | Unsupported pending definition | Document numerator/denominator, accounting basis, source dates and sector applicability before building any series. |

The Release A foundation is suitable for a **staging review of historical
financial statements and qualified ratios**, subject to the pilot and
interpretation limits above. It is **not** sufficient to release historical
valuation multiples. A Release B design should first establish as-of data
selection, split/share-class-compatible prices and EPS, historical shares
outstanding, validated TTM construction and missing-value policy. No Release B
metric is implemented on this branch.
