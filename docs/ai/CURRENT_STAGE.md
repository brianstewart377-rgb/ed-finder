# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, after every merged change, and after any accepted decision or evidence run.

## Status

**D2b — D2a Merge Working-Point Reconciliation is drafted for independent review on branch `docs/d2b-d2a-merge-working-point`. D2a — Working-Point Hierarchy Enforcement and Historical Records Index is accepted and merged in PR `#306 — docs: enforce working-point hierarchy and index historical records`, with reviewed head `986bf44fe61ba984b029722873c5ac9268e79809`, merge commit `70895524847527a603aea0f31aeda847ca4a51ba`, merge method `merge commit`, and merged time `2026-07-03T20:15:53Z`. The D2a two-pass preflight protocol and historical-records index are now canonical. D2a authorised no archive moves, deletions, renames, code, runtime, API, database, CRE, CPE, or R1 implementation. D2b is docs-only, not accepted or merged, and grants no new implementation or cleanup authority.**

## Branch and base

- Repository: `brianstewart377-rgb/ed-finder`
- Canonical base branch: `work/r1-canonical-body-evidence`
- Required canonical base SHA: `70895524847527a603aea0f31aeda847ca4a51ba`
- Working branch: `docs/d2b-d2a-merge-working-point`

The live head for this draft is not recorded statically here. Before any review, owner-acceptance wording, or merge decision, fetch live branch or PR metadata and verify the exact current head, changed-file scope, review state, and thread state.

## Recent merged predecessor facts

- PR: `#302 — docs: establish documentation control plane`
- PR base branch: `work/r1-canonical-body-evidence`
- PR base SHA before merge: `2302634a226ab79545bf27dfaf77cd6aff26a309`
- Reviewed head SHA: `2317012372742864b79b85f08f52361e1b5aee18`
- Merge commit SHA: `4d01e0213046825f640e245cc551512c7e9d90f1`
- Merge method: `merge commit`
- Merged at: `2026-07-03T16:23:05Z`

At closeout preflight, `origin/work/r1-canonical-body-evidence` resolved to the merge commit above.

- PR: `#304 — docs: record D0 estate and boundary register`
- PR base SHA before merge: `95b1eba4c026ac75b003e148fc8d3d8a4430ac46`
- Reviewed head SHA: `a0670bc00562077f8e49a2516dfc3a8233c059d9`
- Merge commit SHA: `2d1472cc63f9c228e26796d68d7e75384fc0db61`
- Merged at: `2026-07-03T17:26:10Z`

- PR: `#305 — docs: clarify root navigation and history`
- PR base SHA before merge: `2d1472cc63f9c228e26796d68d7e75384fc0db61`
- Reviewed head SHA: `a8be0792bed7982d36e679ea1ba3961569510a23`
- Merge commit SHA: `0e8190e56ed44f6ba176f8a8b7e31e5fa51fe4cc`
- Merged at: `2026-07-03T18:39:28Z`

- PR: `#306 — docs: enforce working-point hierarchy and index historical records`
- PR base SHA before merge: `0e8190e56ed44f6ba176f8a8b7e31e5fa51fe4cc`
- Reviewed head SHA: `986bf44fe61ba984b029722873c5ac9268e79809`
- Merge commit SHA: `70895524847527a603aea0f31aeda847ca4a51ba`
- Merge method: `merge commit`
- Merged at: `2026-07-03T20:15:53Z`

## D2a scope

- create `docs/ai/AGENT_WORKING_POINT_PREFLIGHT_PROTOCOL_V1.md`;
- create `docs/HISTORICAL_RECORDS_INDEX.md`;
- update current control documents so the working-point hierarchy is explicit and hard to ignore;
- correct stale D0/D1b next-action wording using live merged facts;
- link historical records to their controlling replacement or next document to read.

## D2a exclusions

- no code, test, fixture, schema, API, runtime, deployment, database, CRE, CPE, or R1 semantic change;
- no archive, move, rename, deletion, physical document reorganisation, root `README.md`, `CHANGES.md`, or beta-version work;
- no automation, CI, hooks, scripts, templates, package changes, or implementation authority;
- no Stage 25 semantic change, no universal-score change, and no change to CRE/CPE ownership boundaries.

## What D1a changed

- introduced `docs/DOCUMENTATION_INDEX.md` as a navigation layer subordinate to `CURRENT_STAGE.md`;
- separated current Stage 25 control, legacy stored ED-Finder ratings, DEV-only R1 Assessment Laboratory, future CPE System Assessment Engine, and CRE research truth;
- aligned AI recovery and handoff material with current control records and live GitHub/Git recovery;
- reconciled pre-merge acceptance with post-merge closeout;
- corrected stale Stage 25C wording without claiming Stage 25 is complete;
- updated the Reference Pack to lead with current control material before historical roadmaps.

## What D1a did not change

- no code, test, SQL, schema, API, runtime, deployment, CRE, CPE, or R1 semantic change;
- no document move, rename, archive, delete, or physical reorganisation;
- no changelog or versioning baseline;
- no database change, root `README.md` work, beta-version work, or implementation authority;
- no merge, rebase, force-push, review request, PR comment, deployment, or automation authority;
- no claim that Stage 25 is complete.

## Control boundaries preserved

- Legacy ED-Finder ratings remain the stored `0–100` product ratings documented in `docs/colonisation-redesign/rating-system-current-contract.md`.
- The R1 Assessment Laboratory remains DEV-only, fixture-backed, deterministic, local, and separate from the public product.
- CRE remains the authority for evidence, provenance, mechanics, contradictions, confidence, and planner-safe releases.
- CPE remains the future authority for programme-specific assessment and player-specific plan construction.
- The future CPE System Assessment Engine must not be described as a universal score or universal rank.

## Live merged GitHub state checked for Stage 25 wording

- PR `#262` — `Add Stage 25C product shell and navigation hierarchy` — merged.
- PR `#263` — `Fix Review Lab mobile planner contract` — merged.
- PR `#269` — `[codex] stage 25d-a finder save, inspect, and plan start` — merged.
- PR `#271` — `[codex] Stage 25D-A.2 planner clarity and draft lifecycle` — merged.

These merged facts correct stale wording that still described Stage 25C Slice 1 as pending review. They do not justify calling Stage 25 complete.

## Validation history

- PR `#302` was verified merged at `4d01e0213046825f640e245cc551512c7e9d90f1`.
- The reviewed head for that completed predecessor merge was `2317012372742864b79b85f08f52361e1b5aee18`.
- The changed-file scope for that predecessor merge remained the approved ten-file D1a documentation allowlist.
- PR `#304` was verified merged at `2d1472cc63f9c228e26796d68d7e75384fc0db61`.
- PR `#305` was verified merged at `0e8190e56ed44f6ba176f8a8b7e31e5fa51fe4cc`.
- PR `#306` was verified merged at `70895524847527a603aea0f31aeda847ca4a51ba`.
- This D2b branch was created from the fetched canonical base only after the worktree was verified clean.

## Remaining documentation debt

- D0 is now recorded in `docs/ai/D0_DOCUMENTATION_ESTATE_AND_CODE_BOUNDARY_REGISTER_V1.md` as a read-only documentation-estate and code-boundary register.
- D1b is complete and merged in PR `#305`; its merge facts remain historical evidence, not current working authority.
- D1c remains a separate CRE documentation-repair batch and does not alter current ed-finder control authority here.
- D2 remains the later logical archive/index treatment candidate; it is not started or authorised by this draft.
- Stale historical-stage wording outside D1a requires later, separately authorised conservative cleanup batches.
- Archive, move, rename, deletion, root `README.md`, changelog, beta-version, and physical documentation reorganisation require separate explicit authorisation.

## Next safe action

No new archive, deletion, CRE, CPE, R1, API, runtime, or implementation work is authorised by this reconciliation.
A separately owner-authorised next batch is required.

## Closeout rule

This closeout records PR `#302`’s completed merge.

This closeout PR cannot record its own eventual merge SHA before it merges.

Its own eventual merge remains recoverable from live GitHub PR metadata.

Do not open another PR solely to record this closeout PR’s own merge SHA.

A later ordinary working-point update may record this closeout merge as historical evidence.

## Recovery instruction

If context is lost, start read-only. Read:

1. this file;
2. `docs/DOCUMENTATION_INDEX.md`;
3. `docs/ai/AGENT_WORKING_POINT_PREFLIGHT_PROTOCOL_V1.md`;
4. `docs/ai/PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`;
5. `docs/ai/CPE_SYSTEM_ASSESSMENT_ROADMAP_V1.md`;
6. `docs/ai/SYSTEM_ASSESSMENT_CONTINUITY_LEDGER_V1.md`;
7. `docs/HISTORICAL_RECORDS_INDEX.md`;
8. `docs/ai/DECISIONS.md`;
9. the live GitHub and Git state.

Report the recovered branch, exact base, controlling document, exact current-status wording, active scope, exclusions, merged-predecessor facts, and next safe action before making any write.
