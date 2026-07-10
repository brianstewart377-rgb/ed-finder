# Remote Branch Cleanup 2026-07-10

This note captures the safe immediate remote-branch cleanup from the integrated
post-deploy line at `ee6707c`.

Status:

- completed on 2026-07-10 for:
  - `origin/devscore-retire-ratings`
  - `origin/stage25-closeout-checkpoint`
  - `origin/TEST`
- completed on a second-pass duplicate cleanup for:
  - `origin/work/r1-canonical-body-evidence`
- the temporary local fetch exclusion for `^refs/heads/TEST` was also removed
- the current local worktree branch was renamed to
  `work/post-audit-followthrough-20260710` and tracks `origin/main`
- the dedicated `main` worktree was fast-forwarded to `20c25b2`

## Safe Now

These remote branches are already fully contained in `origin/main` and are the
best immediate delete candidates:

- `devscore-retire-ratings`
  - now points to the same commit as `main` (`ee6707c`)
  - keeping it around mostly creates re-divergence risk and preserves the old
    vocabulary in the branch name
- `stage25-closeout-checkpoint`
  - its head (`98a3ff4`) is already contained in `origin/main`
  - the history itself is still preserved after branch deletion because the
    commit is now reachable from `main`
- `TEST`
  - not fetched locally on Windows because the repo currently carries a
    negative fetch refspec to avoid the `TEST` vs `test/*` ref collision
  - should be deleted on the remote first, then the local fetch exclusion can
    be removed

## Exact PowerShell Commands

Executed from the repo root on the local machine:

```powershell
git push origin --delete devscore-retire-ratings
git push origin --delete stage25-closeout-checkpoint
git push origin --delete TEST

git config --unset-all remote.origin.fetch "^refs/heads/TEST"
git fetch origin --prune
git branch -r
```

If you want a one-shot sequence with explicit pauses:

```powershell
git push origin --delete devscore-retire-ratings
git push origin --delete stage25-closeout-checkpoint
git push origin --delete TEST
git config --get-all remote.origin.fetch
git config --unset-all remote.origin.fetch "^refs/heads/TEST"
git config --get-all remote.origin.fetch
git fetch origin --prune
git branch -r --merged origin/main
```

## Why Not Delete More Right Now

`git branch -r --merged origin/main` currently shows only:

- `origin/main`

That means the large historical docs/stage branch pile should not be deleted as
an "obviously safe" batch without a second pass that explicitly decides whether
each branch should be:

- deleted as merged,
- tagged then deleted,
- or retained for a deliberate historical reason.

## Recommended Next Pass

Use this review command to build the next archival/delete shortlist:

```powershell
git for-each-ref --format="%(refname:short) %(objectname:short) %(committerdate:short) %(subject)" refs/remotes/origin
```

Then evaluate the older `docs-*`, `stage-*`, and `feat/*` refs in batches
rather than deleting them blind.

Current remaining remote-head inventory after the safe-now and duplicate-alias
cleanup:

- `docs*`: 53
- `stage-*`: 30
- `feat/*`: 10
- `fix/*`: 3
- `chore/*`: 2
- `other`: 2

That means the next meaningful cleanup should be done by family, not one branch
at a time:

1. `docs*` historical closeout/design branches
2. `stage-*` implementation-history branches
3. `feat/*` and `fix/*` branches that may still hold unique non-ancestor tips

One safe pattern already used in the second pass:

- if two remote refs point at the exact same SHA, delete the scratchier alias
  and keep the clearer canonical name
- example completed here:
  - kept `origin/feat/stage25d-b-plan-outcome-loop`
  - deleted duplicate alias `origin/work/r1-canonical-body-evidence`
