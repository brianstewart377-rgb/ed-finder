# Remote Branch Cleanup 2026-07-10

This note captures the full remote-branch cleanup from the integrated
post-deploy line through the final archive/delete sweep on 2026-07-10.

Status:

- completed on 2026-07-10 for:
  - `origin/devscore-retire-ratings`
  - `origin/stage25-closeout-checkpoint`
  - `origin/TEST`
- completed on a second-pass duplicate cleanup for:
  - `origin/work/r1-canonical-body-evidence`
- completed on a final archive/delete sweep for every remaining non-`main`
  remote head under `origin/chore/*`, `origin/feat/*`, `origin/fix/*`, and
  `origin/fix-*`
- the temporary local fetch exclusion for `^refs/heads/TEST` was also removed
- the current local worktree branch was renamed to
  `work/post-audit-followthrough-20260710` and tracks `origin/main`
- the dedicated `main` worktree was fast-forwarded to the current `origin/main`
- `99` archive tags were created and pushed under
  `archive/remote-branches/2026-07-10/*`
- the remote branch list now contains only:
  - `origin/HEAD -> origin/main`
  - `origin/main`

## Final Outcome

Remote branch clutter is now fully drained. Historical work is preserved by the
archive-tag namespace, while the live remote branch surface is reduced to the
single canonical branch:

- `origin/main`

That leaves local/worktree discipline straightforward:

- `git fetch --prune`
- `git pull --ff-only`
- branch from `main` when new work actually begins
- delete remote heads promptly after merge or archive-tag them if they are being
  retired as historical snapshots instead of active integration branches

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

## Final Sweep Method

The historical `docs*` and `stage-*` families were already archive-tagged and
deleted in the earlier sweep. The remaining families were then evaluated with
divergence counts against `origin/main`:

```powershell
$branches = git for-each-ref --format='%(refname:short)' refs/remotes/origin |
  Where-Object { $_ -notin @('origin','origin/HEAD','origin/main') }
foreach ($branch in $branches) {
  $counts = git rev-list --left-right --count origin/main...$branch
  '{0} {1}' -f $branch, $counts
}
```

Those counts confirmed that the remaining refs still carried unique historical
tips rather than being clean merge-ancestors. We therefore used the same
preserve-then-delete pattern as the earlier sweep:

1. create archive tags for every remaining remote head
2. push the archive tags
3. delete the remote heads
4. `git fetch --prune`

Representative branches archived and deleted in that final pass:

- `origin/chore/ai-continuity-protocol`
- `origin/chore/review-lab-product-pr-gate`
- `origin/feat/colonisation-access`
- `origin/feat/local-review-test-environment`
- `origin/feat/r1-assessment-core`
- `origin/feat/r1-assessment-lab-presentation`
- `origin/feat/r1-lab-entry-boundary`
- `origin/feat/r1-plan-fit-core`
- `origin/feat/r1-stage4c-plan-fit-lab`
- `origin/feat/stage25c-selected-system-context`
- `origin/feat/stage25c-selected-system-context-clean`
- `origin/feat/stage25d-b-plan-outcome-loop`
- `origin/fix-hetzner-operator-ssh-key-newline`
- `origin/fix/db-isolation-explicit-empty-env`
- `origin/fix/local-single-user-readiness`
- `origin/fix/stage23a-live-evidence-provider`

## Practical Result

Going forward, a healthy local sync loop is now simple again:

```powershell
git fetch origin --prune
git switch main
git pull --ff-only
git branch -r
```

Expected remote-branch output now:

```text
origin/HEAD -> origin/main
origin/main
```
