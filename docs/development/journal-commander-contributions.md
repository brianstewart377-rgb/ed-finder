# Verified commanders and optional journal galaxy contributions

Implementation draft, 2026-09-13. This change does not deploy, apply migrations,
publish a generation, operate production, or restart Search/Ratings.
It follows the account/header UI in PR #711 and the user-authorized enrichment
decision in `accounts-journal-ui-plan.md`.

## Frontier and CAPI

The existing OAuth flow requests `scope=auth`, `audience=all`, then uses the
authenticated `/decode` and `/me` responses. Configuration for a CAPI base URL
exists, but the active flow does not request CAPI permissions or call `/profile`.
The permissions registered with Frontier have not been inspected. This is not
evidence that the application lacks CAPI access.

Commander verification uses the actual authenticated `usr.customer_id` as journal
`F<customer_id>`. This mapping is also used by
[EDMarketConnector's Auth.refresh](https://github.com/EDCD/EDMarketConnector/blob/main/companion.py).
The login account may still group child customers by a parent subject. The child
FID remains distinct: parent IDs, commander names and uploaded FIDs never prove
ownership. A new FID creates its own verified commander; an existing conflicting
owner produces a review-required error. Unknown customer formats keep normal
account login usable but do not grant journal verification.

CAPI may subsequently supply a commander display name/current game state. It is
not needed for this FID association and cannot make uploaded logs tamper-proof.
A real Frontier login/callback proof remains a release acceptance requirement.

## Personal import

The new authenticated, same-origin `/api/v1/journal/verified-imports` endpoint
classifies each file from its `Commander`/`LoadGame` FID headers. Other players
mentioned in events do not change ownership. Missing, unlinked, conflicting and
mid-file multiple identities hold that file intact; other valid files continue.
Duplicate filenames and ambiguous offsets are also held.

Verified commander groups commit independently. Account, commander and semantic
event identity prevent overlapping commander histories from collapsing. Later
Scan observations have their own UTC observation identity. The legacy endpoint
can still store unassigned personal data; it no longer guesses a default owner.
Old unassigned files require ownership review, with no inferred backfill.

The Svelte worker resets context for every file and limits an operation to 200
files, 16 MiB/file, 64 MiB total and 50,000 supported events. Committed work survives
a lost response; retries recover original owned receipts using file hashes.
The new offer API also requires those selected hashes, so retrying one file does
not opt in other private files from an older multi-file receipt. Parsing/request
cancellation and account-panel removal abort pending browser work; already
committed database transactions remain saved.

This is bounded whole-file import, not a durable segment/chunk archive protocol.
Oversized and mixed files remain held. Full Journal/Codex/travel views and archive
resume remain later UI/protocol work; existing personal projections read committed
events immediately, independently of Spansh.

## Shared facts and build integration

Sharing is off by default and separate from research permission. The exact import
and selected file hashes must be explicitly offered for ED-Finder site/API use.
Only Live 4.x `Scan` scalar physical fields are eligible in policy
`journal-galaxy-physical-v1`. Normalization uses exact system/body identifiers,
UTC observation time, finite/ranged numeric values and explicit unit conversion.
Names, FIDs, account IDs, credits, filenames and private event payloads are not
copied into the public snapshot. Travel history, markets, stations, taxonomy and
new system/body creation are outside this policy.

Offers enter the private contribution ledger as OFFERED. A recently authenticated
site OWNER must review them before they become ELIGIBLE. The API never updates a
canonical body. A source replay artifact stores the exact sanitized bytes with
their digest, normalizer/code hashes and contribution/evidence lineage.

The new disposable build command `scripts/dev/build_journal_galaxy.py` runs the
frozen Spansh builder and then the journal reconciliation phase. The recovered
`v3_spansh` package remains byte-for-byte unchanged because its checksums belong
to the published canonical/V4 replay contract. No existing production build
command or scheduler is modified; adopting this orchestration requires the
normal reviewed release process.

Spansh builds first finish baseline validation, identity indexes and constraints.
An additional atomic validation phase then applies only allowed scalar fields to
a never-published READY candidate with no derived build. Current, previously
published and retired catalogues are refused. Failures roll back values and the
enrichment validation receipt. Existing constraints stay enforced; there is no
replica trigger suppression. The original validation receipt is retained with a
versioned enrichment decision digest chain.

The new build command carries forward eligible observations reviewed by the
candidate's creation time, using keyset batches of at most 500. Later reviews wait
for the next build; the separate reconciliation utility can record explicitly
selected contribution IDs as extra inputs. If enrichment stops, its
`--all-eligible --apply` mode resumes against the saved READY candidate. The publication
guard refuses a candidate that omitted an applicable eligible observation, so a
Spansh refresh cannot silently discard retained journal evidence. Unknown or
inactive canonical identities stay unresolved. Existing body identity indexes
are required before any per-body query, avoiding repeated scans of build heaps.

Missing physical fields can be filled. Conflicting non-null values change only
when observation/provenance time proves the incoming value is newer; equal-time
or unknown-freshness conflicts preserve the catalogue value. Source upload time
never substitutes for observation time. Baseline row provenance stays intact;
journal field decisions have separate evidence.

Withdrawal is idempotent, closes future eligibility and writes a durable outbox
request. A publication guard rechecks used contributions and active ownership.
Already published catalogue effects remain immutable until an operator performs
a replacement build/publication. This PR adds no outbox consumer, scheduler,
production operator authority or immediate derived refresh. Search/Ratings retain
their separate build and publication gates.

## Validation and deployment boundary

Additive migrations 008/009 and their checked hashes must pass the normal PG18
migration/release process before this API code is deployed. No migrations were
applied to production. Migration 007 remains reserved by the separate workstream.

Focused tests cover OAuth/FID association, ownership classification, private
storage, physical normalization and precedence. Svelte tests cover default-private
import, mixed-file reporting, selected-file sharing retries and account removal.
The dedicated CI PG18 job applies the new schema to an empty disposable database
and exercises actual transactions, HTTP ownership/auth/origin handling, consent
scope, source replay bytes, indexed reconciliation, carry-forward, publication
refusal, withdrawal and retry. Local runs skip that DB module when no confirmed
disposable PG18 instance is available; a skip is not a database pass.

Browser visual acceptance, a real Frontier callback/logout, large-archive segment
resume, personal Journal/Codex views and operator replacement publication remain
explicit subsequent acceptance/work items. Draft status is not production readiness.
