"""Public-safe source labels and currency/share-basis overlay eligibility."""


def financial_source_caption(result):
    identity = result.identity
    if identity is None:
        return result.source
    return (f"{result.source} · {identity.issuer_name} · {identity.issuer_id} · "
            f"{identity.accounting_framework} · reporting currency {identity.reporting_currency} · "
            f"basis {identity.consolidation_basis}")


def price_overlay_unavailable_reason(result, market):
    if result.identity is None or market is None or result.ticker != market.ticker:
        return "The financial issuer/listing relationship is unavailable."
    identity = result.identity
    if identity.reporting_currency != market.metadata.currency:
        return "Statement and market-price currencies differ; no hidden FX conversion is applied."
    # Preserve the validated US GAAP exact-listing implementation. New foreign
    # issuer routes require independently verified security/share compatibility.
    if not identity.share_basis_verified and not (
        identity.accounting_framework == "US_GAAP" and identity.identity_method == "exact_ticker"
    ):
        return "Issuer financial statements are available, but listing/share-basis compatibility is unverified."
    return None
