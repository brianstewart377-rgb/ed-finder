FROM postgres:16-alpine

# We use the official postgres:16-alpine image as a base because it
# already has psql, libpq, and a thin runtime — no point pulling
# alpine then re-installing 100 MB of psql client packages on top.
#
# Add `dcron` for the nightly schedule. We deliberately do NOT install
# the full BusyBox cron — dcron's `crond -f` runs in foreground which
# plays nicely with `docker logs`.
#
# `python3` + `py3-psycopg2` let the sidecar run the production-safe
# invariants wrapper directly on its weekly schedule, and `rclone`
# provides the optional offsite backup sync path.
RUN apk add --no-cache dcron tini bash python3 py3-psycopg2 rclone

WORKDIR /opt/ed-finder

# Copy the maintenance/backup scripts and crontab.
COPY apps/maintenance/scripts/run_maintenance.sh           /usr/local/bin/run_maintenance.sh
COPY apps/maintenance/scripts/run_backup.sh                /usr/local/bin/run_backup.sh
COPY apps/maintenance/scripts/crontab                      /etc/crontabs/root
COPY scripts/run_data_invariants_receipted.sh              /usr/local/bin/run_data_invariants_receipted.sh
COPY scripts/checks/data_invariants.py                     /opt/ed-finder/scripts/checks/data_invariants.py
COPY shared_contracts/__init__.py                          /opt/ed-finder/shared_contracts/__init__.py
COPY shared_contracts/data_invariant_contracts.py          /opt/ed-finder/shared_contracts/data_invariant_contracts.py
RUN chmod +x /usr/local/bin/run_maintenance.sh /usr/local/bin/run_backup.sh /usr/local/bin/run_data_invariants_receipted.sh

# tini = proper PID 1 so SIGTERM from `docker stop` actually reaches
# crond and any in-progress psql.
ENTRYPOINT ["/sbin/tini", "--"]

# `crond -f -l 8 -L /dev/stdout` = foreground, log level 8 (debug),
# log to stdout. So `docker compose logs maintenance` shows every
# scheduled run.
CMD ["crond", "-f", "-l", "8", "-L", "/dev/stdout"]
