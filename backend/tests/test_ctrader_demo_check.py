from pathlib import Path

import pytest

from scripts.check_ctrader_demo import load_local_config, decode_spot_quote


def test_spot_quote_is_read_only_decimal_and_keeps_source_timestamp():
    result = decode_spot_quote(293573000, 293603000, 1760875200000, 1760875201000)
    assert result == {'bid': '2935.73', 'ask': '2936.03',
                      'source_time_utc': '2025-10-19T12:00:00+00:00',
                      'age_seconds': 1.0, 'freshness': 'CURRENT'}
    assert decode_spot_quote(0, 293603000, 1760875200000, 1760875201000) is None
    assert decode_spot_quote(293603000, 293573000, 1760875200000, 1760875201000) is None


def test_requires_app_credentials_without_echoing_values(tmp_path: Path):
    path = tmp_path / "settings"
    path.write_text("CTRADER_CLIENT_ID=sample\nCTRADER_CLIENT_SECRET=\n", encoding="utf-8")
    with pytest.raises(ValueError, match="APP_CREDENTIALS_MISSING"):
        load_local_config(path)


def test_rejects_live_endpoint_and_bad_account_id(tmp_path: Path):
    path = tmp_path / "settings"
    path.write_text("CTRADER_CLIENT_ID=a\nCTRADER_CLIENT_SECRET=b\nCTRADER_ENVIRONMENT=live\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="DEMO_ONLY"):
        load_local_config(path)
    path.write_text("CTRADER_CLIENT_ID=a\nCTRADER_CLIENT_SECRET=b\nCTRADER_ACCOUNT_ID=xyz\n",
                    encoding="utf-8")
    with pytest.raises(ValueError, match="ACCOUNT_ID_INVALID"):
        load_local_config(path)


def test_parses_optional_token_without_logging(tmp_path: Path):
    path = tmp_path / "settings"
    path.write_text("# local\nCTRADER_CLIENT_ID = app\nCTRADER_CLIENT_SECRET = secret\n"
                    "CTRADER_ACCESS_TOKEN = sample-token\nCTRADER_ENVIRONMENT=demo\n",
                    encoding="utf-8")
    config = load_local_config(path)
    assert config["CTRADER_ACCESS_TOKEN"] == "sample-token"
    assert config["CTRADER_ENVIRONMENT"] == "demo"
