# Stage 19AT - Paused-State Next Operator Decision

## Purpose

Stage 19AT records the next Stage 19 checkpoint after Stage 19AS.2 as a
paused-state operator decision gate. It is a documentation and static-test
checkpoint only.

Stage 19AT does not choose, approve, or execute the next operational lane. Any
wider pilot, scheduler work, canonical write lane, canonical apply lane,
rebaseline, or production-like database target still requires explicit operator
approval in a later checkpoint.

## Current Authority

Active authority remains
`docs/colonisation-redesign/stage-19-state-authority.json`.

- Stage 19AS-AU is complete and recorded.
- Stage 19AS.1 is complete and recorded.
- Stage 19AS.2 is complete and recorded.
- Stage 19 remains paused.
- The approved Stage 19AR baseline remains the 5f777 source run, b617 artifact,
  and 25 diagnostic rows.
- The Stage 19AS-AU checkpoint remains the 100-row source run
  `stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9`.
- No canonical apply is complete.
- No rebaseline is complete.

## Decision Boundary

Stage 19AT is a decision checkpoint, not an execution checkpoint.

It records that the next operational lane must be selected and approved before
any new Stage 19 execution happens. The decision may later choose a docs-only
design, read-only verification, staging-only write, controlled write, or another
test-environment gate, but Stage 19AT itself approves none of those executions.

The next operational lane still requires explicit operator approval.

## Blocked Work

Stage 19AT keeps these actions blocked:

- wider pilot execution;
- Stage 19 operator commands;
- Stage 19AR with `--commit`;
- Stage 19AS-AU with `--commit`;
- full source batch execution;
- database mutation;
- staging row writes;
- canonical table writes;
- canonical apply;
- rebaseline;
- scheduler, timer, or service-manager work;
- production-like database targets;
- host `5432` as a direct Stage 19 target;
- secrets access or printing;
- runtime source JSON or operator artifact JSON commits.

No Stage 19 operator command is authorized by this checkpoint. No DB mutation is
authorized by this checkpoint.

## Added Coverage

`tests/test_stage19at_paused_state_next_operator_decision.py` covers:

- Stage 19 remains paused in active authority;
- Stage 19AS-AU remains complete and recorded;
- Stage 19AS.1 remains recorded;
- Stage 19AS.2 remains recorded;
- Stage 19AT is documented as docs/static-test only;
- no canonical apply or rebaseline is marked complete;
- wider pilot execution and database execution remain unauthorized;
- forbidden actions remain documented.

## Validation

Expected focused validation:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest tests/test_stage19at_paused_state_next_operator_decision.py -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest tests/test_stage19as2_operator_script_contract.py tests/test_stage19as1_disposable_postgres_constraints.py -p no:cacheprovider
git diff --check
```

These checks are repo-local and static/unit-only for Stage 19AT. They must not
run operator scripts or DB commands.

