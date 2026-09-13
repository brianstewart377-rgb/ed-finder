# Accounts, personal Journal/Codex and log import

This is the implementation assessment requested on 2026-09-13, based on main
`5937cf6cca8cdaaaa39fe3378df87556c8cdf7da`. It extends the user's UI/account
review; it does not install migrations, upload personal journals, enable a
watcher, publish research or change the running Ratings/Search generations.

## What exists

| Surface | Existing implementation | Remaining UI/integration work |
| --- | --- | --- |
| Account identity | Frontier OAuth, opaque cookie sessions, stable internal accounts, linked external identities, owner roles, identity-link/unlink APIs | Finish the new shared account controls and account page, test a real callback, retain account identity for private query isolation |
| Private journal imports | `/api/v1/journal/imports`, import receipts, per-account file/event duplicate detection, payload allowlists, quotas, transactional writes | Svelte upload controls, useful progress/retry states, import history and a durable large-import protocol |
| Personal Journal/Codex | Summary, systems, bodies, Codex, organic progress and sales endpoints | Svelte views, date/filter/search affordances, bounded database pagination and links into Inspect |
| Journal parser | Shared `@ed-finder/planner-core/journal` contracts and parser logic, plus the retained React lane's streaming worker adapter | Reuse the shared parser; move framework-independent worker orchestration into the current application and test cancellation/memory limits |
| Research sharing | Separate explicit consent, withdrawal and sanitized export implementation | A separate opt-in setting, clearly independent of using private journals |

The current migration manifest records `005_v3_journal_intelligence.sql` as
confirmed applied on 2026-09-12. This assessment did not re-query production or
verify that every current API route is deployed. Fresh read-only release/schema
evidence still belongs to the normal release process.

Useful sources: `apps/api/src/routers/v3_journal.py`,
`apps/api/src/edfinder_api/journal/{store,identity,projections}.py`,
`apps/api/src/routers/v3_journal_research.py`,
`frontend/src/features/account/AccountWorkspace.tsx`,
`frontend/src/features/account/useJournalUpload.ts`,
`frontend/src/features/account/JournalUploadPanel.tsx`, and
`frontend/src/features/journal-import/`.
The generated Svelte API client already includes V3 journal operations; expose
them through `apps/web/src/lib/api/client.ts`, not direct component imports.

## Account and commander boundaries

Use one ED-Finder account for authentication, settings and private data ownership.
Keep Frontier login identities and in-game commanders as distinct concepts.
The server must derive the owner from the authenticated session; an upload must
never choose another owner's account ID.

Before promising separate histories for multiple commanders, address the current
model: the router passes `commander_id=None`, the store can select the most
recently granted active owner edge, and event uniqueness is
`(owner_account_id, event_type, event_key)`. That model combines personal data at
account level. Adding a commander selector alone would not create independent
histories. Define explicit association and dedupe semantics, migrate/test them,
and hold ambiguous ownership for review instead of silently choosing a commander.
Journal display names alone are not proof of account ownership.

The current Svelte auth store retains only commander name and owner status.
Carry the stable session account ID into account-aware query keys before adding
private data screens. Cancel private requests and clear private caches on
logout/account change; stale responses must not populate a different account.
Owner/operator permissions remain separate from normal account access.

## Proposed user journey

1. **Account:** sign in, see the active commander/account, manage linked sign-in
   identities and choose research-sharing preferences separately.
2. **Import journals:** select `.log`/supported JSON journal files or a folder
   where supported; preview the date range, detected commanders, supported events
   and warnings. Import recognised authorised segments while holding unmatched
   or ambiguous segments for review. One mismatch must not abort the selection.
3. **Import progress:** distinguish reading, uploading and saved work. Show a
   durable receipt with new events, duplicates, skipped files and errors.
4. **My Journal:** show visited systems and scans, then a cursor-paginated travel
   timeline. Existing system summaries are not a full chronological event feed;
   add that bounded backend projection explicitly.
5. **My Codex / Exobiology:** show recorded entries, observed regions, species,
   scan stages and sales from the existing projections. Link systems/bodies to
   Inspect using exact identifiers. Do not invent completion percentages without
   a defined total or present personal observations as universal catalogue truth.

Manual selection is the first importer. Automatic folder watching after a tab
closes requires a separate local companion/device-ingestion design with explicit
access, revocable credentials and durable cursors; the browser upload flow does
not provide it. An import does not automatically update the public canonical
galaxy or grant research consent.

## How uploaded logs should enrich the shared galaxy

The user asks whether uploaded logs should contribute to the shared database or
whether Spansh should be its sole updating source. **Recommendation: retain
Spansh as the bulk catalogue source and allow eligible, explicitly shared journal
observations to supplement it through a validated ingestion path.** This is a
design recommendation, not an implemented or enabled V3 publication pipeline.

The current personal importer commits accepted events to
`v3_private.journal_event` in one transaction. The personal projection endpoints
query those rows directly, so committed observations can be read immediately;
the Svelte UI must refresh its account-scoped queries after a successful import.
This does not depend on a Spansh refresh. Conversely, importing privately does
not submit records to Spansh, and waiting for its next refresh does not guarantee
that those records will ever become shared catalogue data.

| Data or action | Proposed treatment |
| --- | --- |
| Travel history, commander identity, private progress and account records | Keep in the personal account/commander scope; do not publish as galaxy facts |
| Eligible scans and physical system/body observations | With explicit sharing permission, validate identifiers, payload, game version and observation time; retain source and lineage; stage for reconciliation |
| Missing or conflicting shared facts | Fill gaps or update only according to field-specific precedence and freshness rules; retain conflicts for reconciliation and never treat upload time as observation time |
| Published changes relevant to Search or ratings | Refresh affected derived records through a bounded incremental process, with publication status and retry receipts; avoid triggering a whole-galaxy rebuild for each upload |
| Later Spansh refresh | Reconcile against retained journal provenance; do not blindly erase accepted journal-only facts or let an older observation replace a newer fact |
| Unmatched commander segments | Hold for ownership/permission resolution while other valid files continue; do not silently publish them under the signed-in commander |

Authentication establishes who submitted a file; it does not prove that the
contents are accurate. Missing coordinates, identifiers, timestamps or other
required evidence must leave an observation unresolved rather than fabricate a
canonical system/body. Older observations can fill suitable gaps, but must not
masquerade as current station, market or other time-sensitive state. Catalogue
acceptance and derived Search/ratings publication are separate checkpoints;
personal import success must not imply that either has happened.

Start with a small, defined set of galaxy facts and a reviewed reconciliation
path, then automate only after duplicate, conflict, retry and Spansh-refresh
behavior is demonstrated. Shared publication requires its own explicit purpose
and withdrawal semantics; the existing research-sharing grant must not be
silently interpreted as permission for a different public contribution use.

The retained `/api/journal/imports/{run_key}/promote` implementation already
illustrates staging plus administrator promotion in the older data model. It is
not a V3 bridge. The V3 research export is consent-gated and sanitized, but its
store only touches private observations/export receipts, not canonical galaxy
tables. Reuse those design lessons without wiring the new account UI to legacy
promotion or treating an export receipt as shared publication.

Evidence: `apps/api/src/edfinder_api/journal/{store,projections,export}.py`,
`apps/api/src/routers/{v3_journal,v3_journal_research,journal_import}.py`, and
`apps/api/src/source_precedence.py` (older-model precedence reference).
This assessment did not check the live Spansh scheduler; the recommendation does
not depend on whether its current cadence is nightly.

## Large imports and resumption

The retained upload hook accepts at most 200 files, caps each selected file at
128 MiB, and rejects selections above 50,000 uploadable events. It sends one
complete request. Its own source explains why naive request splitting is unsafe:
the first request admits a file by `(account, content_sha256)`; later requests
repeating that file are skipped, including their events.

Keep that existing bounded endpoint intact initially. For large archives, add a
versioned import-session protocol with a file manifest, unambiguous file identity,
chunk sequence/hash, persisted acknowledgement cursor and explicit completion.
Chunk writes and acknowledgements must commit together. A committed chunk must
be safe to retry after a lost response; an incomplete file must remain resumable
and must not be marked complete by file-level dedupe. Report parsing progress
separately from committed progress. Preserve lossless system IDs and server-side
event validation. Do not treat a client progress counter as a durable checkpoint.

Bound reads as well as writes. The current Codex and organics endpoints return
all matching grouped account rows without pagination. Systems and bodies already
apply offset/limit in SQL. Add bounded database pagination for Codex/organics and
supported filters with a stable ordering before presenting these views as
suitable for large histories.

## Required: mixed-commander logs must not crash the importer

The user explicitly requires support for a selection containing more than the
commander associated with the signed-in account. Treat this as normal input,
not a fatal parser error or a reason to discard every file.

- Track the journal's own commander/session identity from the applicable
  `Commander`/`LoadGame` identity records. Other players' names in multiplayer,
  crew, combat or similar event payloads are not a change of journal owner.
  Display-name equality is not an ownership proof; use a verified identity
  association where available and report uncertainty otherwise.
- Keep identity context scoped to each file/session. Do not carry the last
  commander's identity into the next file merely because files were processed
  in one worker or arrived in an unusual order. If identity changes within a
  stream, delimit segments rather than attributing the entire file to one player.
- Classify segments as recognised/authorised, another commander, or unknown/
  ambiguous. Continue importing recognised segments. Hold the others locally
  for review by default and show their commander/file counts and reasons. Do not
  upload another commander's records under the current commander or silently
  attach them to the store's default owner edge.
- An optional later association must verify access server-side. A forged file
  identity or client-selected account ID must never grant cross-account access.
- Preserve valid segments when another file/segment has a bad line, conflicting
  identity or unsupported event. Report per-file/segment results, skip only what
  cannot be safely attributed, and keep receipts for work actually committed.
  Global failures such as expired login should pause the upload for recovery,
  without losing already acknowledged work.
- **Do not mark a partly accepted mixed file fully imported.** Existing whole-
  file dedupe would otherwise suppress the held segments on a later retry.
  Mixed-file admission needs segment/chunk completion in the new import protocol;
  until that exists, report/hold that file and continue with other valid files.
- Acceptance fixtures must cover two commanders across separate files, a mid-
  file identity switch, missing identity headers, renamed commanders, other
  players merely mentioned inside events, out-of-order files, a corrupt segment,
  cancellation/retry after partial success, and resolving a previously held
  segment. Assert no crash, no cross-commander contamination, continued progress,
  truthful counts and no loss/duplication on retry.

This is a required importer implementation contract, not a claim that the current
upload hook or schema already supplies commander partitioning or segment resume.

## Delivery order and evidence

1. Finish this account/header UI draft and a real sign-in/callback/logout proof.
2. Add Svelte import and summary views using the existing bounded API/shared
   parser. Make current limits visible; prove reimport and account isolation.
3. Resolve multi-commander ownership and add the versioned resumable import
   protocol, including migrations and schema compatibility through normal review.
4. Add personal Codex/exobiology and travel views with bounded server pagination.
5. Consider a local watcher only after the manual/retry workflow is reliable.
6. Treat shared galaxy enrichment as a separate reviewed workstream: define
   eligible facts, contribution permission, conflict/freshness rules and derived
   publication behavior before implementing a V3 bridge. Personal Journal/Codex
   delivery does not need to wait for it.

Essential acceptance cases: guest denial, account switching, overlapping logs,
identical names with different file content, a lost response after commit,
mid-import restart, changed source files, malformed/unsupported events, large
files, cancelled parsing, wrong commander association and consent withdrawal.
Existing journal tests provide useful fixtures and baseline assertions; the new
Svelte/browser and chunk-protocol cases must exercise actual integrated behavior.
