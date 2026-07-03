# Acceptance Protocol

This protocol defines pre-merge acceptance. Post-merge closeout is separate and is governed by `docs/ai/PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md`.

## What acceptance means

A stage is not accepted merely because an assistant writes “approved” in chat. Before acceptance, the implementation must already be committed and pushed to a named branch, with the exact reviewed head commit identified.

Acceptance means the owner authorises merge against that exact live reviewed head after independent review.

Acceptance does **not** merge, deploy, rebase, close out merge records, or grant any new implementation authority.

## Mandatory pre-merge checks

Before calling a stage accepted:

1. Confirm the branch, pull request if any, and exact reviewed head SHA.
2. Re-check the live PR head, changed files, review state, and actionable threads when a PR exists.
3. Confirm the owner authorises that exact head SHA, not a moving branch in general.
4. Confirm the evidence reviewed and any explicit caveats.

If the head moved, a required review is missing, or an actionable thread remains open, pause and re-review instead of calling it accepted.

## Durable record rule

Acceptance and merge closeout are distinct:

- **Pre-merge acceptance** records the exact reviewed head and the owner's merge authorisation.
- **Post-merge closeout** records the actual merge event, including merge SHA and what changed or did not change.

Do not weaken accountability by collapsing those two steps into one vague status.

## If the code is not pushed

Do not call the stage accepted. Ask for the exact pushed branch and reviewed head first.

## If there is a pull request

Record the exact PR number and exact reviewed head. A PR comment may be useful in some cases, but it is not a mandatory rule when it would conflict with the accepted merge-closeout process.

## Standard pre-merge acceptance record

Use this structure in `CURRENT_STAGE.md` when a dedicated acceptance checkpoint is needed before merge:

```md
## Acceptance checkpoint

- Status: Accepted, awaiting merge
- Accepted reviewed head: `<full SHA>`
- Branch: `<branch>`
- Pull request: `<number or none>`
- Evidence reviewed:
  - `<tests/build/artifacts>`
- Caveats:
  - `<none or explicit items>`
- Next safe action:
  - `Merge only against the exact accepted head, then perform merge closeout under docs/ai/PROJECT_CONTINUITY_AND_MERGE_CLOSEOUT_PROTOCOL_V1.md.`
```

## After merge

After merge, do not rely on the pre-merge acceptance note alone. Update the durable recovery records under the merge-closeout protocol so a later recovery can distinguish:

- what exact head was accepted;
- what exact merge commit landed;
- what changed;
- what did not change; and
- what remains safe next.
