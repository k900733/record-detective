import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    discogs_token: str
    ebay_app_id: str
    ebay_cert_id: str
    telegram_token: str
    db_path: str = "vinyl_detective.db"
    ebay_poll_minutes: int = 30
    discogs_refresh_days: int = 7
    affiliate_campaign_id: str = ""


_REQUIRED_KEYS = ("DISCOGS_TOKEN", "EBAY_APP_ID", "EBAY_CERT_ID", "TELEGRAM_TOKEN")


def load_config() -> Config:
    load_dotenv()
    missing = [k for k in _REQUIRED_KEYS if not os.environ.get(k)]
    if missing:
        raise ValueError(f"Missing required env var(s): {', '.join(missing)}")
    return Config(
        discogs_token=os.environ["DISCOGS_TOKEN"],
        ebay_app_id=os.environ["EBAY_APP_ID"],
        ebay_cert_id=os.environ["EBAY_CERT_ID"],
        telegram_token=os.environ["TELEGRAM_TOKEN"],
        db_path=os.environ.get("DB_PATH", "vinyl_detective.db"),
        ebay_poll_minutes=int(os.environ.get("EBAY_POLL_MINUTES", "30")),
        discogs_refresh_days=int(os.environ.get("DISCOGS_REFRESH_DAYS", "7")),
        affiliate_campaign_id=os.environ.get("AFFILIATE_CAMPAIGN_ID", ""),
    )
