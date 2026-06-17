# Stage 22C - Operator Artifact Review And Audit Surfaces

## Purpose

Stage 22C improves how read-only operator-facing artifacts are inspected before
any later handoff or closeout discussion. It does this without opening Stage 19
production activation, canonical apply, scheduler wiring, DB writes, or any
other operator execution lane.

The checkpoint focuses on the existing export workspace because that is where
the planner already assembles:

- the Markdown operator pack,
- the JSON review snapshot,
- the CSV planned-sequence extract,
- the closeout-readiness surface,
- the provenance and warehouse review posture.

## Delivered Surface

Stage 22C adds a dedicated operator-review and audit section to the export
workspace. That section makes three things easier to inspect together:

- review focus items that still need human attention;
- sanitized references such as source-run key, artifact basename, and warehouse
  posture;
- export safeguards and section-presence checks that prove the artifact pack
  stays read-only and review-oriented.

## Boundaries Preserved

- Read-only only.
- No operator commands are run.
- No DB writes are performed.
- No canonical apply or rebaseline is triggered.
- No scheduler/service activation is introduced.
- Export references remain informational review aids, not planner authority.
- Private paths, secrets, runtime source files, and operator artifact JSON stay
  excluded from the exported pack.

## Implementation Notes

- `frontend-v2/src/features/system-detail/simulation-preview/exportArtifacts.ts`
  now builds an explicit `operator_review` section for Markdown and JSON
  outputs, with:
  - focus items;
  - safeguards;
  - section coverage;
  - sanitized references.

- `frontend-v2/src/features/system-detail/simulation-preview/ExportReadinessWorkspaceView.tsx`
  now renders an `Operator review and audit` panel alongside closeout
  readiness and the existing export blocks.

- The new surface remains derived from existing read-only planner, provenance,
  and observed-evidence inputs.

## Acceptance

Stage 22C is complete when:

- operator-review artifacts are easier to inspect than the raw export textareas
  alone;
- source-run and artifact references stay sanitized;
- export safeguards remain explicit in the UI and exported pack;
- the exported pack keeps planned, projected, observed, inferred, warehouse,
  guardrails, and operator-review sections separate;
- no runtime artifact becomes authority;
- all deferred Stage 19 boundaries remain false.
