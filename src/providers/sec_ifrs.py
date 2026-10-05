"""SEC IFRS extension reusing the validated identified transport and cache.

20-F/40-F annual facts only. 6-K interim reports are not assumed compatible.
The original US GAAP provider remains the first route for exact SEC listings.
"""

import hashlib
from dataclasses import replace

from ..financial_models import SecurityIdentity
from ..financials.ifrs_concepts import IFRS_ANNUAL_FORMS, ifrs_mappings
from .sec import (
    SecFinancialPayload, SecFinancialProvider, UnsupportedReportingBasis,
    UnsupportedSecIdentity, MissingStructuredData, listing_key,
)


# A verified listing relationship, not a name-similarity alias. SAP's primary
# stock page identifies the EUR ordinary share and its NYSE ADR; 1 ADR = 1 share.
SEC_LISTING_LINKS = {
    "SAP.DE": ("SAP", "0001000184", "https://www.sap.com/investors/en/stock/basic-data.html"),
}


class GlobalSecFinancialProvider(SecFinancialProvider):
    def fetch(self, metadata, *, force_refresh=False):
        ticker = metadata.ticker.upper().strip()
        link = SEC_LISTING_LINKS.get(ticker)
        lookup = replace(metadata, ticker=link[0]) if link else metadata
        try:
            payload = super().fetch(lookup, force_refresh=force_refresh)
            annual_filings = [row for row in payload.accession_ledger.values()
                if row.get("form") in {*IFRS_ANNUAL_FORMS, "10-K", "10-K/A"}]
            if annual_filings:
                newest = max(row.get("filing_date") or "" for row in annual_filings)
                if any(row.get("form") in IFRS_ANNUAL_FORMS and row.get("filing_date") == newest
                       for row in annual_filings):
                    # Old 10-K facts must not hide a subsequent IFRS reporting
                    # transition or cause the current FPI to use GAAP mappings.
                    raise UnsupportedReportingBasis("Latest verified annual form requires the separate foreign-private-issuer route")
            if link:
                if payload.identity.cik != link[1]:
                    raise UnsupportedSecIdentity("Verified foreign listing CIK mismatch")
                return replace(payload, identity=replace(payload.identity, ticker=ticker,
                    security_id=f"{payload.identity.issuer_id}:{ticker}",
                    identity_method="verified_cross_listing", identity_evidence_url=link[2]))
            return payload
        except UnsupportedReportingBasis:
            pass
        directory, _ = self._json("https://www.sec.gov/files/company_tickers.json")
        matches = [row for row in directory.values() if listing_key(str(row.get("ticker", ""))) == listing_key(lookup.ticker)]
        if len(matches) != 1:
            raise UnsupportedSecIdentity("No unique exact SEC foreign-private-issuer ticker")
        cik = f"{int(matches[0]['cik_str']):010d}"
        if link and cik != link[1]:
            raise UnsupportedSecIdentity("Verified foreign listing CIK mismatch")
        submissions, raw_submissions = self._json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        if str(submissions.get("cik", "")).lstrip("0") != str(int(cik)):
            raise UnsupportedSecIdentity("SEC submissions CIK mismatch")
        if sum(listing_key(value) == listing_key(lookup.ticker) for value in submissions.get("tickers", [])) != 1:
            raise UnsupportedSecIdentity("SEC submissions do not verify this listed security")
        year_end = str(submissions.get("fiscalYearEnd", ""))
        if len(year_end) != 4 or not year_end.isdigit():
            raise UnsupportedSecIdentity("Unverified fiscal year end")
        facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        facts, raw_facts = self._json(facts_url)
        if str(facts.get("cik", "")).lstrip("0") != str(int(cik)):
            raise UnsupportedSecIdentity("SEC Company Facts CIK mismatch")
        taxonomy = facts.get("facts", {}).get("ifrs-full", {})
        if not taxonomy:
            raise MissingStructuredData("No structured IFRS Company Facts are available")
        # Native currency comes from the latest annual revenue disclosure, not
        # the ADR/listing currency. Multiple native units are an explicit conflict.
        currency_tags = ["Revenue"] if taxonomy.get("Revenue", {}).get("units") else [
            mapping.tag for mapping in ifrs_mappings("USD") if not mapping.concept.startswith("eps_")]
        revenue = [(row.get("filed", ""), unit) for tag in currency_tags
                   for unit, rows in taxonomy.get(tag, {}).get("units", {}).items()
                   for row in rows if row.get("form") in IFRS_ANNUAL_FORMS and len(unit) == 3 and unit.isupper()]
        if not revenue:
            raise UnsupportedReportingBasis("Native IFRS reporting currency could not be verified from annual monetary facts")
        latest_date = max(date for date, _ in revenue)
        currencies = {unit for date, unit in revenue if date == latest_date}
        if len(currencies) != 1:
            raise UnsupportedReportingBasis("Latest IFRS disclosure has ambiguous reporting currencies")
        currency = currencies.pop()
        filings = submissions.get("filings", {})
        ledger = self._ledger(filings.get("recent", {}))
        mappings = ifrs_mappings(currency)
        needed = {row['accn']: row['filed'] for mapping in mappings
                  for row in taxonomy.get(mapping.tag, {}).get("units", {}).get(mapping.unit, [])
                  if row.get("form") in IFRS_ANNUAL_FORMS and row.get("accn") and row.get("filed") and row['accn'] not in ledger}
        digest = hashlib.sha256(raw_facts + raw_submissions)
        loaded = 0
        older_files = filings.get("files", [])
        for entry in older_files:
            dates = [date for accession, date in needed.items() if accession not in ledger]
            if not dates or loaded >= 64:
                break
            if not any(entry.get("filingFrom", "") <= date <= entry.get("filingTo", "9999") for date in dates):
                continue
            name = entry.get("name", "")
            if not name.startswith(f"CIK{cik}-submissions-") or not name.endswith(".json") or "/" in name or "\\" in name:
                continue
            older, raw = self._json(f"https://data.sec.gov/submissions/{name}")
            ledger.update(self._ledger(older)); digest.update(raw); loaded += 1
        if not {row.get("form") for row in ledger.values()}.intersection(IFRS_ANNUAL_FORMS):
            raise UnsupportedReportingBasis("Verified 20-F/40-F annual submissions are unavailable")
        identity = SecurityIdentity(ticker=ticker, cik=cik,
            issuer_name=str(submissions.get("name") or ticker), issuer_id=f"SEC:CIK{cik}",
            security_id=f"SEC:CIK{cik}:{ticker}", exchange=metadata.exchange,
            reporting_currency=currency, fiscal_year_end=year_end, sec_ticker=lookup.ticker,
            identity_method="verified_cross_listing" if link else "exact_sec_listing",
            sic=str(submissions.get("sic") or "") or None, sic_description=submissions.get("sicDescription"),
            accounting_framework="IFRS", identity_evidence_url=link[2] if link else f"https://data.sec.gov/submissions/CIK{cik}.json",
            share_basis_verified=bool(link))
        return SecFinancialPayload(identity, facts, ledger, self._response_times[facts_url],
                                   digest.hexdigest(), len(older_files), loaded, taxonomy="ifrs-full")
