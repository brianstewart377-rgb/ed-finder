#!/usr/bin/env bash
# Backup heartbeat (dead-man's switch). Pings the configured healthchecks URL
# only when pgBackRest itself proves a recent successful backup; pings its
# /fail endpoint when it can prove the opposite. When it cannot run at all
# (no URL, no Python), it sends nothing, so the missing ping alerts instead.
# Exit status alone never stands in for evidence: pgbackrest-operation.sh exits
# 0 on every SKIP, which is why this reads the repository, not the timers.
set -euo pipefail
exec python3.14 -I -S - "$@" <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import urllib.request

CONTAINER = "edfinder-v3-phase4c-full-20260827_r5-postgres"
STANZA = "edfinder_v3"
URL_FILE = Path("/etc/ed-finder/v3-production/backup-heartbeat.url")
URL_FILE_OWNER = 0  # root
# Daily backups: Mon-Sat diff and Sun full at 02:30 UTC (+ up to 15 min), and a
# full backup runs about three hours, so the longest healthy gap between two
# finished backups is about 27 hours. 36 hours keeps headroom and still alerts
# on the same day as any single missed backup.
MAX_AGE_HOURS = 36
BACKUP_TYPES = ("full", "diff", "incr")
URL_PATTERN = re.compile(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/[A-Za-z0-9._~/-]{1,200}")
PING_ATTEMPTS = 3
PING_PAUSE_SECONDS = 2


class ConfigError(Exception):
    pass


def read_url(path: Path | None = None) -> str:
    """The ping URL is a credential: root-owned, private, never printed."""
    path = URL_FILE if path is None else path
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ConfigError("heartbeat_url_file_missing") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_uid != URL_FILE_OWNER or info.st_mode & 0o077:
        raise ConfigError("heartbeat_url_file_not_private_root_file")
    if info.st_size > 512:
        raise ConfigError("heartbeat_url_file_too_large")
    url = path.read_text(encoding="ascii").strip()
    if not URL_PATTERN.fullmatch(url):
        raise ConfigError("heartbeat_url_invalid")
    return url


def read_info() -> object:
    env = {key: value for key, value in os.environ.items() if not key.startswith("DOCKER_")}
    result = subprocess.run(
        ["docker", "--host", "unix:///var/run/docker.sock", "exec", "-u", "postgres", CONTAINER,
         "pgbackrest", f"--stanza={STANZA}", "--log-level-console=off", "--output=json", "info"],
        capture_output=True, text=True, timeout=180, check=False, env=env,
    )
    if result.returncode:
        raise ValueError("pgbackrest_info_failed")
    return json.loads(result.stdout)


def judge(info: object, now: float, max_age_hours: float = MAX_AGE_HOURS) -> tuple[bool, str]:
    """Return (healthy, one-line summary). Anything unproven is unhealthy."""
    if not isinstance(info, list) or len(info) != 1 or not isinstance(info[0], dict):
        return False, "pgbackrest_info_unexpected_shape"
    stanza = info[0]
    status = stanza.get("status")
    if not isinstance(status, dict) or status.get("code") != 0 or status.get("message") != "ok":
        code = status.get("code") if isinstance(status, dict) else None
        return False, f"stanza_status_not_ok code={code}"
    finished = []
    for backup in stanza.get("backup") or []:
        if not isinstance(backup, dict) or backup.get("type") not in BACKUP_TYPES or backup.get("error") is True:
            continue
        stop = (backup.get("timestamp") or {}).get("stop")
        if type(stop) is int and stop > 0:
            finished.append((stop, backup["type"]))
    if not finished:
        return False, "no_successful_backup_recorded"
    stop, kind = max(finished)
    age_hours = (now - stop) / 3600
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stop))
    if age_hours < -0.25:
        return False, f"newest_backup_in_future type={kind} stop={stamp}"
    summary = f"type={kind} stop={stamp} age_hours={age_hours:.1f} max_hours={max_age_hours:g}"
    if age_hours > max_age_hours:
        return False, "newest_backup_too_old " + summary
    return True, "ok " + summary


def ping(url: str, body: str) -> None:
    last: Exception | None = None
    for attempt in range(PING_ATTEMPTS):
        try:
            request = urllib.request.Request(url, data=body.encode("ascii", "replace"), method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:
                if 200 <= response.status < 300:
                    return
                last = RuntimeError(f"status {response.status}")
        except Exception as exc:  # noqa: BLE001 - every transport failure is retried, then reported
            last = exc
        if attempt + 1 < PING_ATTEMPTS:
            time.sleep(PING_PAUSE_SECONDS)
    raise RuntimeError(type(last).__name__ if last else "ping_failed")


def main() -> int:
    try:
        url = read_url()
    except ConfigError as exc:
        # Nothing can be sent, so the check's own silence raises the alert.
        print(f"backup heartbeat: not sent: {exc}")
        return 78
    try:
        healthy, summary = judge(read_info(), time.time())
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        healthy, summary = False, (str(exc) if isinstance(exc, ValueError) and str(exc).isidentifier()
                                   else "pgbackrest_info_unreadable")
    target = url if healthy else url.rstrip("/") + "/fail"
    try:
        ping(target, "ED-Finder V3 backup heartbeat: " + summary)
    except RuntimeError as exc:
        print(f"backup heartbeat: {'healthy' if healthy else 'unhealthy'}: {summary}; ping failed ({exc})")
        return 75
    print(f"backup heartbeat: {'healthy' if healthy else 'unhealthy'}: {summary}; "
          f"{'success' if healthy else 'fail'} ping sent")
    return 0 if healthy else 1


raise SystemExit(main())
PY
