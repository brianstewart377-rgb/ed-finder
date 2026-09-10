# Frontier OAuth V3 staging and cutover

The implementation reuses the proven behavior from PR #490 and adapts its
storage/API boundary to the locked V3 identity model. It does not replace or
reroute the live V2 login before controlled cutover.

PR #490 was never deployed and contains no production OAuth state to migrate.
It is superseded reference evidence, not a migration ancestor. The V3 database
authority is `sql/v3/migration-manifest.txt`: frozen baseline
`001_v3_baseline.sql`, followed first by `002_v3_accounts_identity.sql`, with
checksums recorded in `v3_meta.schema_migration` by the explicit V3 runner.
Neither `sql/048_frontier_accounts.sql` nor any V2 OAuth-shaped table is part of
the V3 chain.

## Contract and registered callback

The permanent V3 endpoints are:

```text
GET    /api/v1/auth/frontier/login
GET    /api/v1/auth/frontier/callback
POST   /api/v1/auth/frontier/link
GET    /api/v1/auth/session
POST   /api/v1/auth/logout
POST   /api/v1/auth/owner/claim
DELETE /api/v1/auth/identities/{external_identity_id}
```

Frontier remains registered to this production callback:

```text
https://ed-finder.app/api/auth/frontier/callback
```

The API therefore exposes that callback as an OpenAPI-hidden compatibility
alias to the same V3 handler. No other V2 auth route is retained. The V3 login
request and server-side token exchange continue to send the registered URI.

## Secret custody

Required values are `FRONTIER_CLIENT_ID`, `FRONTIER_CLIENT_SECRET`, and
`FRONTIER_REDIRECT_URI`. On the new host they are staged outside Git at:

```text
/etc/edfinder-v3/frontier-oauth.env
```

The file must remain root-owned mode `0600`. Load the normal deployment env
first, then pass this file as an additional final Compose `--env-file`; do not
use the three-line OAuth file as the deployment's only env source. Do not copy
it into a checkout, build context, frontend environment, image layer,
transcript, or evidence bundle.

## Staging rule

Local and isolated tests mock Frontier. Do not route the public callback to the
new host while V2 is live. A real browser smoke is deferred to controlled
production-readiness/cutover unless a separately registered staging callback is
approved by Frontier and the owner.

## Production activation blockers

`FRONTIER_OAUTH_RATE_LIMIT_CLIENT_IDENTITY: BLOCKED`

The repository represents `Cloudflare -> nginx -> API/Uvicorn`, but it does not
yet prove a trustworthy per-client address at the application boundary.
nginx keys `limit_req` on its apparent peer address and forwards
`X-Forwarded-For`; Uvicorn's production command does not name the nginx Docker
source as a trusted forwarded proxy, and the Docker network has no pinned
subnet. SlowAPI therefore retains `get_remote_address` only as coarse defence
in depth. It is not production-verified per-client OAuth throttling. Do not set
`FORWARDED_ALLOW_IPS=*`, trust arbitrary forwarded headers, or guess a Docker or
Cloudflare range.

Before production activation, controlled network evidence must prove all of
the following:

- direct origin access is restricted to the approved edge/operations paths;
- nginx derives the client address only from a maintained, authenticated or
  allowlisted Cloudflare edge boundary and rejects spoofed inbound forwarding
  headers;
- Uvicorn trusts only the proven nginx-to-API source boundary;
- two controlled client addresses produce distinct SlowAPI keys, while a
  forged `X-Forwarded-For` or `CF-Connecting-IP` cannot choose a key; and
- nginx and application limits still fail safely across restart and the
  single-worker runtime actually deployed.

`FRONTIER_OAUTH_QUERY_LOG_REDACTION: REQUIRED_BEFORE_PRODUCTION_ACTIVATION`

Repository-level controls remove query strings for both callback paths from
the nginx access format, Uvicorn access records, FastAPI problem instances and
generic exception messages, and Sentry/GlitchTip request events. Ordinary
request logging remains unchanged. Production activation still requires a
synthetic canary callback whose unique fake `code` and `state` are absent from
nginx access/error logs, API/container logs, retained log-driver output, and
Sentry/GlitchTip events. This controlled proof is necessary because native
nginx error-log and deployed log-aggregation behavior cannot be established
from repository configuration alone.

## Security properties

- Authorization Code with PKCE S256.
- Random one-time state stored only as a SHA-256 digest, ten-minute expiry, and
  delete-on-consume replay prevention.
- Server-side token exchange; identity-only `scope=auth`; `/decode` and `/me`
  issuer/subject validation; provider tokens discarded.
- Safe relative `return_to`, exact trusted-Origin checks on cookie-authorized
  writes, and coarse defence-in-depth limits on
  login/link/callback/bootstrap/unlink. Per-client production identity remains
  blocked on the controlled proxy-trust proof above.
- Opaque rotating sessions with only token digests in PostgreSQL, idle and
  absolute expiry, recent-auth enforcement, revocation, and secure cookies.
- UUID account authority, unique provider issuer/subject mapping, separate
  Commander records, role assignments, and security audit events.
