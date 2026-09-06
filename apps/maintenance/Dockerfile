FROM python:3.14-alpine

# LEGACY SELF-HOST / LOCAL-CI IMAGE — NEVER V3 PRODUCTION OR BACKUP AUTHORITY.
# The retained root Compose environment still uses PostgreSQL 16. Current V3
# production uses PostgreSQL 18 and requires an explicitly current backup/PITR
# runbook and runtime definition; this client-only helper deliberately does not
# define either database runtime.

# Add `dcron` for the nightly schedule. We deliberately do NOT install
# the full BusyBox cron — dcron's `crond -f` runs in foreground which
# plays nicely with `docker logs`.
#
# Exact CPython 3.14 + pinned Psycopg 3 let this legacy sidecar run its guarded
# invariants wrapper directly on its weekly schedule, `rclone`
# provides the optional offsite backup sync path, and `curl` sends the
# optional dead-man's-switch heartbeats.
RUN apk add --no-cache dcron tini bash postgresql-client rclone curl && \
    python -m pip install --no-cache-dir 'psycopg[binary]==3.3.4' && \
    python -c "import platform, psycopg, sys; assert platform.python_implementation() == 'CPython'; assert sys.version_info[:2] == (3, 14); assert psycopg.__version__ == '3.3.4'"

WORKDIR /opt/ed-finder

# Copy the maintenance/backup scripts and crontab.
COPY apps/maintenance/scripts/run_maintenance.sh           /usr/local/bin/run_maintenance.sh
COPY apps/maintenance/scripts/run_backup.sh                /usr/local/bin/run_backup.sh
COPY apps/maintenance/scripts/run_ingest_watchdog.sh       /usr/local/bin/run_ingest_watchdog.sh
COPY apps/maintenance/scripts/run_disk_watchdog.sh         /usr/local/bin/run_disk_watchdog.sh
COPY apps/maintenance/scripts/crontab                      /etc/crontabs/root
COPY scripts/run_data_invariants_receipted.sh              /usr/local/bin/run_data_invariants_receipted.sh
COPY scripts/checks/data_invariants.py                     /opt/ed-finder/scripts/checks/data_invariants.py
COPY shared_contracts/__init__.py                          /opt/ed-finder/shared_contracts/__init__.py
COPY shared_contracts/data_invariant_contracts.py          /opt/ed-finder/shared_contracts/data_invariant_contracts.py
RUN chmod +x /usr/local/bin/run_maintenance.sh /usr/local/bin/run_backup.sh /usr/local/bin/run_ingest_watchdog.sh /usr/local/bin/run_disk_watchdog.sh /usr/local/bin/run_data_invariants_receipted.sh

# tini = proper PID 1 so SIGTERM from `docker stop` actually reaches
# crond and any in-progress psql.
ENTRYPOINT ["/sbin/tini", "--"]

# `crond -f -l 8 -L /dev/stdout` = foreground, log level 8 (debug),
# log to stdout. So `docker compose logs maintenance` shows every
# scheduled run.
CMD ["crond", "-f", "-l", "8", "-L", "/dev/stdout"]
