# R1 canonical body evidence preflight

## Repository baseline

- Original repository HEAD before R1 schema work: `565e105e09e0670bc11cfc777f8e0b067b4145dc`
- Working branch for this task: `work/r1-canonical-body-evidence`

## Migration baseline

- Existing numbered migration baseline before R1 work: `sql/029_create_source_runs.sql`
- New additive R1 migration: `sql/030_r1_canonical_body_evidence.sql`

## Backup / snapshot evidence

No repository-committed database dump is present in this checkout.

Existing backup/snapshot readiness evidence:
- `docs/colonisation-redesign/stage-18j-p6-external-identity-migration-production-readiness.md`
- `docs/operations/enrichment-warehouse-runbook.md`

Those records already require a backup/snapshot or explicit schema-only risk
acceptance before production schema application. This branch does not deploy or
apply production schema.

## Frozen forensic surfaces

Legacy tables kept read-only as forensic evidence:
- `ratings`
- legacy `ratings.score_*`
- legacy `ratings.*_count`
- legacy `ratings.economy_suggestion`
- legacy `ratings.score_breakdown`
- legacy `ratings.rating_version`

Current v4 evidence kept read-only:
- `system_archetype_scores`
- `system_archetype_traits`
- `mv_archetype_rankings`

Raw/source-side tables R1 is allowed to read:
- `systems`
- `bodies`
- `body_rings`
- `body_scan_facts`

## Boundary

This branch adds:
- a canonical body semantics contract
- additive R1 tables
- a standalone R1 classifier / dry-run path
- bounded golden-corpus fixtures and tests

This branch does not:
- deploy
- restart services
- rebuild legacy ratings
- rebuild v4 archetypes
- modify legacy/v4 rows
- overwrite imported raw body/system records
- add player-facing R1 recommendation UI
