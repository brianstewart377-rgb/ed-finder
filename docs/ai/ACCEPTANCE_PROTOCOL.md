# Acceptance Checkpoint Protocol

This protocol turns a reviewer acceptance into a durable recovery point.

## What acceptance means

A stage is not accepted merely because an assistant writes “approved” in chat. Before acceptance, the implementation must already be committed and pushed to a named branch, with the exact reviewed code commit identified.

Acceptance does **not** merge, deploy, rebase, or change product code.

## Automatic actions after acceptance

When the reviewing assistant accepts a stage, it should perform these actions without waiting for a separate reminder:

1. Confirm the accepted branch, pull request if any, and exact reviewed code commit SHA.
2. Create a documentation-only acceptance checkpoint by updating `docs/ai/CURRENT_STAGE.md` on the accepted branch. The update must record:
   - status: `Accepted`;
   - accepted code commit SHA;
   - acceptance date/time;
   - branch and pull request reference, if any;
   - evidence reviewed;
   - caveats or follow-up work;
   - next safe action.
3. Add a top-level pull-request comment, when a pull request exists, containing the same acceptance summary and the SHA of the documentation-only checkpoint commit.
4. State clearly in chat that the checkpoint was written and that merge/deployment remain separate decisions.

The documentation-only checkpoint commit is allowed to follow the accepted code commit. It must modify only `docs/ai/` files. It does not reopen product-code review.

## If the code is not pushed

Do not create an acceptance checkpoint and do not call the stage accepted. Ask for the exact branch and pushed commit first.

## If there is no pull request

Create the documentation-only checkpoint on the named branch and report its commit SHA. The Git commit is still the durable acceptance record.

## Standard acceptance record

Use this structure in `CURRENT_STAGE.md`:

```md
## Acceptance checkpoint

- Status: Accepted
- Accepted code commit: `<full SHA>`
- Acceptance checkpoint commit: `<full SHA once created>`
- Branch: `<branch>`
- Pull request: `<number or none>`
- Evidence reviewed:
  - `<tests/build/artifacts>`
- Caveats:
  - `<none or explicit items>`
- Next safe action:
  - `<merge, start next planning stage, or other explicit step>`
```

## New-chat recovery after acceptance

A new agent must read `CURRENT_STAGE.md` first. It should treat the accepted code SHA as the reviewed baseline and the acceptance checkpoint commit as the durable handoff state. It must not infer that a merge or deployment occurred unless the record says so.
