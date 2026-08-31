# ED-Finder R1 — Bounded Real-System Snapshot
## Review 1 — Stage Definition

Date: 2026-08-31
Status: pre-code Review 1
Branch: `chatgpt-ed-new-ops-requests`

## Goal
Create a bounded, operator/research-only, read-only loader that fetches canonical `systems`, `bodies`, and `body_rings` rows for explicitly named/id64 systems and feeds them into the completed `r1_evidence_bridge`.

The purpose is to measure what real stored data can support vs what remains Unknown before any live Finder ranking integration.

## Non-goals
- no Finder/API/frontend wiring;
- no ratings/archetype rebuild;
- no DB writes/migrations/temp tables;
- no Evidence Store mutation;
- no automatic pair resilience;
- no Plan Fit calibration;
- no galaxy-wide scan.

## Safety
Reuse the repository's established read-only pattern: connection/session must be read-only and `SHOW transaction_read_only` must return `on` before any canonical query. Abort otherwise.

## Bound
- explicit system IDs/names only;
- maximum 20 systems per invocation;
- deterministic query/result ordering;
- SELECT-only SQL allowlist;
- no dynamic table/column names from user input.

## Output
For each system:
1. raw row-shaped canonical snapshot metadata;
2. projected `ProjectedSystemEvidence`;
3. projected `CandidateEvidence` capability shape;
4. counts of known/unknown/ambiguous/conflicting field states;
5. slot prediction coverage;
6. deterministic snapshot digest.

## Golden validation set
Start with existing audit controls where identities are known: HR 1188, HIP 294, Brambai DL-Y g32, Eorgh Prou AA-A h24, HIP 70564, Praea Euq PS-U c2-3, Blu Thua JS-J d9-1, and sparse controls where useful.

Running the real DB probe is a separate operator action; implementation tests use fake read-only rows and do not claim production observations.
