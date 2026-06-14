# Stage 19AU - Read-Only AS-AU Safety Gate

## Purpose

Stage 19AU records the next Stage 19 checkpoint after Stage 19AT as a
read-only AS-AU safety-gate checkpoint. Its purpose is to keep the recorded
Stage 19AR and Stage 19AS-AU state inspectable before any new Stage 19 write,
wider pilot, scheduler work, or canonical path is considered.

This checkpoint started as documentation and static/unit test coverage. The
follow-up Stage 19AU read-only DB verification used the approved safe local
target `127.0.0.1:55432` and did not run Stage 19 operator commands, create a
source run, write staging rows, enable scheduler work, rebaseline, or run
canonical apply.

## Current Authority

Active authority remains
`docs/colonisation-redesign/stage-19-state-authority.json`.

- Stage 19AS-AU is complete and recorded.
- Stage 19AS.1 is complete and recorded.
- Stage 19AS.2 is complete and recorded.
- Stage 19AT is complete and recorded.
- Stage 19 remains paused.
- The approved Stage 19AR baseline remains the 5f777 source run, b617 artifact,
  and 25 diagnostic rows.
- The Stage 19AS-AU checkpoint remains the 100-row source run
  `stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9`.
- No canonical apply is complete.
- No rebaseline is complete.

## Verification Boundary

Stage 19AU is read-only verification only. It does not authorize a write-capable
lane.

The Stage 19AU implementation PR did not run DB verification because no explicit
safe local or disposable read-only DB target was supplied. That was recorded as:

```text
db_verification:
not_run

db_verification_reason:
No explicit safe local/disposable DB target was provided for this checkpoint.
The repo changes are docs/static-test only.
```

The follow-up read-only DB verification passed against the approved safe local
target `127.0.0.1:55432`. The connection resolved to database `edfinder` as
user `edfinder`, with container port `5432` reached only through the safe host
mapping `127.0.0.1:55432`.

```text
db_verification:
passed

db_verification_target:
127.0.0.1:55432
```

The follow-up verification confirmed:

- the approved Stage 19AR baseline source run, bridge key, b617 artifact, and
  25 diagnostic rows;
- the Stage 19AS-AU source run, bridge key, 7f6 artifact checksum, and row
  counts of 100 read, 100 staged, 0 rejected, and 0 skipped;
- every checked Stage 19AR and Stage 19AS-AU staging row remains diagnostic-only,
  uses the legacy `enrichment_source_runs.id` bridge, avoids `source_runs.id`,
  and preserves `canonical_write_allowed=false`;
- no active or failed Stage 19 source run blocks the next lane;
- source-run safety boundaries keep canonical apply disabled, canonical writes
  planned at zero, scheduler/service work disabled, and production DB access
  false;
- the AS-AU artifact file checksum matches the recorded
  `7f6f20a4d01b543d8ef12072891d8fda749bcc1b6633c26bc9ec178a40b8f84e` value;
- the prerequisite staging evidence remains separate from the Stage 19AS-AU
  completion source run.

Any future DB verification must remain read-only, must use existing
local/disposable guardrails, must redact secrets, and must stop on
production-like DSNs or direct host `5432` targets.

Allowed future read-only checks may verify only:

- the approved Stage 19AR `source_run_key`, bridge key, artifact hash, and 25
  row baseline;
- the Stage 19AS-AU `source_run_key`, bridge key, artifact hash, and operator
  artifact hash;
- AS-AU row counts of 100 read, 100 staged, 0 rejected, and 0 skipped;
- diagnostic isolation and canonical-write blocking for AS-AU staging evidence;
- absence of active or failed Stage 19 source runs that block the next lane;
- absence of canonical apply or canonical-write evidence in checked Stage 19
  artifacts.

## Blocked Work

Stage 19AU keeps these actions blocked:

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

No wider pilot is authorized by Stage 19AU. No DB mutation is authorized by
Stage 19AU. No scheduler or service work is authorized by Stage 19AU. No
canonical apply or rebaseline is authorized by Stage 19AU.

Any future write-capable lane requires a separate explicit operator decision.

## Added Coverage

`tests/test_stage19au_readonly_asau_safety_gate.py` covers:

- Stage 19 remains paused in active authority;
- Stage 19AS-AU remains complete and recorded;
- Stage 19AS.1 remains recorded;
- Stage 19AS.2 remains recorded;
- Stage 19AT remains recorded;
- Stage 19AU is documented as read-only docs/static-test coverage for this PR;
- DB verification is recorded as `not_run` unless an explicit safe target is
  provided in a later checkpoint;
- no canonical apply or rebaseline is marked complete;
- wider pilot execution, scheduler/service work, DB mutation, and Stage 19
  operator execution remain unauthorized;
- forbidden actions remain documented.

## Validation

Expected focused validation:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/dev/resolve_project_state.py --strict
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest tests/test_stage19au_readonly_asau_safety_gate.py -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest tests/test_stage19at_paused_state_next_operator_decision.py tests/test_stage19as2_operator_script_contract.py tests/test_stage19as1_disposable_postgres_constraints.py -p no:cacheprovider
git diff --check
```

These checks are repo-local and static/unit-focused for Stage 19AU. They must
not run Stage 19 operator commands or mutate a database.
