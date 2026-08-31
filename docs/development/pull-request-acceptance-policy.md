# Pull Request Acceptance Policy

This document is the canonical merge-acceptance policy for every ED-Finder pull
request. A PR is accepted only against its latest head commit; record that
latest-head SHA in the PR before merge.

## Acceptance gate

All of the following are mandatory:

1. Every required CI, security, coverage, and status check for the latest PR
   head has completed successfully. Green CI alone is insufficient.
2. Both configured automated reviewers have completed against the latest PR
   head:
   - `chatgpt-codex-connector` (**Codex Review**)
   - **Octopus Review**

   Do not merge while either reviewer is pending, still reviewing, or errored.
   If either reviewer did not auto-run, explicitly trigger it and wait for it
   to complete.
3. Inspect all relevant review surfaces with pagination: top-level PR/issue
   conversation comments, formal review bodies, inline review comments, and
   unresolved review conversations. Checking only a summary or only inline
   comments is insufficient. Use paginated API queries (`--paginate` or an
   equivalent cursor loop) so later pages cannot be silently omitted.
4. Triage every substantive finding from either reviewer against the actual
   latest code. Record each disposition on the PR as exactly one of:
   - fixed and verified;
   - demonstrated false positive with concrete evidence;
   - superseded by a verified later change; or
   - explicitly accepted risk by the repository owner.

   No substantive unresolved finding or review conversation may remain at
   merge. A clean review from one bot never overrides a finding from the other.
5. Any new commit after a review invalidates that review for acceptance unless
   the reviewer clearly reviewed the new head. Record the reviewed SHA for
   Codex Review and Octopus Review separately.

Reviewer findings are evidence, not ground truth. Verify them against the
actual code before acting: trace values to where they are persisted or used,
search the whole repository before declaring code unused, and read the relevant
tests before claiming a gap. This verification discipline does not relax the
requirement to disposition every substantive finding.

## Reviewer failure and owner waiver

Reviewer service failure or unavailability is **fail-closed by default**. Never
infer or silently apply a waiver. The only exception is an explicit written
repository-owner waiver on the PR that:

- names the unavailable reviewer;
- records the replacement manual review and its evidence; and
- explicitly accepts the risk.

Without all three, the PR must wait for the reviewer service to recover.

## Findings after merge

Waiting for both reviewers to complete against the latest head is what prevents
late-arriving findings. If a finding nevertheless arrives after merge, add it
to the repair backlog immediately and block dependent work where relevant until
it is triaged and resolved.
