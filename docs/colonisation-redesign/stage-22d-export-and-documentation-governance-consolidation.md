# Stage 22D - Export And Documentation Governance Consolidation

## Purpose

Stage 22D consolidates how read-only export artifacts describe their own
governance posture. The goal is to make current-state and historical review
surfaces easier to trust without allowing any export, snapshot, or operator
artifact to become execution authority.

## Delivered Surface

Stage 22D adds an explicit documentation-governance layer to the export
workspace and exported pack:

- a governance section in Markdown and JSON exports;
- a dedicated `Documentation governance` panel in the export workspace;
- explicit exclusions for private paths, secrets, runtime source files, and
  operator artifact JSON;
- explicit authority-scope language stating that the export pack is review
  context only;
- explicit documentation references that point reviewers back to the committed
  roadmap and governance records.

## Governance Rules Preserved

- Export packs are review artifacts, not planner authority.
- Historical closeouts stay review context only.
- Current authority remains the committed Stage 22 roadmap and state authority
  file.
- Private paths, secrets, admin tokens, DSNs, runtime source files, and
  operator artifact JSON stay excluded from exported pack content.
- No Stage 19 activation, DB writes, operator commands, scheduler wiring, or
  canonical apply are authorized by these surfaces.

## Implementation Notes

- `frontend/src/features/system-detail/simulation-preview/exportArtifacts.ts`
  now includes a `governance` section in exported Markdown and JSON outputs.

- `frontend/src/features/system-detail/simulation-preview/ExportReadinessWorkspaceView.tsx`
  now renders a `Documentation governance` panel with:
  - authority scope;
  - exclusions;
  - historical-status language;
  - committed document references.

## Acceptance

Stage 22D is complete when:

- export-governance rules are visible in both the export workspace and exported
  pack;
- the pack explicitly says it is not planner authority;
- exclusions remain visible and testable;
- historical review context is easier to navigate without competing with current
  control documents;
- all deferred Stage 19 boundaries remain false.

