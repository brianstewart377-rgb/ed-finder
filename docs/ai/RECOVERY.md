# Recovery Protocol

Use this protocol when an AI chat crashes, is closed, becomes too large, or returns with uncertain context.

## Stop condition

Until this protocol is complete, the agent must **not**:

- edit, create, move, or delete files;
- run formatting or code generation;
- reset, restore, stash, clean, amend, rebase, merge, commit, push, or deploy;
- claim that a worktree is clean unless the raw Git output proves it.

## Read first

From the repository root, read:

```text
docs/ai/README.md
docs/ai/PROJECT_CONTEXT.md
docs/ai/CURRENT_STAGE.md
docs/ai/DECISIONS.md
```

Then run these read-only commands and preserve the raw output:

```bash
pwd
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
git log --oneline -10
git diff --stat
git diff --name-status
git diff --check
git ls-files --others --exclude-standard
```

For frontend work, then inspect the actual project root before assuming paths:

```bash
find . -maxdepth 5 -type f -name package.json -print | sort
find . -maxdepth 7 -type f -path '*/src/App.tsx' -print | sort
```

## Recovery report format

Return only:

1. Repository root and frontend root.
2. Branch and full HEAD SHA.
3. Modified and untracked files, exactly as Git reports them.
4. Active stage status from `CURRENT_STAGE.md`.
5. Whether the current worktree matches the stage record.
6. Any mismatch, missing evidence, or blocker.
7. The next safe action, without making changes.

## If the expected branch or files are missing

Do not recreate work from memory. First search, read-only:

```bash
git worktree list --porcelain
git branch -a
git reflog --all --date=iso || true
git fsck --full --no-reflogs --unreachable || true
git remote -v
```

Then report whether recovery is possible from:

- the current checkout;
- another local worktree;
- a remote branch;
- reflog/unreachable objects;
- a pushed handoff/commit;
- or whether reconstruction requires a new, approved stage.

## Exit condition

Only the project owner may approve moving from recovery mode to planning or implementation mode.
