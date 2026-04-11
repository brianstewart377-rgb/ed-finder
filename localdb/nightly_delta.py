#!/usr/bin/env python3
"""
ED:Finder — Nightly Delta Updater
==================================
Downloads and applies the Spansh 1-day delta (galaxy_1day.json.gz) to keep
the local galaxy.db current without re-importing the full 110 GB dump.

Schedule: run once per day via cron or systemd timer.

Usage:
    python3 nightly_delta.py [--db /data/galaxy.db] [--dest /data]

Crontab example (2 AM daily):
    0 2 * * * /usr/local/bin/python3 /app/localdb/nightly_delta.py >> /data/logs/delta.log 2>&1
"""
from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("nightly_delta")

DELTA_1DAY_URL  = "https://downloads.spansh.co.uk/galaxy_1day.json.gz"
DELTA_7DAY_URL  = "https://downloads.spansh.co.uk/galaxy_7day.json.gz"
DEFAULT_DB      = "/data/galaxy.db"
DEFAULT_DEST    = "/data"


def download(url: str, dest: str) -> None:
    tmp = dest + ".tmp"
    log.info("Downloading %s → %s", url, dest)
    t0 = time.time()
    prev_pct = -1

    def _progress(block_num, block_size, total_size):
        nonlocal prev_pct
        downloaded = block_num * block_size
        if total_size > 0:
            pct = int(min(downloaded / total_size * 100, 100))
            if pct != prev_pct and pct % 10 == 0:
                log.info("  %d%% (%.1f GB)", pct, downloaded / 1e9)
                prev_pct = pct

    urllib.request.urlretrieve(url, tmp, _progress)
    os.rename(tmp, dest)
    elapsed = time.time() - t0
    size_gb = os.path.getsize(dest) / 1e9
    log.info("Downloaded %.2f GB in %.0f s", size_gb, elapsed)


def apply_delta(db_path: str, delta_file: str) -> None:
    """Apply delta by calling the import module."""
    # Import here so the script can be called standalone without
    # the full backend being installed
    sys.path.insert(0, os.path.dirname(__file__))
    from import_systems import import_delta
    import_delta(db_path, delta_file)


def record_delta_run(db_path: str) -> None:
    """Write delta_last_run timestamp to import_meta so the UI can display it."""
    ts = datetime.now(timezone.utc).isoformat()
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute(
            "INSERT OR REPLACE INTO import_meta (key, value) VALUES ('delta_last_run', ?)",
            (ts,)
        )
        conn.commit()
        conn.close()
        log.info("Recorded delta_last_run = %s", ts)
    except Exception as exc:
        log.warning("Could not record delta_last_run: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="ED:Finder nightly delta updater")
    parser.add_argument("--db",   default=DEFAULT_DB,   help="Galaxy SQLite DB path")
    parser.add_argument("--dest", default=DEFAULT_DEST, help="Directory to store downloaded delta")
    parser.add_argument("--7day", dest="seven_day", action="store_true",
                        help="Download 7-day delta instead of 1-day")
    args = parser.parse_args()

    url       = DELTA_7DAY_URL if args.seven_day else DELTA_1DAY_URL
    filename  = "galaxy_7day.json.gz" if args.seven_day else "galaxy_1day.json.gz"
    dest_file = os.path.join(args.dest, filename)

    log.info("=== ED:Finder nightly delta — %s ===",
             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    t_total = time.time()

    try:
        download(url, dest_file)
        apply_delta(args.db, dest_file)

        # Clean up delta file to save space (the full dump is the source of truth)
        try:
            os.unlink(dest_file)
            log.info("Deleted temporary delta file: %s", dest_file)
        except OSError:
            pass

        record_delta_run(args.db)

        elapsed = time.time() - t_total
        log.info("Nightly delta complete in %.0f s", elapsed)

    except Exception as exc:
        log.error("Nightly delta FAILED: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
