# Stage 19AQ - Operator cockpit UI closeout

## Summary

Stage 19AQ adds a minimal read-only operator/admin cockpit UI for Data Warehouse Utopia.

The cockpit is available at the frontend `#operator` route and consumes the Stage 19AP read-only operator visibility endpoints:

- `GET /api/operator/safety-gates`;
- `GET /api/operator/source-runs`;
- `GET /api/operator/source-runs/{source_run_key}`;
- `GET /api/operator/diagnostic-staging-rows`.

## Panels

- Safety Gates panel with safe/not-safe state, blockers, latest source run key, notes, and explicit scheduler/canonical-apply warnings.
- Recent Source Runs table with source, domain, status, timestamps, row counts, artifact/hash state, bridge state, trigger context, and short git SHA.
- Selected Source Run detail panel with redacted source/artifact paths, artifact summary, bridge summary, staging impact summary, validation warnings, and operator notes.
- Diagnostic Rows panel showing diagnostic-only staging rows without raw payloads.

## Safety boundary

- Read-only UI only.
- No production DB access.
- No imports.
- No migrations.
- No scheduler/timer enablement.
- No staging writes.
- No canonical writes.
- No canonical apply.
- No import, scheduler, canonical write, or canonical apply buttons/actions added.

## Next stage

The next recommended stage is Stage 19AR: a bounded 25-row staging pilot using the cockpit, only if safety gates remain green.
