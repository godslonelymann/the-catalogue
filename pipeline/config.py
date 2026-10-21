"""Settings, read from environment variables and an optional .env file in the project root."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    # Values already set in the environment win over the file.
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    db: str = os.environ.get("CATALOGUE_DB", "dbname=catalogue")
    storage: str = os.environ.get("CATALOGUE_STORAGE", "s3://the-catalogue-raw-anurag")
    aws_region: str = os.environ.get("AWS_REGION", "ap-south-1")
    telegram_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_username: str = os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@")
    request_delay: float = float(os.environ.get("CATALOGUE_REQUEST_DELAY", "1"))
    user_agent: str = "Mozilla/5.0 (compatible; the-catalogue/1.0)"
    timezone: str = "Asia/Kolkata"


CONFIG = Config()
