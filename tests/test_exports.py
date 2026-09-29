import io
import zipfile

from src.exports import export_bundle, historical_csv, zip_bytes


def test_html_csv_and_zip_are_in_memory(synthetic_result):
    files = export_bundle(
        synthetic_result,
        ["lifetime_html", "volume_html", "dividend_html", "history_csv", "actions_csv", "dividend_csv", "validation_csv"],
        theme="dark",
    )
    assert len(files) == 7
    assert any(name.endswith(".html") and payload.startswith(b"<!doctype html>") for name, payload in files.items())
    history = next(payload for name, payload in files.items() if "lifetime_history" in name)
    assert b"relative_volume_20" in history and b"ttm_dividend_yield" in history
    package = zip_bytes(files)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        assert set(archive.namelist()) == set(files)


def test_cdn_and_portable_modes(synthetic_result):
    small = export_bundle(synthetic_result, ["lifetime_html"], portable_html=False)
    portable = export_bundle(synthetic_result, ["lifetime_html"], portable_html=True)
    assert len(next(iter(small.values()))) < len(next(iter(portable.values())))
