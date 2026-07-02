# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Stage 5A and Stage 5B are accepted and merged. The documentation-only acceptance-and-provenance closeout merged in PR `#292` at `1b7b36b4c411e50ad102adadd51339653476b68d`.**

## Baseline

- Canonical base branch: `work/r1-canonical-body-evidence`
- Canonical base SHA for this closeout: `f1b1e5b42859a42b0e651ad957c01d5261bec754`
- Documentation closeout branch: `docs/r1-acceptance-closeout`
- Stage 5A discovery PR: `#290`, merged at `dad3a99f4571428fcb517a13785be297f57e875a`
- Stage 5A reviewed head: `36371887bf09dad420c86b6c6ca6faffb7cfa0cd`
- Stage 5B evidence-discipline PR: `#291`, merged at `f1b1e5b42859a42b0e651ad957c01d5261bec754`
- Stage 5B reviewed head: `b42d8cfa6d1ad453d6637ea7f24919d85950ec95`
- No deployment occurred.

## Closeout scope

The closeout changes only:

- `docs/ai/CURRENT_STAGE.md`
- `docs/ai/DECISIONS.md`
- `docs/ai/R1_STAGE5A_5B_ACCEPTANCE_CLOSEOUT_V1.md`

It records acceptance and provenance only. It does not alter R1 semantics, fixtures, tests, UI, normal application behavior, external research authority, implementation authority, or deployment behavior.

## Stage 5A acceptance checkpoint

- **Status:** Accepted and merged.
- **Accepted code commit:** `36371887bf09dad420c86b6c6ca6faffb7cfa0cd`
- **Acceptance date/time:** `2026-07-02`; owner acceptance occurred before PR `#290` merged at `2026-07-02T10:05:41Z`. The exact chat timestamp was not durably captured and is not fabricated here.
- **Branch:** `docs/r1-stage5a-control-fixture-discovery`
- **Pull request:** `#290`, merged at `dad3a99f4571428fcb517a13785be297f57e875a`
- **Acceptance checkpoint commit:** `2d9b6fb65dfb246618a9133098b5eda53ea41182`
- **Evidence reviewed:** Independent read-only Stage 5A discovery review found no required corrections and returned “Ready for owner acceptance.”
- **Caveat:** The acceptance checkpoint was omitted at the time of merge and is recorded post-merge by this documentation-only closeout. It does not reopen the Stage 5A review.
- **Next safe action:** A separate docs-only Stage 5B evidence-discipline contract, subject to independent review and owner acceptance. That contract was subsequently completed and merged.

## Stage 5B acceptance checkpoint

- **Status:** Accepted and merged.
- **Accepted code commit:** `b42d8cfa6d1ad453d6637ea7f24919d85950ec95`
- **Acceptance date/time:** `2026-07-02`; owner acceptance occurred before PR `#291` merged at `2026-07-02T10:55:34Z`. The exact chat timestamp was not durably captured and is not fabricated here.
- **Branch:** `docs/r1-stage5b-evidence-discipline`
- **Pull request:** `#291`, merged at `f1b1e5b42859a42b0e651ad957c01d5261bec754`
- **Acceptance checkpoint commit:** `2d9b6fb65dfb246618a9133098b5eda53ea41182`
- **Evidence reviewed:** An independent Stage 5B review found one recovery-record correction. The subsequent correction verification at `b42d8cfa6d1ad453d6637ea7f24919d85950ec95` found it complete and returned “Correction accepted; Stage 5B is ready for owner acceptance.”
- **Caveat:** The acceptance checkpoint and owner-intent provenance were omitted from PR `#291` and are recorded post-merge by this documentation-only closeout. The accepted Stage 5B rules are unchanged.
- **Next safe action:** No external evidence inventory, fixture, implementation, or deployment is authorised. Any later programme-definition or evidence-inventory stage requires separate owner authorisation.

## Stage 5A accepted record

- Discovery record: `docs/ai/R1_STAGE5A_CONTROL_FIXTURE_DISCOVERY_V1.md`
- Accepted conclusion: the canonical repository does not contain enough evidence to reconstruct historic semantics for `wregoe_dual_dodec_control` or `plateau_30_vs_60_case`.
- Neither name is admitted to the active fixture registry, tests, Assessment semantics, Plan Fit semantics, UI, or normal product behavior.
- This is a non-inference rule, not a claim that those controls never had historical meanings.
- The durable accepted decision is recorded in `docs/ai/DECISIONS.md`.

## Stage 5B accepted record

- Contract file: `docs/ai/R1_STAGE5B_EVIDENCE_DISCIPLINE_CONTRACT_V1.md`
- The authoritative accepted-status and owner-intent-provenance amendment is `docs/ai/R1_STAGE5A_5B_ACCEPTANCE_CLOSEOUT_V1.md`.
- Stage 5B adopts the evidence-chain discipline:

```text
source record
→ normalized evidence fact
→ named programme requirement or constraint
→ requirement outcome
→ bounded Assessment or Plan Fit consequence
```

- Owner-provided intent may authorise forward design but does not establish lost historical semantics or turn unknown game facts into known facts.
- Missing, contradictory, stale, incomplete, unsupported, or out-of-scope evidence limits the conclusion; it cannot silently become a positive.
- No comparison may begin with total body count. A programme must first define finite, named requirements and constraints.
- The illustrative `plateau_30_vs_60_case` rule is capacity-sufficiency only: surplus bodies are neutral only where they change no named requirement or constraint. It is not a universal threshold, score, rank, recommendation, preference, or best-system rule.
- The accepted contract does not authorise external system research, a fixture, test changes, UI changes, code changes, live queries, or implementation.

## Preserved merged invariants

- The R1 laboratory remains DEV-only, fixture-backed, deterministic, and local.
- The lab exposes exactly five closed local select controls: Fixture, Lens kind, Lens value, Carrier mode, and Strategy.
- The first four selector IDs, values, defaults, ordering, and semantics remain unchanged. Strategy is explicit local DEV-lab context only, with fixed `baseline_local_strategy` and `remote_logistics_strategy` options; it is not inferred.
- Five fixture IDs and three carrier modes are selectable; the six approved fixture/scenario state rows are test assertions, not six fixtures.
- The fixed template is displayed read-only.
- Lens remains explicit context only; it does not alter accepted fixture outcomes, conditions, evidence, state, Plan Fit output, or ordering.
- Carrier behavior remains bounded to accepted logistics-sensitive outcomes. `compare_both` preserves `no_carrier` then `carrier_available` order.
- Stage 4B Plan Fit remains subordinate to accepted Stage 2B Assessment output.
- No production behavior, scoring, ranking, recommendation, strategy inference, planning behavior, or deployment is introduced.

## Next safe action

No further work is authorised by this closeout. Do not collect external system evidence, create a fixture, edit R1 code/tests/UI, change the normal application, merge a later implementation, or deploy. Any later programme-definition or evidence-inventory stage requires separate owner authorisation.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
