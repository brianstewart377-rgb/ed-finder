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
   normal. Do **not** automatically rerun Octopus on every intermediate head;
   only trigger it after the new head again satisfies the final-candidate
   criteria below. Before merge, both reviewer services must have completed
   against the exact latest head and each reviewer's reviewed SHA must be
   recorded.

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

This cadence changes *when* Octopus is invoked, not the exact-head safety rule.
A stale Octopus review from an earlier SHA can never contribute to merge
eligibility.

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
