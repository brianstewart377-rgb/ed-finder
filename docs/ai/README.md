# AI Continuity Protocol

This directory is the durable handoff record for AI-assisted work on ED-Finder.

Chats are disposable. Git history and the files in this directory are the source of truth.

## Read order

1. `docs/DOCUMENTATION_INDEX.md`
2. `docs/ai/CURRENT_STAGE.md`
3. `docs/ai/PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`
4. `docs/ai/CPE_SYSTEM_ASSESSMENT_ROADMAP_V1.md`
5. `docs/ai/SYSTEM_ASSESSMENT_CONTINUITY_LEDGER_V1.md`
6. `docs/ai/DECISIONS.md`
7. live GitHub PR state and live Git branch/worktree state

`docs/ai/PROJECT_CONTEXT.md`, `docs/ai/RECOVERY.md`, `docs/ai/CHAT_HANDOFF_TEMPLATE.md`, and `docs/ai/ACCEPTANCE_PROTOCOL.md` support that reading order. They do not outrank `docs/ai/CURRENT_STAGE.md`.

## Non-negotiable rules

1. No meaningful stage may exist only in an agent chat or only as an uncommitted worktree.
2. Before implementation, create or select a named branch and record the exact base commit in `CURRENT_STAGE.md`.
3. Before an agent stops, update `CURRENT_STAGE.md`, commit the change with the work where practical, and push the branch.
4. Agents must start in read-only recovery mode: read the control documents, inspect live GitHub/Git state, and report before editing.
5. Stage explicit paths only. Do not use `git add -A` for AI-assisted work.
6. Never put passwords, tokens, API keys, private prompts, or customer data in these files.
7. A chat transcript is supporting context, not the specification. Record accepted decisions in `DECISIONS.md` and stage-specific facts in `CURRENT_STAGE.md`.
8. Pre-merge acceptance and post-merge closeout are separate. Exact-head owner authorisation is mandatory. Merge closeout follows `PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`.

## Index

- `docs/DOCUMENTATION_INDEX.md` — practical documentation entry point and authority order.
- `CURRENT_STAGE.md` — single current control document for the active working point and next safe action.
- `CPE_SYSTEM_ASSESSMENT_ROADMAP_V1.md` — current future-system-assessment roadmap.
- `SYSTEM_ASSESSMENT_CONTINUITY_LEDGER_V1.md` — ownership, lifecycle, and anti-burial continuity record.
- `PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md` — mandatory post-merge recovery-record protocol.
- `R1_STAGE6_STATUS_CLOSEOUT_V1.md` — Stage 6 status closeout and accepted merge record.
- `R1_RECONSTRUCTION_CONTRACT_V1.md`, `R1_STAGE4_PLAN_FIT_CONTRACT_V1.md`, `R1_STAGE4C_PLAN_FIT_LAB_PRESENTATION_CONTRACT_V1.md`, `R1_STAGE5A_CONTROL_FIXTURE_DISCOVERY_V1.md`, `R1_STAGE5B_EVIDENCE_DISCIPLINE_CONTRACT_V1.md`, `R1_STAGE6B_CRE_CPE_BOUNDARY_CONTRACT_V1.md`, `R1_STAGE6C_CRE_CPE_FIELD_CONTRACT_DETAIL_V1.md` — R1 and boundary contracts.
- `PROJECT_CONTEXT.md`, `RECOVERY.md`, `CHAT_HANDOFF_TEMPLATE.md`, `ACCEPTANCE_PROTOCOL.md` — recovery and handoff material.
- `DECISIONS.md` — append-only durable decisions and invariants.

## Normal workflow

1. Read `docs/DOCUMENTATION_INDEX.md` and `CURRENT_STAGE.md`.
2. Read the merge-closeout protocol, roadmap, continuity ledger, and relevant `DECISIONS.md` entries.
3. Confirm branch, base commit, current commit, Git status, allowed files, and live PR state where relevant.
4. Do one narrow stage.
5. Run the evidence listed in `CURRENT_STAGE.md`.
6. Update `CURRENT_STAGE.md` with actual results, blockers, commit SHA where known, and the next safe action.
7. Commit and push the stage before leaving it.
8. After merge, perform durable closeout under `PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`.

## When a chat is too large

Do not try to summarise the whole chat manually. Update `CURRENT_STAGE.md`, commit and push it, then open a new chat and use `CHAT_HANDOFF_TEMPLATE.md`. The new agent should recover from the repository records and live GitHub/Git state rather than assume that chat history is correct.
