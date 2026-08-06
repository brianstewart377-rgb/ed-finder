# GlitchTip error tracking

Error tracking is opt-in at every layer: the `glitchtip_*` containers, the
API's error capture, and the frontend's error capture each require their own
explicit configuration. Deploying the compose changes alone starts nothing
and sends no data anywhere.

GlitchTip is a self-hosted, Sentry-API-compatible error tracker. It gets its
own Postgres and Redis (`glitchtip_postgres`, `glitchtip_redis`) — never the
app's — so a GlitchTip migration, restart, or version bump can never touch
app data or the app's migration-ledger discipline (see CLAUDE.md's
"Debugging data drift" section on why that separation matters here).

## 1. Start the stack

```bash
docker compose --profile errortracking up -d
```

This brings up `glitchtip_postgres`, `glitchtip_redis`, a one-shot
`glitchtip_migrate` (Django migrations, unrelated to `sql/NNN_*.sql`), then
`glitchtip_web` (bound to `127.0.0.1:8080`, same loopback-only pattern as
Grafana/Prometheus) and `glitchtip_worker` (Celery + beat).

Required `.env` values before first start:

```dotenv
GLITCHTIP_POSTGRES_PASSWORD=   # openssl rand -hex 24
GLITCHTIP_SECRET_KEY=          # openssl rand -hex 32
```

These use a bare `${VAR}` reference in `docker-compose.yml`, not the `:?`
required-variable syntax used elsewhere — that syntax's error message needs
an unquoted colon (`generate with: openssl ...`), which breaks YAML parsing
in a mapping context and fails the CI `compose validate` job even for
services gated behind `profiles: ["errortracking"]` (profile gating doesn't
skip interpolation at `docker compose config` time). Leaving them unset
prints a compose warning, not an error, and the containers themselves fail
at their own startup instead — same fail-closed outcome, just enforced one
layer up. Matches the existing `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}`
pattern used by the main `postgres` service.

`GLITCHTIP_DOMAIN` defaults to `http://localhost:8080`; set it to the real
public URL if GlitchTip is ever exposed past nginx (not currently wired —
today it's loopback-only, reached via SSH port-forward or a local tunnel).

## 2. Bootstrap the org and project (manual, UI-only)

There's no compose-level bootstrap for this — GlitchTip has no first-run API
for it. Once `glitchtip_web` is healthy:

1. Open `http://127.0.0.1:8080` (port-forward if running against a remote
   host) and create the first user — this is GlitchTip's own account system,
   unrelated to ed-finder's (deferred) accounts work.
2. Create an organization and a project (e.g. project type "Python" for the
   API, "React" for the frontend — or one project for both, either works).
3. Each project's settings page shows a DSN — copy it into `.env` as
   `SENTRY_DSN` (API) and/or `VITE_SENTRY_DSN` (frontend).

## 3. Wire up capture

**API** (`apps/api/src/config.py` / `main.py`): `sentry_sdk.init()` runs only
when `SENTRY_DSN` is set. Because `main.py`'s catch-all `Exception` handler
converts every unhandled error into a JSON response before it can propagate,
it explicitly calls `sentry_sdk.capture_exception(exc)` — sentry_sdk's usual
automatic ASGI-level capture never sees these, since nothing re-raises past
the handler.

**Frontend** (`frontend/src/main.tsx`): `Sentry.init()` runs only when
`VITE_SENTRY_DSN` is present at build time (it's inlined by Vite like any
other `VITE_`-prefixed variable — set it in the shell or `.env` *before*
`yarn build`, not after). `ErrorBoundary.componentDidCatch` calls
`Sentry.captureException` so the same critical-UI-error path that currently
only logs to the console also reaches GlitchTip.

Set `SENTRY_DSN` / `VITE_SENTRY_DSN` blank (the default) to leave both call
sites as documented no-ops — `sentry_sdk.capture_exception` and
`Sentry.captureException` are safe to call uninitialized.

Redeploying with a DSN set follows the normal sequence — see CLAUDE.md's
"Frontend deployment" section; `VITE_SENTRY_DSN` must be exported into the
shell (or present in `frontend/.env`) before the `yarn build` step for it to
be baked into the bundle.

## 4. Optional: Grafana datasource

`config/grafana/provisioning/datasources/glitchtip.yml` provisions GlitchTip
as a Grafana data source (community `grafana-sentry-datasource` plugin,
installed via `GF_INSTALL_PLUGINS` in `docker-compose.yml`) so error-rate
trends sit next to the existing infra dashboards. This is independent of
whether the monitoring profile or the errortracking profile is running —
Grafana provisions the datasource either way, it just has nothing to query
until `glitchtip_web` is up and a token is configured.

To wire it:

1. In GlitchTip, create an **internal integration** with Read access to
   Project, Issue & Event, and Organization — this yields an auth token
   (distinct from the project DSNs above).
2. Write only that token to `config/glitchtip_grafana_auth_token.local`
   (never commit it — same pattern as `grafana_admin_password.local` in
   `docs/operations/monitoring.md`).
3. Set in `.env`:
   ```dotenv
   GLITCHTIP_GRAFANA_ORG_SLUG=<your-org-slug>
   GLITCHTIP_GRAFANA_AUTH_TOKEN_FILE=./config/glitchtip_grafana_auth_token.local
   ```
4. Restart Grafana: `docker compose up -d grafana`.

Leaving `GLITCHTIP_GRAFANA_ORG_SLUG` at its `not-configured` default and the
token file at the committed `config/glitchtip_grafana_auth_token.disabled`
placeholder leaves the datasource provisioned but unauthenticated — Grafana
surfaces that as a datasource-level auth error, not a startup failure
(`config/grafana/start-with-secret.sh` treats a missing/placeholder token as
non-fatal, unlike the Grafana admin password).

## Stopping / disabling

```bash
docker compose --profile errortracking stop \
  glitchtip_web glitchtip_worker glitchtip_migrate glitchtip_redis glitchtip_postgres
```

Named volumes (`glitchtip_postgres_data`) are retained between rehearsals,
matching the monitoring stack's convention. To fully disable error capture
without stopping the containers, blank `SENTRY_DSN` and `VITE_SENTRY_DSN`
(rebuild the frontend for the latter to take effect) — both call sites
degrade to no-ops.
