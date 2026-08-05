# Production monitoring

The monitoring profile is deliberately opt-in. Normal application deploys do
not start or restart Grafana, Prometheus, or the exporters.

## Local production files

Create these three ignored files on the production host. Never commit their
contents:

| File | Contents |
| --- | --- |
| `config/grafana_admin_password.local` | The Grafana admin password only |
| `config/healthchecks_readonly_api_key.local` | The Healthchecks.io read-only `hcr_` key only |
| `config/healthchecks_targets.local.yml` | A copy of the example target file with the real project UUID |

The production `.env` must contain:

```dotenv
GRAFANA_USER=admin
GRAFANA_PASSWORD_FILE=./config/grafana_admin_password.local
HEALTHCHECKS_PROMETHEUS_TOKEN_FILE=./config/healthchecks_readonly_api_key.local
HEALTHCHECKS_PROMETHEUS_TARGETS_FILE=./config/healthchecks_targets.local.yml
```

Do not add `GRAFANA_PASSWORD` to `.env`. The password belongs only in the
ignored password file.

## Prepare permissions

Run this from `/opt/ed-finder` as root:

```bash
bash scripts/prepare_monitoring.sh
```

This command does not start containers. It only validates the three local
files and applies the ownership required by the non-root images:

| File | Owner | Mode |
| --- | --- | --- |
| Grafana password | `472:0` | `0400` |
| Healthchecks.io key | `65534:65534` | `0400` |
| Healthchecks.io targets | `0:0` | `0644` |

To verify the files later as root without changing anything:

```bash
bash scripts/prepare_monitoring.sh --check
```

The helper reports filenames and permissions only. It never prints secret
contents.

## Start a rehearsal

Prepare permissions first, then start only the monitoring services:

```bash
docker compose --profile monitoring up -d --no-deps \
  postgres_exporter postgres_custom_exporter redis_exporter prometheus grafana
```

The main application containers are not recreated by this command. Grafana and
Prometheus remain bound to loopback-only host ports:

- Grafana: `127.0.0.1:3000`
- Prometheus: `127.0.0.1:9090`
- PostgreSQL exporter: `127.0.0.1:9187`
- ED Finder SQL exporter: `127.0.0.1:9399`
- Redis exporter: `127.0.0.1:9121`

Check the service state:

```bash
docker compose --profile monitoring ps
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://127.0.0.1:3000/api/health
```

Stop only the rehearsal services:

```bash
docker compose --profile monitoring stop \
  grafana prometheus postgres_exporter postgres_custom_exporter redis_exporter
```

Named Prometheus and Grafana volumes are intentionally retained between
rehearsals.

## PostgreSQL metrics split

`postgres_exporter` provides the standard `pg_*` families. The separate SQL
Exporter runs ED Finder's deployment-specific queries and exposes the
`ed_finder_dirty_counts_*`, import-progress, table-size, and slow-query
families. Those custom queries are cached for five minutes and limited to one
database connection.
