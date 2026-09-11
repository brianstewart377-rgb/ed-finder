# Replacement manual review evidence — PR #678

**Status:** manual (non-Codex) review evidence. This is **not** a Codex Review and
does not by itself satisfy the acceptance gate. See "Gate status" below.

| Field | Value |
|---|---|
| Repository | `brianstewart377-rgb/ed-finder` |
| PR | [#678 — Land the account-scoped V3 journal intelligence lane](https://github.com/brianstewart377-rgb/ed-finder/pull/678) |
| Exact reviewed head SHA | `249b9624b7aa8ddd68f8c8c469cbc16cea5888a5` |
| Base | `main` @ `8ce2abf9ec2cfea05999c950b70efd17e28c0e2a` |
| Diff size | 78 files, +14,940 / −1,678 |
| Reviewer | Manual review by an agent (Codex-replacement pass), 2026-09-11 |
| Method | Full read of every changed non-generated file; targeted verification of
each candidate finding against the current code and the checked-in tests. |

## Why this document exists

`chatgpt-codex-connector` posted a usage-limit failure on this head
(PR comment `IC_kwDORx2EiM8AAAABT6n6fg`, 2026-09-11T08:16:31Z) and therefore
**did not review** the final candidate. Octopus Review did run against this exact
head (`PRR_kwDORx2EiM8AAAABNJsqeQ`, submitted 2026-09-11T10:18:04Z, 25 files,
1 finding, overall 3/5).

`docs/development/pull-request-acceptance-policy.md` is fail-closed when a
reviewer service is unavailable and permits an owner waiver only when the waiver
records **replacement manual-review evidence covering the exact latest head**.
This file is that evidence. It does not waive anything by itself.

## Scope and limitations

Reviewed in full: the `edfinder_api/journal/*` package (consent, event contract,
export, identity, projections, sanitize, store), `routers/v3.py`,
`routers/v3_journal.py`, `routers/v3_journal_research.py`, migration
`005_v3_journal_intelligence.sql`, the frontend `account` feature and
`lib/api/journal.ts`, the `planner-core` journal parser changes, and the landing
repairs (`cleanup.sh`, `protected_resources.*`, `.gitattributes`, `.gitignore`,
`config.py`).

Skimmed only: the two regenerated API clients (`types.gen.ts`, `api.gen.ts`),
which are generated artifacts, and the large new test/fixture corpus (I read the
test files where a finding needed confirming, not exhaustively).

Not verified here: runtime behaviour against a live database, secret/credential
scanning, and anything requiring production access. Migration 005 was read, not
executed.

## Gate status on this head

| Gate | State |
|---|---|
| Exact head re-verified | ✅ still `249b9624b7aa8ddd68f8c8c469cbc16cea5888a5` |
| Protected CI on `249b9624` | ✅ green (28 checks succeeded; 1 skipped) |
| Octopus Review on `249b9624` | ✅ completed (3/5, 1 finding) |
| Codex Review on `249b9624` | ❌ **did not run** — usage limit |
| Complete paginated review-surface inspection | ✅ done (see below) |
| Findings below dispositioned | ⚠ proposed below; owner must confirm and resolve the one Octopus thread |

Until each finding below is dispositioned on the PR (fixed and verified /
demonstrated false positive / superseded by a verified later change / explicitly
accepted risk by the repository owner) **and** a named reviewer-service waiver is
recorded, the policy is not satisfied. This document is the replacement evidence;
it does not by itself close the gate.

## Review-surface inspection (complete, paginated)

Re-pulled from GitHub on 2026-09-11 with `--paginate` / GraphQL so later pages
cannot be silently omitted.

| Surface | Result |
|---|---|
| Formal reviews | 1 — `octopus-fc8f7111f1[bot]`, `COMMENTED`, on commit `249b9624` |
| Inline review comments | 1 — Octopus N+1 finding at `apps/api/src/routers/v3.py:243` (RIGHT side, no reply) |
| Top-level PR comments | 3 — Codex usage-limit failure (08:16:31Z), owner's `@octopus review` trigger (10:17:36Z), Octopus summary (10:17:40Z) |
| Review threads | 1 — unresolved, not outdated, `apps/api/src/routers/v3.py:243` (the Octopus N+1) |
| Hidden/unseen findings | none |

The only substantive unresolved thread on the PR is the Octopus N+1 (recorded as
F7 below). It must be dispositioned (or resolved) before merge even if the owner
waives the failed Codex lane.

## Findings

### F1 — High (data integrity): export truncation is silent and systematically biased against the observation types the export exists for

`apps/api/src/edfinder_api/journal/export.py:62-68`

```sql
SELECT event_type, event_key, event_payload, event_timestamp, source_record_hash
FROM v3_private.journal_event
WHERE owner_account_id = $1
ORDER BY event_type, event_key, event_timestamp
LIMIT $2
```

`export.py:168-182` bounds the row set by `limit`, and `export.py:204` stores the
applied limit in the **receipt** manifest only. The router default is 1,000 rows
with a hard cap of 10,000 (`apps/api/src/routers/v3_journal_research.py:33-34,55-60`),
while the ingestion cap is 200,000 events/day/account
(`edfinder_api/journal/store.py:24`).

Because the truncation happens on `ORDER BY event_type, event_key, event_timestamp`
— not chronologically — the rows that survive are the alphabetically earliest
event types. Sorting the 30 allowlisted event types, the last entries are:

```
... SAAScanComplete, SAASignalsFound, Scan, ScanOrganic, Screenshot,
    SellExplorationData, SellOrganicData, Touchdown
```

So for any account over the limit, the dropped rows are exactly the exported
science observations (`Scan`, `ScanOrganic`, `SellOrganicData`, `SAAScanComplete`)
while the retained rows are dominated by travel/identity events that
`sanitize_observation` then discards as `EXCLUDED_EVENT_TYPES`
(`sanitize.py:52-57`). The failure mode is a payload whose `manifest.observation_count`
is small or zero, emitted with no indication that the account had far more data.

The EDRE-visible manifest has no truncation flag (`export.py:107-111`), and the
consumer schema is `additionalProperties: false`, so an EDRE consumer cannot
distinguish "this account observed little" from "we exported a biased prefix".

**Recommendation:** order the selection chronologically (or by a
completeness-preserving key) rather than by `event_type`, raise the cap to
something compatible with the ingestion quota, and/or record truncation in a way
the consumer is contractually required to read.

### F2 — Medium (contract mismatch): the hand-declared frontend DTO for the export detail contradicts the API

`frontend/src/lib/api/journal.ts:139-141`

```ts
export interface V3ResearchExportDetail extends V3ResearchExportReceipt {
  payload: Record<string, unknown>;
}
```

The server model is a wrapper, not an extension
(`apps/api/src/routers/v3_journal_research.py:74-76`, returned at line 434), and
both generated clients agree: `packages/api-client/src/generated/api.gen.ts:7198-7204`
and `apps/web/src/lib/api/generated/types.gen.ts:7924-7932` are
`{ receipt: V3ResearchExportReceipt; payload: {...} }`.

The file's own header comment (`journal.ts:3-7`) claims these interfaces match
the V3 wire DTOs exactly, so this is a divergence from the stated intent, not a
documented shorthand. Any consumer of `getV3ResearchExport()` will read the
receipt fields at the wrong level. `frontend/src/lib/api/journal.test.ts:119`
exercises only the URL, so the mismatch is not caught by tests.

Minor, same file: `journal.ts:47-48` types `started_at`/`finished_at` as
`string | null` while `V3JournalImportReceipt` server-side is non-nullable `str`
(`v3_journal.py:112-113`).

**Recommendation:** replace the hand-declared research interfaces with the
generated types, or wrap them to match `{ receipt, payload }`.

### F3 — Medium (traceability): the sanitization contract's cited authority is not in the repository

`sanitize.py` cites `cre-export-schema.md` as the arbitration source for the
normalized shapes and unit conversions (lines 74, 182-189, 223-229), asserting
things a reviewer cannot check from the tree: that `radius_km = Radius / 1000`
rounded to 4dp, that `surface_gravity_g = SurfaceGravity / 9.80665` rounded to
6dp, that `signals` projects to `{Type, Count}` only, and that `sale.count` is the
number of `BioData` items rather than their per-item `Count`.

A recursive search for `*cre-export-schema*` across the repository returns no
file. The A1–A14 sanitization table is likewise referenced but not present.

**Recommendation:** check the schema/arbitration document into the repository
(or point these citations at the committed `docs/architecture/` decision doc),
so the redaction contract is auditable at the exact head.

### F4 — Low: events can be attributed to the wrong `journal_file_id` when two files in one request share a name

`edfinder_api/journal/store.py:441-449`

```python
file_sha_by_name = {
    str(item.get('name') or ''): _hash_bytes(
        item.get('content_sha256'), field='content_sha256',
    )
    for item in files
}
```

Events carry only `source_file` (a name), so a name→hash map bridges the two key
spaces. Duplicate names in one request make this last-wins: events from the first
file are attributed to the second file's `journal_file_id`. The comment
acknowledges the assumption ("names unique in practice") and
`V3JournalFileRef.name` (`v3_journal.py:44-51`) imposes no uniqueness.

Impact is bounded to provenance within a single account's own import (the FK is
`(journal_file_id, owner_account_id)`), so this is a correctness nit, not a
tenancy issue — but it is the same class of bug the file's own comment says was
already fixed once for `admitted_file_ids`.

### F5 — Low: the daily quota counts received rather than admitted events, and is not concurrency-safe

`edfinder_api/journal/store.py:192-206` compares `stored_today + received_events`
against `MAX_DAILY_EVENTS_PER_ACCOUNT`. A file that is entirely skipped by
content-hash dedupe (`store.py:422-440`) still consumes quota, so re-uploading an
unchanged file set can return 429 while inserting nothing. The read-then-insert
also has no lock, so two concurrent requests can both pass the check.

### F6 — Low: `source_record_hash` is client-supplied and never recomputed server-side

`store.py:467-475` takes the hash from the request. For the content-addressed
event types (`identity.py:22-26`, used at `identity.py:187-188`) that value *is*
the dedupe identity, so a buggy or malicious client can collapse distinct events
into one row. Blast radius is the caller's own account-scoped data, and the value
is documented as the client parser's per-line hash, so this is a robustness note
rather than a vulnerability.

### F7 — Low (performance): N+1 query per station economy

`apps/api/src/routers/v3.py:249-256` issues one `station_economy_current` query
per station inside the loop over stations. This is the finding Octopus reported
as "N+1 station economies query pattern" (Performance 3/5). The endpoint is an
unauthenticated canonical read, so the cost is attacker-influenceable.

**Recommendation:** one grouped query joined on `station_pk`.

### F8 — Informational: rate-limiting asymmetry

The new canonical read endpoints in `v3.py` carry no `@limiter.limit`
(5 endpoints, 0 limits), and neither do `systems.py`, `ratings_v4.py`,
`simulate.py` or `simulation.py`. The new journal endpoints in `v3_journal.py`
(8/8) and `v3_journal_research.py` (5/5) are all limited. So the omission is
consistent with the existing canonical-read convention rather than a new
divergence — but the two files being landed together makes the inconsistency
worth an explicit decision.

### F9 — Informational: the private zone has no row-level security

No V3 migration defines RLS (`001`–`005` are all `rls=0`), and none of the new
query sites get database-level protection. Isolation rests entirely on the
`owner_account_id` predicate. The new code carries it consistently — 45
references across the journal package and the two routers — and I found no query
in the new path that omits it. Recording the inventory here because a single
future omission would be a cross-account read of personal journal data.

I could not find any `GRANT` on the `v3_*` schemas anywhere under `sql/` or
`scripts/`, including the baseline, so role provisioning appears to live outside
the migration set; migration 005 adding no grants matches its predecessors and
is not a divergence this PR introduces.

---

## Verified as sound

Checked and found correct, in case it saves the next reviewer the trip:

- **Fail-closed payload stripping.** `event_contract.py:129-142` rejects unknown
  event types and strips non-allowlisted keys; the client parser's
  `EVENT_PAYLOAD_FIELDS` and the server's `_PARSER_PAYLOAD_FIELDS` are in parity
  for the fields that changed (`StarSystem`/`SystemName` on `CodexEntry`,
  `ScanOrganic`, `SAAScanComplete`; `GameVersion`/`GameBuild` attach on the nine
  exported types).
- **Account scoping.** Every new query in `store.py`, `projections.py`,
  `consent.py`, `export.py` and the two routers is scoped by `owner_account_id`
  taken from the session, never from request data (`v3_journal.py:196-200`
  and the `_require_user` equivalent in the research router).
- **Write-path CSRF posture.** All mutating endpoints call `require_same_origin`
  (`v3_journal.py:229`, `v3_journal_research.py:346,386`).
- **Deterministic replay and supersede-not-delete.** The receipt stores the
  payload SHA-256; the rebuild reproduces `generated_at` at `timespec='seconds'`
  from `created_at` and returns 409 on divergence
  (`v3_journal_research.py:253-272,424-432`); withdrawal supersedes by lineage
  token and never deletes (`export.py:246-323`).
- **Consent is never inferred.** Consent is not referenced from the import path;
  the state machine refuses duplicate GRANT and unbacked WITHDRAW with a DB-level
  `UNIQUE (owner_account_id, consent_version, decision)` and a CHECK tying
  `withdrawn_at` to the WITHDRAW decision (`005_v3_journal_intelligence.sql:141-159`).
- **Identity canonicalisation.** `_uint64_decimal` rejects bools and
  non-integral floats rather than truncating (`identity.py:55-76`), which is the
  documented fix for the earlier collision finding.
- **SQL injection surface.** The two f-string SQL sites in `projections.py:29`
  are built only from a frozen module-level literal, and `v3.py:20,122-124`
  validates the generation schema name against `^v3_gen_[a-z][a-z0-9_]{0,30}$`
  before interpolating it. Both are safe as written.
- **Migration shape.** 005 is guarded by a baseline `to_regclass` check, manages
  its own transaction, is pinned `-text` in `.gitattributes`, and its recorded
  sha256 in `migration-manifest.txt` matches the on-disk bytes (verified
  independently). It is declared but not applied, and it sorts after every
  applied row, so the live ledger remains an exact prefix.
- **Sentry hardening.** `config.py` adds `include_local_variables=False`, which
  stops provider access/refresh tokens being serialized from frame locals.
- **Cleanup guard.** `scripts/operator/protected_resources.sh` is fail-closed on
  exact volume-name matches and requires an explicit
  `EDFINDER_ALLOW_PROTECTED_CLEANUP=$EDFINDER_PROTECTED_RETENTION_ID` override;
  `cleanup.sh` sources it before acting on dangling volumes, and the manifest
  file is force-tracked via the `.gitignore` negation.

## Octopus finding cross-check

Octopus reported one finding (performance / N+1 station economies) with an
overall 3/5 and "Test Coverage Impact: Needs Attention". The N+1 is real and is
recorded above as F7. I did not find a coverage gap that contradicts the PR
body's test evidence (142 passed / 1 skipped on the journal and lineage suites);
the new lane ships roughly 4,000 lines of tests across nine
`tests/test_v3_journal_*.py` files plus two integration flows, and I did not
find an untested branch on the security-relevant paths I traced.

## Proposed dispositions (owner to confirm)

These are the reviewer's proposed dispositions. Any code change creates a new
head and invalidates this evidence for `249b9624`; the waiver below is valid only
for the recorded head.

| Finding | Severity | Proposed disposition | Owner decision |
|---|---|---|---|
| F1 truncation bias | High | Fix before merge, or explicitly accept risk for first landing | choose |
| F2 frontend DTO mismatch | Medium | Fix before merge (swap to generated types) | choose |
| F3 missing `cre-export-schema.md` | Medium | Commit the authority document, or accept risk | choose |
| F4 name-collision attribution | Low | Accept risk for first landing | record |
| F5 quota counts received, not admitted | Low | Accept risk for first landing | record |
| F6 client-supplied `source_record_hash` | Low | Accept risk for first landing | record |
| F7 station-economies N+1 (Octopus) | Medium (perf) | Fix before merge, or accept risk — resolve the thread either way | choose |
| F8 rate-limit asymmetry | Info | Decision only, no code change | record |
| F9 no RLS on `v3_*` | Info | Decision only, no code change | record |

## Owner waiver — draft for the PR comment

> **Reviewer-service waiver.** `chatgpt-codex-connector` (Codex Review) failed on
> head `249b9624b7aa8ddd68f8c8c469cbc16cea5888a5` at 2026-09-11T08:16:31Z with a
> usage-limit error (comment `5631507070`), so it is unavailable for this head.
> Replacement manual-review evidence for this exact head is recorded in
> `docs/development/evidence/codex-review-replacement-2026-09-11-pr678.md`.
> Accepted risk: **\<owner completes\>**. Octopus Review completed on this head
> (3/5, one finding). The single unresolved thread (N+1 at
> `apps/api/src/routers/v3.py:243`) is dispositioned as **\<fixed and verified /
> demonstrated false positive / superseded / explicitly accepted risk\>**.

## Queue — what to hand back to Codex when the review lane returns

1. Re-run `chatgpt-codex-connector` against a fresh head after F1 and F2 are
   fixed; not against `249b9624`, because fixing them changes the head and
   invalidates this evidence anyway.
2. Hand F1, F2 and F3 to the Codex review as the specific points to adjudicate —
   they are the ones where a second opinion is worth the spend, and F1 in
   particular is a judgement call about whether truncation is acceptable for a
   first landing.
3. F4–F7 are safe to batch into the same remediation commit; F8 and F9 are
   decisions, not code changes.
4. If the PR is to merge before the review lane returns, the owner waiver under
   "Reviewer failure and owner waiver" must name `chatgpt-codex-connector`,
   document the usage-limit failure, cite this file as the replacement evidence,
   and state the accepted risk explicitly.
