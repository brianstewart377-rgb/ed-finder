# New Chat Handoff Template

Use this when closing a large chat and opening a new one. Before using it, update `CURRENT_STAGE.md` with the real branch, commit, worktree status, completed evidence, blockers, and next safe action. Commit and push that update.

## Copy into the new agent chat

```text
You are taking over ED-Finder work after a planned chat handoff.

Start in read-only recovery mode. Do not edit, create, move, delete, reset, stash, clean, restore, commit, amend, rebase, merge, push, deploy, or run code generation.

Repository: brianstewart377-rgb/ed-finder
Expected branch: <copy from docs/ai/CURRENT_STAGE.md>
Expected current commit: <copy from docs/ai/CURRENT_STAGE.md>

Read these repository files first:
- docs/ai/README.md
- docs/ai/PROJECT_CONTEXT.md
- docs/ai/CURRENT_STAGE.md
- docs/ai/DECISIONS.md
- docs/ai/RECOVERY.md

Then run the read-only recovery commands in docs/ai/RECOVERY.md.

Return only:
1. current repository root;
2. branch and full HEAD SHA;
3. Git working-tree state;
4. whether this matches CURRENT_STAGE.md;
5. the active goal, allowed files, evidence status, blockers, and next safe action.

Do not make changes until I explicitly approve your recovery report.
```

## What to provide to ChatGPT or another non-repository agent

Upload or paste, in this order:

1. `docs/ai/PROJECT_CONTEXT.md`
2. `docs/ai/CURRENT_STAGE.md`
3. relevant recent entries from `docs/ai/DECISIONS.md`
4. the branch name and full commit SHA
5. the latest test/build/evidence output only if it is not already recorded in `CURRENT_STAGE.md`
6. a link or patch for the specific diff under review, if applicable

Avoid pasting an entire old conversation. The stage record and Git state should replace it.

## Before closing a chat checklist

- [ ] `CURRENT_STAGE.md` says exactly what is active and what is next.
- [ ] Allowed files and non-goals are explicit.
- [ ] Branch name, base SHA, and current SHA are recorded.
- [ ] Test/build/evidence results are recorded or linked.
- [ ] Known failures and unresolved choices are recorded.
- [ ] Current work is committed and pushed, or the handoff explicitly says why it is not safe to stop yet.
- [ ] No secrets or private credentials are present in commits or handoff files.

## Size rule

When the chat becomes hard to navigate, stop at a natural checkpoint. Update the stage record and start a new chat. Do not wait until the conversation is near a context limit.
