# Release A.1 — Generalized SEC coverage (development checkpoint)

Isolated branch: `feature/generalized-sec-release-a1`, based on production
`85c9050a7c0c6e8b655239ae2e8329d952c14107`. No production deployment,
main merge, historical Release A branch modification or Release B work is authorized.

## Architecture and accounting scope

- Eligibility now depends on exact SEC directory resolution, confirmed submissions
  listing and matching submissions/Company Facts CIK, not a four-symbol gate.
  Only dot/dash share-class spelling is normalized (e.g. BRK.B ↔ BRK-B).
  Multiple candidates, unconfirmed renamed/retired tickers and identity mismatches
  fail closed. No fuzzy company-name matching or guessing an ADR/predecessor issuer.
- The four audited mappings are retained by CIK, including explicit revenue
  date transitions and NVDA's separate productive-asset-spending series.
  Generalized mappings are explicitly labelled **not issuer-specifically audited**.
- Revenue alternatives, in declared order: customer revenue excluding assessed
  tax; net sales revenue; reported revenues; customer revenue including assessed
  tax. Equal newest-disclosure facts use declared priority. Conflicting alternatives
  in the newest comparable disclosure are withheld, never summed. A later disclosure
  remains latest-disclosed, not a look-ahead-free vintage. Revenue growth is withheld
  across incompatible mapping bases; an issuer-specific audited transition is unchanged.
- Other exact standard mappings retain GrossProfit, OperatingIncomeLoss,
  parent NetIncomeLoss, reported basic/diluted EPS, OCF, positive PPE cash
  payments, cash, assets/liabilities, current balances and parent equity.
  Long-term/noncurrent/current debt, short-term borrowings and commercial paper
  are separately identified components, not assumed to be a complete debt total.
  Total debt/net debt remain unavailable without a verified complete definition.
- No custom-tag inference, currency conversion, lease-inclusive capital-spending
  substitution, consolidated-income substitution for parent income, or share-class
  EPS inference. USD and USD/shares are the supported canonical units.
- Partial annual or quarterly coverage is usable. Missing values remain missing,
  and derived metrics retain input compatibility/status safeguards. ROE stays annual
  and parent-attributable; qualified ROCE/FCF are withheld for financial sectors,
  using SEC SIC 6000–6799 as a conservative backstop to listing sector metadata.
  Conglomerates with financing operations may require additional manual interpretation.
- Existing fiscal classification, restatement selection, compatible cumulative
  quarter derivation, same-filing EPS growth and qualified capital-efficiency
  formulas are reused. No point-in-time financial-history claim or valuation multiples.

## Identity, source and unavailable states

`AVAILABLE` means the latest annual core inputs are present, not complete history
or a manual accounting audit. `PARTIAL` permits independently valid series and
quarterly-only histories. `UNAVAILABLE` means no compatible statement periods;
`MISSING_INPUT` means insufficient mapped USD facts. `UNSUPPORTED_SECURITY`
identifies funds/index/currency/crypto instruments; `NON_SEC_SOURCE` identifies
foreign-listed exchange suffixes; `UNRESOLVED_SEC_IDENTITY` covers missing,
ambiguous or unconfirmed SEC identities. `UNSUPPORTED_REPORTING_BASIS` identifies
absent compatible U.S. GAAP/10-K/10-Q reporting. `INSUFFICIENT_STRUCTURED_DATA`
identifies an SEC issuer without compatible Company Facts. `MISSING_SEC_IDENTITY` refers to
operator configuration, not company identity. `TRANSPORT_BLOCKED` is a provider
access/network failure and `FINANCIAL_ERROR` a processing failure. These never
prevent market workspaces or combined-report unavailable explanations.

## SEC fair access and efficiency

The private operator configuration is retained. SEC JSON responses are cached
in process for 12 hours, bounded to 128 URLs, and copied before consumers use
them. Cache keys contain URLs, not contacts. Explicit fresh Analyze bypasses the
raw-response cache and Streamlit analysis cache. The Company Facts retrieval
timestamp is preserved on cache reuse. UI horizon/workspace changes reuse the
in-memory result. Live requests remain serially paced at at most two per second
per process, with bounded retries and no retry bypass for HTTP 403/429.

Older submissions are requested only for blocks containing missing mapped-fact
filing dates, up to 64 blocks per analysis. A large insider-filing history no
longer masquerades as a transport failure. Unjoined acceptance timestamps remain
explicitly flagged; missing lineage is not invented or treated as complete.
The response cache is ephemeral and requires no persistent filesystem.

Primary references: [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
describe entity-wide standard facts and submissions identity metadata;
[SEC access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
describes identification and fair-access constraints.

## Actual live coverage snapshot

Snapshot collected 2026-10-05. Counts are **annual / standalone quarterly**
nonmissing observations; they are not proof of continuous coverage. Full counts,
first/last fiscal-period dates, source tags, CIKs and retrieval timestamps for
every mapped core metric and debt component are in
[the coverage evidence CSV](validation/release_a1_sec_coverage.csv).
Quarterly OCF/FCF includes only compatible derived quarters; ROE/ROCE remain annual.

| Issuer | Revenue | Parent income | Diluted EPS | OCF | PPE CapEx | FCF | ROE | ROCE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MSFT | 18/66 | 19/75 | 19/69 | 17/59 | 19/72 | 17/59 | 16/0 | 15/0 |
| KO | 10/33 | 19/68 | 19/51 | 19/65 | 19/65 | 19/63 | 16/0 | 14/0 |
| AAPL | 19/69 | 19/72 | 19/67 | 18/57 | 13/50 | 12/37 | 18/0 | 14/0 |
| NVDA | 18/72 | 19/73 | 19/66 | 19/66 | 3/26 | 3/26 | 16/0 | 16/0 |
| MELI | 5/31 | 18/69 | 18/67 | 17/51 | 16/52 | 15/43 | 13/0 | 11/0 |
| CAT | 10/38 | 3/10 | 17/63 | 12/37 | 8/29 | 8/29 | 0/0 | 10/0 |
| HD | 19/71 | 19/72 | 19/63 | 19/67 | 0/0 | 0/0 | 13/0 | 17/0 |
| DE | 18/68 | 18/68 | 19/65 | 15/47 | 19/63 | 15/46 | 17/0 | 0/0 |
| META | 16/60 | 16/60 | 16/46 | 16/56 | 16/51 | 16/48 | 14/0 | 12/0 |
| JPM | 19/26 | 19/71 | 19/55 | 19/56 | 0/0 | 0/0 | 16/0 | 0/0 |
| BRK.B | 7/46 | 19/69 | 0/0 | 15/43 | 19/70 | 0/0 | 14/0 | 0/0 |

- KO's audited revenue still starts in 2016. NVDA's latest PPE FCF remains missing.
- MELI revenue currently maps only five annual periods (2016–2020); later revenue
  is **not** patched with financial-interest/subcomponent or custom-tag guesses.
  PPE FCF is unavailable in recent years despite other usable statements.
- CAT parent net-income coverage is only three annual periods; earnings available
  to common stockholders is not silently substituted. Parent ROE remains unavailable.
- HD has no compatible mapped PPE cash-payment observations; no FCF is fabricated.
- DE has no valid qualified ROCE in this snapshot; other financial series remain usable.
- JPM and BRK.B verify SIC-based sector exclusions. Their FCF/ROCE are unavailable,
  not zero. BRK.B share-class EPS remains unavailable from these entity-wide tags.
- SAP.DE returns `NON_SEC_SOURCE`; Yahoo workspaces remain independent. Foreign
  private issuers and IFRS/20-F/6-K coverage remain separately scoped.

## Staging checklist

### Validation results

- Initial retained deterministic regression suite: **74 passed**.
- Expanded deterministic suite: **93 passed** (19 additional parameterized cases).
- Opt-in live SEC/Yahoo suite: **22 passed**, including the original four pilot
  issuers, seven generalized/alias issuers, eight Yahoo market symbols and two
  live Yahoo export cases. Generalized SEC report tests combine real SEC facts
  with the deterministic market fixture; the retained MSFT combined/complete
  package test additionally uses real Yahoo and SEC data together.
- Dark/light financial specialist and Combined HTML, portable/CDN payload counts,
  selected ZIP, complete ZIP and provenance CSV tests passed. Full-resolution
  numerical data remains separate from reader-facing abbreviated formatting.
- Compile/import checks and headless Streamlit HTTP health check passed. Existing
  Streamlit interaction tests cover workspace/horizon/export changes without
  additional provider requests. Public source/diff scan found no operator contact,
  credentials, private absolute paths or committed cache/secrets files.
- The first combined live run was blocked by an unreadable local yfinance cache
  database. A writable temporary test cache resolved it; no provider or financial
  formula was changed. Packaged Streamlit startup required its development-mode
  flag disabled locally. Dependency deprecation warnings remain non-failing.
- GitHub Actions and hosted staging status are reported at the branch checkpoint;
  hosted staging is intentionally **not deployed** without separate approval.

Use repository `nayakpranav/equity-lifetime-explorer`, branch
`feature/generalized-sec-release-a1`, entry point `app.py`, with the existing private
SEC operator setting. Do not change the production or historical staging branch.
No hosted staging deployment or merge is performed by this development checkpoint.

Review MELI/CAT/HD/DE/META partial histories, JPM sector exclusions, BRK.B identity,
SAP.DE unavailable financial state, annual/quarter controls, optional price overlay,
source tags/acceptance gaps, specialist/combined HTML, precise CSVs and selected/complete
ZIPs. Chart settings must not retrieve providers again. Use the retained pilot
regression suite to verify KO and NVDA missing-data safeguards.

Release B remains out of scope: latest-disclosed histories are not point-in-time
valuation denominators. Further issuer-specific audits may expand coverage, but
should not weaken accounting definitions to make missing columns appear populated.
