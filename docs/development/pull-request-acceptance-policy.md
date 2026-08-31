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

   A reviewer that did not auto-run must be explicitly triggered. Pending and
   still-reviewing services must be awaited; ordinary pending or in-progress
   review cannot be waived.
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
5. Any new commit invalidates all prior CI and reviewer evidence. Re-run every
   protected check, re-run both reviewer services, re-inspect every paginated
   review surface, and record each reviewer's reviewed SHA for the new exact
   head.

Reviewer findings are evidence, not ground truth. Verify them against the
actual code before acting: trace values to where they are persisted or used,
search the whole repository before declaring code unused, and read the relevant
tests before claiming a gap. This verification discipline does not relax the
requirement to disposition every substantive finding.

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

Historical transition evidence (2026-08-31): open Dependabot PRs #513 and #505
had `auto_merge: null`. PRs #492 and #502 had legacy requests from
`github-actions[bot]` and were closed fail-closed to cancel them. The resulting
audit found no open Dependabot PR with auto-merge enabled.

## Findings after merge

Waiting for both reviewers to complete against the latest head is what prevents
late-arriving findings. If a finding nevertheless arrives after merge, add it
to the repair backlog immediately and block dependent work where relevant until
it is triaged and resolved.
