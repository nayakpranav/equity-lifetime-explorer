from src.validation import _assessment


def test_quality_assessment(synthetic_result):
    assert synthetic_result.provenance.validation_status in {"HIGH", "MEDIUM", "LOW"}
    assert "annual_dividend_aggregation" in set(synthetic_result.validation["check"])
    assert "dollar_volume_integrity" in set(synthetic_result.validation["check"])
