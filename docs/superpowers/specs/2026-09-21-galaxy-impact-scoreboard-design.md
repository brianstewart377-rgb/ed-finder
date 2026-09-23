# Your Galaxy Impact

Date: 2026-09-21. Approved product direction, reconstructed before implementation.

## Purpose and approved design

Replace the developer-oriented galaxy contributions panel with a player-friendly,
cumulative scoreboard of the commander's own exploration. Show systems discovered,
bodies scanned, Earth-Like Worlds, Water Worlds, Ammonia Worlds, terraformable
candidates and gas giants. Use readable, grouped numbers and neutral existing
panel styles. Never display internal terminology (including "facts", "Planet ID",
raw id64 values or schema names) in this experience.

Body totals must come exclusively from the player's imported journal Scan events,
not the global galaxy catalogue or the sharing-review queue. Uploading, sharing,
reviewing and publishing are separate actions; the scoreboard does not claim that
personal discoveries have been published to the shared galaxy.

## Investigation and data contract

`v3_private.journal_event` retains allowlisted Scan payloads including PlanetClass,
StarType, TerraformState and WasDiscovered. Migration 008 assigns new verified
imports an explicit owner_commander_id; historical unassigned events cannot be
assumed to belong to a verified commander. Repeated Scan observations can have
different timestamps and payloads, so event count is not body count.

Existing journal summary projections count account-wide observations, including
non-Scan events and unassigned history. Existing galaxy contributions endpoints
read sharing receipts and normalized physical measurements, not body taxonomy.
Neither existing summary is an appropriate source for this scoreboard.

The new own-account summary reads only Scan events from READY imports belonging
to the authenticated account and its currently active, verified Frontier OWNER
commanders. Revoked/viewer access, inactive accounts/commanders, unverified
identities, unassigned history and other accounts are excluded. No caller-supplied
account or commander selector can broaden that scope.

Count each exact system/body pair once across the account's eligible commanders
and imports. Re-importing or rescanning never inflates a total. Classify each body
using its latest recognized planet class (or star type); observations missing a
classification do not erase a prior known class. Terraformability uses the latest
present string or explicit null TerraformState independently; only Terraformable
counts as a candidate. An explicit empty string or null clears a previous
candidate status; an absent field preserves the previous known status. A body
whose latest recognized classification is a star cannot count as terraformable.
Stable event identity breaks equal-time ties deterministically. Unknown body
classes count toward bodies scanned but not named planet categories. Gas giants
include the five Sudarsky classes, water/ammonia life variants, helium-rich and
helium gas giants; water giants are not included. Categories can overlap because
a Water World may also be terraformable.

Systems discovered counts distinct systems represented by those valid Scan body
identities, not travel destinations, planned routes, or catalogue entries. Bodies
scanned includes stars and planets. Only complete canonical numeric system/body
identities count; malformed/missing identities do not produce invented matches.
WasDiscovered describes a body and does not prove whole-system first-discovery
credit, so no first-discovery claim is made. The
[Frontier Journal Manual v32](https://hosting.zaonce.net/community/journal/v32/Journal_Manual-v32.pdf),
sections 6.3 and 15.3, documents these body classifications and the distinction
between absent and explicitly empty terraforming values.

## API and safety

GET `/api/v1/journal/galaxy-impact`, operation `getJournalGalaxyImpact`, returns
`GalaxyImpactSummary` with seven nonnegative integer fields: systems_discovered,
bodies_scanned, earth_like_worlds, water_worlds, ammonia_worlds,
terraformable_candidates and gas_giants. Authentication is mandatory (401 when
absent). An eligible new account receives all zeroes. Responses are private and
not cached by browsers/proxies.

Use asyncpg, parameterized SQL and existing authentication dependencies. Return
only aggregate counts, never private event payloads or entity identifiers. Bound
the input to 1,000,000 eligible Scan events plus an overflow sentinel and use a
five-second database execution timeout. Exceeding either bound returns a friendly
unavailable error, never a truncated or fabricated total. Rate-limit this summary.
Do not access production, write catalogue data or change sharing permissions.

## UI behavior

Use a dedicated Svelte 5 panel titled **Your Galaxy Impact**, loaded through the
generated API facade and @tanstack/svelte-query. Account-scoped query keys and
abort signals prevent account switches from reusing private results. Refresh
after committed imports, including partial/cancelled imports with saved batches.

Show the two primary totals followed by a semantic definition list of notable
finds. Keep zero categories visible. Provide distinct loading, retryable failure
and new-commander states. Empty copy invites journal import without implying that
sharing must be enabled. Use an accessible labelled section, ordinary text labels,
status/alert announcements, keyboard-operable retry and existing theme tokens;
do not assign colors by body class. Do not show raw server error text.

Preserve the existing optional sharing and per-contribution withdrawal workflow
under a separate, collapsible **Manage galaxy sharing** control, using readable
observation labels/dates and sharing status, never raw system/body identifiers.
The new cumulative scoreboard replaces the old contribution list as the primary
panel. Translate nearby sharing copy into player language as part of this change.

## Wording/UX decisions for owner review

- Keep the requested **Systems discovered** label, with visible clarification:
  totals reflect imported scans and do not establish first-discovery credit.
- Frame the panel as what you have **recorded**, rather than claiming everything
  has been **added** to the published galaxy. Optional sharing does not change
  personal totals.
- Existing account UI groups linked commanders; totals therefore cover all of
  the account's currently verified owned commanders, deduplicating shared bodies.
- Include stars in bodies scanned, all supported gas giant classes in gas giants,
  and allow terraformable candidates to overlap the named planet classes.
- Retain withdrawal controls in a secondary disclosure rather than remove an
  existing privacy control. Revocation or import removal can reduce totals;
  cumulative means across retained eligible history, not an immutable achievement.

## Acceptance

Real disposable PostgreSQL tests with synthetic imported journals demonstrate
body classification, distinct totals, re-import/rescan behavior, sparse/unknown
payloads, multi-account/commander isolation, readiness/ownership gates, empty
accounts and bounded failure. API tests cover authentication and the typed shape.
Vitest covers populated/empty states, loading/error/retry, player-only wording,
accessibility and refresh/invalidation. Regenerate both API clients from FastAPI
OpenAPI. Run API pytest, `pnpm check` and `pnpm test`; report any blockers honestly.
Commit only on feat/galaxy-contributions-scoreboard; never push or modify main.
