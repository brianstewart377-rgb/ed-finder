# Frontier OAuth and owner access

ED-Finder uses Frontier OAuth for commander accounts. The application contract
and security properties in this document are current, but the former V2
production provisioning procedure is retired.

The production OAuth client is registered with the exact callback:

```text
https://ed-finder.app/api/auth/frontier/callback
```

## V3 production configuration boundary

This document does **not** authorize placing production secrets in the
repository checkout, the root compatibility Compose file, or any retired V2
deployment path.

The repository does not currently contain a reviewed V3 production
secret-provisioning/deployment runbook for Frontier OAuth. Until one is added,
production OAuth enablement, credential rotation, and recovery must fail closed:

- do not use root `docker-compose.yml` as V3 production authority;
- do not use the retired `scripts/deploy_main.sh` tombstone or any deleted V2
  release wrapper;
- do not commit, print, or place Frontier shared keys or admin credentials in
  source-controlled configuration;
- use only an explicitly current V3 operator workflow/runbook that identifies
  the replacement host, the intended API service, and the approved secret
  source;
- preserve the callback above unless Frontier registration and the reviewed V3
  configuration are deliberately changed together.

The current read-only `v3-app-status` operator action may verify that the public
and loopback API health/session surfaces are valid and that the Frontier login,
callback, session, logout, and owner-claim routes are present. It deliberately
does not start an OAuth login or read secret values.

Migration `048_frontier_accounts.sql` is the repository migration that creates
the Frontier account/session foundation. Its presence does not authorize
applying it to production through a retired deployment wrapper. Production
migration execution requires an explicitly current V3 migration/deployment
path and exact-target evidence.

## Required V3 configuration contract

When the V3 provisioning path is implemented, the API must receive equivalent
configuration for:

- Frontier client ID;
- Frontier client secret/shared key through the approved V3 secret mechanism;
- redirect URI `https://ed-finder.app/api/auth/frontier/callback`;
- secure production cookies;
- the existing high-entropy admin/owner bootstrap credential through the
  approved V3 secret mechanism.

The shared key is API-only and must never be included in a frontend build or
browser-visible configuration.

## Link the first owner

Only after the V3 operator path has proved the migration, API configuration,
public callback route, and secret boundary:

1. Open ED-Finder and choose **Sign in**.
2. Authorize ED-Finder on Frontier's site.
3. Return through the registered callback and verify an authenticated session.
4. Open **Ops**. On first setup, use the approved owner-bootstrap path to link
   that signed-in Frontier account as ED-Finder's owner.
5. Sign out and back in to verify that **Ops**, Admin, and Operator access are
   restored without repeating the bootstrap step.

The owner claim is single-use: after an owner exists, another commander cannot
claim the role through the UI. `FRONTIER_OWNER_CUSTOMER_IDS` remains an optional
recovery allowlist when the stable Frontier customer ID is already known, but
its production configuration is subject to the same V3 secret/config boundary.

## Security and privacy boundaries

- OAuth uses Authorization Code flow with PKCE and a one-time, expiring state.
- Browser sessions are opaque random tokens; only SHA-256 token digests are
  stored in PostgreSQL.
- Production cookies are HTTP-only, Secure, SameSite=Lax, and expire after seven
  days.
- Owner-authorized writes also require a trusted `Origin`, protecting sibling
  subdomains from CSRF.
- Admin, Operator, detailed status, and cache diagnostics require owner access.
- Prometheus remains blocked at the public edge.
- The public `/api/health` deployment probe remains available for bounded
  release/liveness verification.
- ED-Finder stores only the stable Frontier account ID and Commander name.
  OAuth access/refresh tokens and other CAPI profile fields are discarded by
  this identity slice.

The first slice establishes identity and owner access. Cross-device colony-plan
sync and on-demand current-location lookup remain separate follow-up slices.
