# Pull Request Acceptance Policy

This document is the canonical merge-acceptance policy for every ED-Finder pull
request. A PR is accepted only against its exact latest head commit. Record that
latest-head SHA and all evidence below on the PR before merge.

## Acceptance gate

All of the following are mandatory:

1. Every protected CI, security, coverage, and status check has completed
   successfully against the exact latest PR head SHA. Green CI alone is
   insufficient.
2. Both configured automated reviewers have completed against that exact SHA:
   - `chatgpt-codex-connector` (**Codex Review**)
   - **Octopus Review**

   A reviewer that did not auto-run must be explicitly triggered when the head
   is being evaluated as a final merge candidate. Pending and still-reviewing
   services must be awaited; ordinary pending or in-progress review cannot be
   waived. This trigger obligation does not require Octopus to review every
   intermediate implementation/remediation head; review cadence is defined
   below.
3. Inspect every review surface with pagination: top-level PR conversation
   comments, formal review bodies, inline review comments, and unresolved
   review conversations/threads. Use `--paginate` or an equivalent complete
   cursor loop for each applicable endpoint so later pages cannot be silently
   omitted. Checking only a summary or only inline comments is insufficient.
4. Triage every substantive finding from either reviewer against the actual
   latest code. Record each disposition on the PR as exactly one of:
   - fixed and verified;
   - demonstrated false positive with concrete evidence;
   - superseded by a verified later change; or
   - explicitly accepted risk by the repository owner.

   No substantive unresolved finding, conversation, or thread may remain at
   merge. A clean review from one service never overrides a finding from the
   other.
5. Any new commit invalidates all prior CI and reviewer evidence for merge
   eligibility on the new head. Re-run protected checks on the new head as
   normal. Do not automatically rerun Octopus on every intermediate head;
   only trigger it after the new head again satisfies the final-candidate
   criteria below. Before merge, both reviewer services must have completed
   against the exact latest head; record each reviewer's reviewed SHA for that
   head. The only exception is the docs-only update-merge rule below, which
   applies to Octopus alone.

Reviewer findings are evidence, not ground truth. Verify them against the
actual code before acting: trace values to where they are persisted or used,
search the whole repository before declaring code unused, and read the relevant
tests before claiming a gap. This verification discipline does not relax the
requirement to disposition every substantive finding.

## Final-candidate review cadence

Octopus is a merge-candidate reviewer, not an iterative-edit reviewer. Paid or
resource-heavy independent review must be concentrated on heads that are
actually intended to merge.

Use this sequence:

1. During implementation and ordinary remediation, push coherent changes and
   run the protected CI/check surface. Codex may review as configured or when
   useful, but do not deliberately trigger Octopus for an intermediate head
   that is already expected to change.
2. A head becomes a **final candidate** only when the intended implementation
   and known remediation are complete, protected CI is green on that exact
   head, and there is no already-known accepted finding that still requires a
   code change. The intent is: absent a new reviewer finding, this is the head
   that would be merged.
3. Trigger Octopus once for that final-candidate head. Its merge-acceptance
   evidence is valid only for the exact SHA it reviewed.
4. If Octopus (or another reviewer) finds issues requiring code changes, batch
   the accepted fixes where practical, push the new head, run protected CI, and
   return to step 2. Do not trigger Octopus on each intermediate fix commit.
5. Once the resulting head again qualifies as a final candidate, trigger one
   fresh Octopus review. Merge only when the acceptance gate above is satisfied
   on that exact final head.

The intended Octopus repository/service configuration is therefore
**final-candidate/manual review rather than automatic per-push review**. The
external Octopus setting should be configured so routine branch pushes do not
spend review credits automatically. Repository policy cannot prove that remote
service setting, so operators must verify it separately; an accidental
per-push review does not create a policy requirement to keep doing so.

**Configured 2026-10-20 (owner):** the self-hosted Octopus instance
(`octopus.ed-finder.app`, the `octopus-web-1` container on the production host,
image `ghcr.io/octopusreview/octopus-selfhost:1.0.122`) now has Auto Review
**off** for `ed-finder` and a spend limit set, so pushes no longer trigger a
review. A review is requested manually, once per final-candidate head, by
posting the PR comment `@octopus-review`; the review it returns is valid only
for the head SHA that was current when the comment was posted. This records the
remote setting at that date; it does not prove the setting on any later date,
and operators should still check it when Octopus reviews appear without being
asked for.

This cadence changes *when* Octopus is invoked, not the exact-head safety rule.
Outside the one narrow case in the next section, a stale Octopus review from an
earlier SHA can never contribute to merge eligibility.

## Docs-only update merges (owner decision 2026-10-30)

Branch protection on `main` requires a PR branch to be up to date before merge.
When `main` moves, the branch has to merge it in, which makes a new head. The
owner decided on 2026-10-30 that, for a docs-only PR, that alone does not need a
fresh Octopus review.

The Octopus review of an earlier head still counts for the new head **only when
every one of these holds**:

1. **Docs-only.** Every file in the PR's own diff against `main`
   (`git diff --name-only origin/main...HEAD`) is under `docs/` or is a Markdown
   (`.md`) file. No file is under `.github/`, `apps/`, `scripts/`, `sql/`,
   `tests/` or `deploy/`.
2. **Only update merges since the review.** Every commit after the
   Octopus-reviewed head is a merge of `main` into the branch, made with no
   conflict resolution and no other edit.
3. **The PR's own lines are unchanged.** The added and removed lines of the PR's
   own diff are identical at both heads. Line numbers may shift. Check it by
   comparing the `+`/`-` lines of `git diff $(git merge-base origin/main <SHA>) <SHA>`,
   leaving out the `+++`/`---` file headers, for the reviewed SHA and the new
   head. Run against the current `origin/main`: `git merge-base` then gives each
   head's own base.
4. **The earlier Octopus review is settled.** It completed on the earlier head,
   and every finding from it has a recorded disposition under the acceptance
   gate.
5. **Everything else is on the new exact head.** All protected CI checks are
   green on the new head. Codex Review has completed on the new head with no
   unresolved finding. The paginated inspection of every review surface is done
   on the new head.
6. **It is recorded on the PR.** A PR comment names the Octopus-reviewed SHA,
   the new head SHA, the merge commits between them, and the result of check 3.

If any condition fails, the normal rule applies and Octopus is requested again
for the new head. That includes any edit to the PR's own text, any file outside
the docs-only set, and any conflict resolution that touches the PR's lines.
This rule never applies to code PRs. It changes nothing about Codex Review or
CI, which still run on every head.

## Reviewer failure and owner waiver

Reviewer service failure or unavailability is **fail-closed by default**. Never
infer or silently apply a waiver. An explicit written repository-owner waiver
is permitted only when the named reviewer service has actually failed or is
unavailable, never because it is pending or still reviewing. The waiver must:

- name the failed or unavailable reviewer service and document the failure;
- record replacement manual-review evidence covering the exact latest head;
- explicitly record the accepted risk; and
- retain every other safeguard in this policy, including protected checks,
  complete paginated inspection, explicit dispositions, and no substantive
  unresolved thread.

Without all of those conditions, the PR must wait for the reviewer service to
recover and complete.

An Octopus response of HTTP `429` with a "no credits remaining" (or equivalent
spend-limit) message is a **service-unavailability failure** of the kind this
section covers: it is an account billing/spend-limit condition on the Octopus
side, not a finding about the code and not a review of the head. It must not be
recorded as a clean review, and it does not waive the gate; either the owner
restores credits (or raises the spend limit) and the review is re-requested for
the same head, or the owner issues the written waiver above.

## Auto-merge transition

Removing an auto-merge workflow does not cancel auto-merge requests already
stored by GitHub. Before accepting any PR under this policy, repository
maintainers must complete a one-time audit of all open PRs and cancel every
pre-existing server-side auto-merge request. The fail-closed steady state is no
open PR with auto-merge enabled.

Historical transition evidence (2026-08-31): a repository-wide event-history
audit covered every then-open PR: #454, #505, #513, #515, #526, #527, #534,
and #536. PR #515 retained a legacy `auto_squash_enabled` request; it was closed
and immediately reopened solely to produce `auto_merge_disabled` without
changing its head. None of the other then-open PR event histories contained an
auto-merge enable event. Earlier PRs #492 and #502 also had legacy requests and
were closed fail-closed to cancel them. After those cancellations, no open PR
had auto-merge enabled.

## Findings after merge

Waiting for both reviewers to complete against the exact final-candidate head
is what prevents late-arriving findings. If a finding nevertheless arrives
after merge, add it to the repair backlog immediately and block dependent work
where relevant until it is triaged and resolved.
