# Current Stage

> **This is the authoritative working-point record.** Update it before an agent stops, before a chat is closed, and after any accepted decision or evidence run.

## Status

**Stage 5B docs-only R1 evidence-discipline contract drafted — awaiting independent review and owner acceptance.**

## Baseline

- Canonical base branch: `work/r1-canonical-body-evidence`
- Stage 5B documentation branch: `docs/r1-stage5b-evidence-discipline`
- Stage 5B documentation base SHA: `dad3a99f4571428fcb517a13785be297f57e875a`
- Stage 5A discovery PR: `#290`, merged
- Stage 5A review head: `36371887bf09dad420c86b6c6ca6faffb7cfa0cd`
- Stage 5A merge commit: `dad3a99f4571428fcb517a13785be297f57e875a`
- Stage 5A was independently reviewed and owner-accepted before merge.
- Stage 4C acceptance closeout PR: `#289`, merged at `fe06439132f52c9ccae5c4652f10de838b5ec445`
- Stage 4C implementation PR: `#288`, merged at `5017b713627600887cefc781066c3a6eacfdbcba`
- Stage 4C accepted code commit: `4eabc24ba9b428c2902fa2221c15b7d5371d0433`
- Stage 4B implementation PR: `#286`, merged at `0565a60428904c4fe234f500e05be9871adb5c6d`
- Stage 4B contract PR: `#284`, merged at `411ceb9232966bf27aa027d72aa5622c83ee0d03`
- Stage 3B PR: `#282`, merged at `98b4bacf1d799e7937b449210046659b3e96615b`
- Stage 2B pure assessment core: PR `#280`, merged at `220c870f89a5af7f98adb88578373dbc3a681a9c`
- No deployment occurred.

## Stage 5A accepted record

- Discovery record: `docs/ai/R1_STAGE5A_CONTROL_FIXTURE_DISCOVERY_V1.md`
- Accepted conclusion: the canonical repository does not contain enough evidence to reconstruct semantics for `wregoe_dual_dodec_control` or `plateau_30_vs_60_case` as historic R1 controls.
- Neither name is admitted to the active fixture registry, tests, Assessment semantics, Plan Fit semantics, UI, or normal product behavior.
- This is a non-inference rule, not a claim that those controls never had historical meanings.
- The durable accepted decision is appended in `docs/ai/DECISIONS.md`.
- Any later forward reconstruction requires an explicit proof question, deterministic payload, traceable evidence, expected outputs, tests, independent review, and separate owner authorisation.

## Active Stage 5B contract

- Contract file: `docs/ai/R1_STAGE5B_EVIDENCE_DISCIPLINE_CONTRACT_V1.md`
- Stage 5B adopts a proposed evidence-chain discipline for later R1 forward reconstruction:

```text
source record
→ normalized evidence fact
→ named programme requirement or constraint
→ requirement outcome
→ bounded Assessment or Plan Fit consequence
```

- The contract distinguishes repository evidence, external observed evidence, owner-provided forward-design intent, deterministic fixture representation, and derived evidence facts.
- Owner-provided intent may authorise forward design but does not establish lost historical semantics or turn unknown game facts into known facts.
- Missing, contradictory, stale, incomplete, or out-of-scope evidence must limit the conclusion; it cannot be silently treated as a positive.
- No comparison may begin with total body count. A programme must first define finite, named requirements and constraints.
- The illustrative `plateau_30_vs_60_case` principle is proposed only as a capacity-sufficiency rule: surplus bodies are neutral only where they change no named requirement or constraint. It is not a universal 30-body threshold, score, rank, recommendation, preference, or best-system rule.
- A larger system may differ materially where extra bodies add a named required capability or resolve a named constraint.
- The immediate deliverable is this documentation-only contract. No system evidence inventory, fixture, test, UI, code, live query, or implementation is authorised by Stage 5B.

## Stage 5B allowed files

- `docs/ai/CURRENT_STAGE.md`
- `docs/ai/DECISIONS.md`
- `docs/ai/R1_STAGE5B_EVIDENCE_DISCIPLINE_CONTRACT_V1.md`

## Stage 5B exact non-goals

Stage 5B does not add or change:

- R1 fixture data, types, templates, requirements, conditions, Assessment semantics, or Plan Fit semantics;
- R1 core, tests, DEV-lab UI, routes, normal navigation, providers, stores, APIs, network behavior, persistence, configuration, build behavior, production assets, exports, reports, or deployment;
- a universal threshold, score, rank, recommendation, preference, winner, best-system result, or automatic selection;
- live runtime data dependence or a claim of recovered historical semantics;
- an external system evidence inventory or a later implementation stage.

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

## Caveats

- No deployment occurred.
- Stage 5B is proposed documentation, not an accepted new semantic rule until independently reviewed and owner-accepted.
- Earlier Stage 4C validation evidence remains historical implementation evidence only; no validation commands are required or implied for this documentation-only stage.

## Next safe action

Obtain an independent read-only review of the Stage 5B evidence-discipline contract, the Stage 5A accepted decision entry, and this stage record. Do not collect external system evidence, create a fixture, edit R1 code/tests/UI, change the normal application, merge a new implementation, or deploy until the owner accepts the reviewed Stage 5B contract and separately authorises any later evidence-inventory stage.

## Recovery instruction

If context is lost, do not edit code. Read the files in `docs/ai`, run the read-only commands in `RECOVERY.md`, and report the result. Continue only after the owner approves the recovered state.
