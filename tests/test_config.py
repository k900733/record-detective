import pytest

from vinyl_detective.config import load_config

REQUIRED = {
    "DISCOGS_TOKEN": "test_discogs",
    "EBAY_APP_ID": "test_ebay_app",
    "EBAY_CERT_ID": "test_ebay_cert",
    "TELEGRAM_TOKEN": "test_telegram",
}


def test_load_config_all_keys(monkeypatch):
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    cfg = load_config()
    assert cfg.discogs_token == "test_discogs"
    assert cfg.ebay_app_id == "test_ebay_app"
    assert cfg.ebay_cert_id == "test_ebay_cert"
    assert cfg.telegram_token == "test_telegram"
    assert cfg.db_path == "vinyl_detective.db"
    assert cfg.ebay_poll_minutes == 30
    assert cfg.discogs_refresh_days == 7


def test_load_config_custom_defaults(monkeypatch):
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("DB_PATH", "/tmp/custom.db")
    monkeypatch.setenv("EBAY_POLL_MINUTES", "15")
    monkeypatch.setenv("DISCOGS_REFRESH_DAYS", "3")
    cfg = load_config()
    assert cfg.db_path == "/tmp/custom.db"
    assert cfg.ebay_poll_minutes == 15
    assert cfg.discogs_refresh_days == 3


def test_load_config_missing_key(monkeypatch):
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DISCOGS_TOKEN")
    monkeypatch.setattr("vinyl_detective.config.load_dotenv", lambda: None)
    with pytest.raises(ValueError, match="DISCOGS_TOKEN"):
        load_config()


def test_load_config_multiple_missing(monkeypatch):
    for k in REQUIRED:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("vinyl_detective.config.load_dotenv", lambda: None)
    with pytest.raises(ValueError, match="DISCOGS_TOKEN") as exc_info:
        load_config()
    msg = str(exc_info.value)
    assert "EBAY_APP_ID" in msg
    assert "EBAY_CERT_ID" in msg
    assert "TELEGRAM_TOKEN" in msg
