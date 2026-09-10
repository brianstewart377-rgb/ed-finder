# V3 Frontier identity decision

Status: locked for the bounded identity foundation authorized 2026-08-26.

## Authorities

- `v3_identity.account.account_id` (UUID) is the durable ED-Finder identity.
- A Frontier login proves one `v3_identity.external_identity` tuple: provider
  `frontier`, issuer `https://auth.frontierstore.net`, and the stable verified
  parent/customer subject returned by Frontier `/decode` and `/me`.
- Provider subjects are never account primary keys. Email, real name,
  Commander display name, and legacy `sync_key` are never login identity.
- Commander data is mutable domain/display data in `v3_identity.commander`, separate from
  authentication. Normal identity login does not request it.
- Roles are assignments in `v3_identity.account_role`; there is no owner
  boolean on `v3_identity.account`.

## Linking and conflict behavior

Normal login creates a UUID account only when the verified provider tuple is
new. Repeated login resolves the same tuple to the same UUID. Explicit linking
requires an authenticated, recent session, trusted Origin, one-time OAuth state,
and the same verified callback flow. If the provider tuple already belongs to a
different account, linking fails closed. Unlinking may not remove an account's
last login identity.

No account merge is inferred from email, name, Commander, or sync-key data.

## Permission boundary

Identity login requests `scope=auth`. The access token is used only server-side
for `/decode` and `/me`, then discarded along with any refresh token. The proven
PR #490 CAPI Commander-profile parser is retained as compatibility evidence but
is not invoked by login. CAPI requires a future separately consented capability.

## Sessions and owner bootstrap

`v3_identity.session` stores only a SHA-256 digest of an opaque random browser
token. Sessions have idle and absolute deadlines, rotation lineage, revocation,
and a recent-auth timestamp. Cookies are HttpOnly, Secure, SameSite=Lax, and use
the host-only `__Host-` session-cookie prefix.

The first owner uses the existing `ADMIN_TOKEN` once after Frontier login.
Provisioning inserts the unique `owner` assignment under an advisory lock and
cannot be claimed twice. Subsequent privileged browser access uses the owner
session; existing token-based host automation remains supported.

## V2 OAuth disposition

Frontier OAuth was never deployed or used in V2, so it is not production state.
PR #490 and its proposed `sql/048_frontier_accounts.sql` are retained only as
prototype/reference evidence until the verified V3 port is safely merged. They
are `RETIRE / SUPERSEDED BY V3` and are not merged into V2/main.

No V2 OAuth data migration, V2 schema compatibility, or V2-to-V3 OAuth table
conversion exists. V3 starts from the fresh `v3_identity` schema in frozen
`001_v3_baseline.sql`; `002_v3_accounts_identity.sql` is its first
post-baseline migration. Legacy V2 migration history is not part of that chain.
