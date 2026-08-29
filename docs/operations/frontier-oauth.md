# Frontier OAuth and owner access

ED-Finder uses Frontier OAuth for commander accounts. The production client is
registered with the exact callback:

```text
https://ed-finder.app/api/auth/frontier/callback
```

## Production configuration

Set these values in the production `.env`; never commit their values:

```dotenv
FRONTIER_CLIENT_ID=<Frontier client ID>
FRONTIER_CLIENT_SECRET=<Frontier shared key>
FRONTIER_REDIRECT_URI=https://ed-finder.app/api/auth/frontier/callback
AUTH_COOKIE_SECURE=true
ADMIN_TOKEN=<existing high-entropy admin token>
```

`docker-compose.yml` passes them only to the API container. The shared key is
never added to the frontend build.

Migration `048_frontier_accounts.sql` must be applied before enabling login.
The normal deployment wrapper applies this manifest-listed migration.

## Link the first owner

1. Deploy the migration, API, and frontend with the OAuth settings above.
2. Open ED-Finder and choose **Sign in**.
3. Authorize ED-Finder on Frontier's site.
4. Open **Ops**. On first setup, enter the existing `ADMIN_TOKEN` once to link
   that signed-in Frontier account as ED-Finder's owner.
5. Sign out and back in to verify that **Ops**, Admin, and Operator are visible
   without entering an admin token again.

The owner claim is single-use: after an owner exists, another commander cannot
claim the role through the UI. `FRONTIER_OWNER_CUSTOMER_IDS` is an optional
comma-separated recovery allowlist when the stable Frontier customer ID is
already known.

## Security and privacy boundaries

- OAuth uses Authorization Code flow with PKCE and a one-time, expiring state.
- Browser sessions are opaque random tokens; only SHA-256 token digests are
  stored in PostgreSQL.
- Cookies are HTTP-only, Secure, SameSite=Lax, and expire after seven days.
- Owner-authorized writes also require a trusted `Origin`, protecting sibling
  subdomains from CSRF.
- Existing `ADMIN_TOKEN` automation remains available for host-side scripts.
- Admin, Operator, detailed status, and cache diagnostics require owner access.
- Prometheus remains blocked at the public edge; Grafana and Prometheus remain
  bound to loopback-only host ports.
- The public `/api/health` deployment probe remains available for uptime and
  release verification.
- ED-Finder stores only the stable Frontier account ID and Commander name.
  OAuth access/refresh tokens and all other CAPI profile fields are discarded.

The first slice establishes identity and owner access. Cross-device colony-plan
sync and on-demand current-location lookup are separate follow-up slices.
