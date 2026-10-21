"""Daily database backup: pg_dump (custom format, already compressed) -> storage backups/."""
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CONFIG

log = logging.getLogger(__name__)


def backup(storage):
    day = datetime.now(ZoneInfo(CONFIG.timezone)).date()
    key = f"backups/catalogue-{day}.dump"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "catalogue.dump"
        subprocess.run(["pg_dump", "--format=custom", f"--file={path}", f"--dbname={CONFIG.db}"], check=True)
        storage.put(key, path.read_bytes(), "application/octet-stream")
        size = path.stat().st_size
    log.info("backup saved: %s (%.1f MB)", key, size / 1e6)
    return key
