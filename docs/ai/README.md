# AI Continuity Protocol

This directory is the durable handoff record for AI-assisted work on ED-Finder.

Chats are disposable. Git history and the files in this directory are the source of truth.

## Non-negotiable rules

1. No meaningful stage may exist only in an agent chat or only as an uncommitted worktree.
2. Before implementation, create or select a named branch and record the exact base commit in `CURRENT_STAGE.md`.
3. Before an agent stops, update `CURRENT_STAGE.md`, commit the change with the work where practical, and push the branch.
4. Agents must start in read-only recovery mode: read this directory, inspect Git state, and report before editing.
5. Stage explicit paths only. Do not use `git add -A` for AI-assisted work.
6. Never put passwords, tokens, API keys, private prompts, or customer data in these files.
7. A chat transcript is supporting context, not the specification. Record accepted decisions in `DECISIONS.md` and stage-specific facts in `CURRENT_STAGE.md`.

## Files

- `PROJECT_CONTEXT.md` — stable architecture, project rules, and practical commands.
- `CURRENT_STAGE.md` — the single authoritative record of the active stage and its next safe action.
- `DECISIONS.md` — append-only accepted decisions and invariants.
- `RECOVERY.md` — what an agent must do after context loss or a crash.
- `CHAT_HANDOFF_TEMPLATE.md` — a short prompt for starting a new chat without losing the working point.

## Normal workflow

1. Read `PROJECT_CONTEXT.md`, `CURRENT_STAGE.md`, and the relevant entries in `DECISIONS.md`.
2. Confirm branch, base commit, current commit, Git status, and allowed files.
3. Do one narrow stage.
4. Run the evidence listed in `CURRENT_STAGE.md`.
5. Update `CURRENT_STAGE.md` with actual results, blockers, commit SHA, and the next safe action.
6. Commit and push the stage before leaving it.
7. Start a new chat with the template if the current conversation becomes unwieldy.

## When a chat is too large

Do not try to summarise the whole chat manually. Update `CURRENT_STAGE.md`, commit and push it, then open a new chat and use `CHAT_HANDOFF_TEMPLATE.md`. The new agent should inspect the repository rather than assume that chat history is correct.
