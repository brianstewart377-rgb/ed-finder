# Accepted Decisions

This file is append-only. Record decisions that affect more than one stage, a later reconstruction, or a recovery workflow.

Use this format:

```md
## YYYY-MM-DD — Decision title

**Decision**
What was decided.

**Reason**
Why it was decided.

**Invariant**
What future work must preserve.

**Evidence / reference**
Branch, commit, issue, PR, test, or document.
```

---

## 2026-07-01 — Durable AI continuity protocol

**Decision**
AI-assisted work must be recoverable from the repository without relying on a live agent conversation.

**Reason**
A previous agent chat and an uncommitted laboratory worktree were lost. The loss showed that chat history and local uncommitted state are not durable project memory.

**Invariant**
Every substantive stage must have a named branch, exact base commit, durable current-stage record, explicit allowed-file list, evidence checklist, and a pushed checkpoint before an agent stops.

**Evidence / reference**
`docs/ai/README.md`, `docs/ai/CURRENT_STAGE.md`, and `docs/ai/RECOVERY.md` on branch `chore/ai-continuity-protocol`.

## 2026-07-01 — Chat handoff standard

**Decision**
When a chat becomes too large, the user may close it after updating and committing the stage handoff. A new agent chat must begin by reading the AI continuity files and inspecting Git state rather than relying on a manual recap.

**Reason**
A short, durable stage record is more reliable than a long chat summary and can be reviewed by any future agent.

**Invariant**
The new chat starts read-only. It may not edit, reset, stash, commit, merge, push, deploy, or delete files until it reports branch, commit, worktree status, and the active stage.

**Evidence / reference**
`docs/ai/CHAT_HANDOFF_TEMPLATE.md` and `docs/ai/RECOVERY.md`.

## 2026-07-01 — R1 Assessment Laboratory is a future clean reconstruction

**Decision**
The R1 Assessment Laboratory will not be reconstructed by guessing from lost chat state or by editing the current application branch opportunistically.

**Reason**
The earlier lab source tree and historical commit were not recoverable from the available checkout, local Git object database, remote branches, reflog, or searched workspace.

**Invariant**
Any future R1 lab work begins with a read-only inventory and written reconstruction contract, then uses a dedicated branch and narrow staged implementation.

**Evidence / reference**
`docs/ai/CURRENT_STAGE.md` and the 2026-07-01 recovery inspection.
