FROM postgres:16-alpine

# We use the official postgres:16-alpine image as a base because it
# already has psql, libpq, and a thin runtime — no point pulling
# alpine then re-installing 100 MB of psql client packages on top.
#
# Add `dcron` for the nightly schedule. We deliberately do NOT install
# the full BusyBox cron — dcron's `crond -f` runs in foreground which
# plays nicely with `docker logs`.
RUN apk add --no-cache dcron tini bash

WORKDIR /maintenance

# Copy the maintenance script and crontab.
COPY scripts/run_maintenance.sh /usr/local/bin/run_maintenance.sh
COPY scripts/crontab            /etc/crontabs/root
RUN chmod +x /usr/local/bin/run_maintenance.sh

# tini = proper PID 1 so SIGTERM from `docker stop` actually reaches
# crond and any in-progress psql.
ENTRYPOINT ["/sbin/tini", "--"]

# `crond -f -l 8 -L /dev/stdout` = foreground, log level 8 (debug),
# log to stdout. So `docker compose logs maintenance` shows every
# scheduled run.
CMD ["crond", "-f", "-l", "8", "-L", "/dev/stdout"]
