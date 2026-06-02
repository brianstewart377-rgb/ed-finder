# Stage 19A - Warehouse Artifact Taxonomy and Chunked Roadmap

## Purpose

Stage 19A defines the artifact taxonomy and chunked roadmap for broadening the
offline enrichment warehouse after the Stage 18J-Q station reconciliation path.

This stage is documentation and planning only. It does not run production
commands, connect to production databases, run imports, run reconciliation, run
station-type dry-run, run canonical apply, implement scheduler wiring, start
Stage 18J-P, or start Stage 18K.

## Artifact Families

Warehouse artifacts must stay split by domain and lifecycle step so review can
advance in small, auditable chunks. A station artifact must not silently become
a body, market, colonisation, or canonical-write artifact.

| Family | Domain scope | Purpose | Write authority |
|---|---|---|---|
| Stations | Station snapshot and staged station rows | Stage, reconcile, compact, and review station evidence such as station type and station body name. | Warehouse staging only until a separately approved canonical station write plan exists. |
| Bodies | Body snapshot and staged body rows | Stage and reconcile body names, body identifiers, body classes, landability, terraformability, and scan-value evidence. | Warehouse staging/report-only. |
| Rings | Ring arrays and staged ring rows | Preserve source-only ring evidence, trusted ring matches, and unknown-not-false ring semantics. | Warehouse staging/report-only. |
| Station/body links | Association evidence between stations and bodies | Review confirmed, inferred/verify, ambiguous, unresolved, and missing association evidence. | Report-only until a dedicated canonical link write design is approved. |
| Markets | Market and commodity source evidence | Inventory source shape, freshness, and future market staging without changing planner economics. | Warehouse staging/report-only. |
| Services | Station service and facility source evidence | Inventory services separately from station identity and market evidence. | Warehouse staging/report-only. |
| Economies | Economy/source classification evidence | Preserve economy observations and conflicts as evidence without changing scoring or planner mechanics. | Warehouse staging/report-only. |
| Colonisation | Construction, colonisation, and related system evidence | Track colonisation/construction source records and review signals separately from canonical system truth. | Warehouse staging/report-only. |
| Freshness | Source age, source update coverage, and stale/undated signals | Explain whether evidence is current enough to review, without wall-clock write decisions. | Status/report-only. |
| Coverage | Source, warehouse, and domain completeness reports | Show what evidence exists, what is absent, and what remains unknown. | Status/report-only. |
| Analytics | Confidence/risk, mission-density, and colonisation signals | Summarize review signals from staged evidence without mutating planner state. | Report-only. |
| Future write plans | Narrow canonical write candidates after explicit review | Carry pre-images, counts, approvals, rollback expectations, and field/table limits. | Manual apply only after separate approval. |

## Naming Pattern

Use domain-qualified artifact names. The `<domain>` token should be stable and
short, for example `stations`, `bodies`, `rings`, `station_body_links`,
`markets`, `services`, `economies`, `colonisation`, `freshness`, `coverage`,
`analytics`, or a narrower approved domain.

| Pattern | Meaning |
|---|---|
| `warehouse_<domain>_load_<timestamp>.json` | Loader output for one domain, source, and run. |
| `enrichment_staging_reconciliation_<domain>_<timestamp>.json` | Read-only reconciliation artifact for one domain. |
| `reconciliation_compact_summary_<domain>_<timestamp>.json` | Compact summary derived from an existing reconciliation artifact. |
| `warehouse_<domain>_freshness_status_<timestamp>.json` | Freshness/source-age status for one domain. |
| `warehouse_operator_status_<timestamp>.json` | Operator-facing aggregate status assembled from reviewed artifacts. |
| `canonical_write_plan_<domain>_<timestamp>.json` | Future manual write-plan candidate packet for one explicitly approved domain. |

Timestamps should be UTC and sortable, normally `YYYYMMDDTHHMMSSZ`. Artifacts
created from production evidence stay outside git by default. Committed
examples must be synthetic or explicitly sanitized.

## Chunking Rules

Every domain follows the same order. Do not skip ahead because a later step has
a familiar command name from a different domain.

1. Source inventory before load.
2. Load before reconciliation.
3. Reconciliation before compact summary.
4. Compact summary before dry-run.
5. Dry-run before approval packet.
6. Approval packet before apply.
7. Apply manual only.
8. Scheduler never runs canonical apply.

Additional rules:

- Each chunk names its domain, source, artifact basename, expected schema, and
  explicit non-goals.
- Each load summary must keep `canonical_writes_planned = 0`.
- Reconciliation remains read-only/report-only and must not create a write
  plan by implication.
- Compact summaries are review aids and default to non-git production handling.
- Dry-runs are not approvals.
- Approval packets must name exact candidate count, table, field, source scope,
  rollback/pre-image expectations, max row count, operator, and stop
  conditions.
- Any canonical apply must be a separate manual command with explicit approval.
- Scheduled jobs may refresh warehouse artifacts only after a disabled-by-
  default scheduler design lands; they must not apply canonical writes.

## Stage 18J Continuation

Stage 18J remains a narrow station-type path. It must continue separately from
the broader Stage 19 warehouse roadmap.

1. **Q8 compact station reconciliation summary**: generate an offline compact
   summary from the valid station reconciliation artifact. Do not commit
   production output.
2. **Q9 compact summary review / station-type dry-run readiness**: review the
   compact station summary, decide whether station-type dry-run is ready, and
   keep Stage 18J-P blocked if counts, blockers, or risk classes are not
   understood.
3. **18J-P retry station-type production dry-run only**: generate only the
   station-type production dry-run from reviewed reconciliation evidence. Do
   not apply.
4. **18J-P2 dry-run review packet**: review dry-run candidates, pre-images,
   row counts, table/field scope, and stop conditions.
5. **18J-P3 tiny apply approval packet**: prepare a tiny manually approved
   apply packet if the dry-run review is boring and bounded.
6. **18J-P4 tiny apply only if explicitly approved**: run a manual tiny apply
   only after explicit approval. Scheduler never runs this apply.

Stage 18K remains untouched until a separate prompt starts it. Stage 19 does
not broaden canonical apply authority.

## Stage 19 Roadmap

Stage 19 expands warehouse observability and coverage in chunks. Each stage is
expected to preserve report-only boundaries unless it explicitly says otherwise.

| Stage | Name | Scope |
|---|---|---|
| 19A | Taxonomy and chunked roadmap | Define artifact families, naming, ordering, and Stage 18J/19 sequencing. |
| 19B | Freshness/scheduler design | Design freshness status and disabled-by-default scheduler boundaries; no cron wiring. |
| 19C | Source inventory | Inventory available source files, domains, shapes, retention needs, and review risks. |
| 19D | Body source shape inspection | Inspect body source shapes with synthetic/local evidence only and define loader contract. |
| 19E | Body warehouse staging loader | Implement body staging loader changes after source-shape inspection. |
| 19F | Body load/reconciliation/summary | Plan and review body load, read-only reconciliation, and compact summary chunks. |
| 19G | Ring source shape inspection | Inspect ring source arrays and trusted/unknown semantics before loader changes. |
| 19H | Ring warehouse staging loader | Implement ring staging loader changes after source-shape inspection. |
| 19I | Ring load/reconciliation/summary | Plan and review ring load, read-only reconciliation, and compact summary chunks. |
| 19J | Station/body association evidence | Broaden association evidence reporting without creating canonical link writes. |
| 19K | Market/services/economy inventory | Inventory source shapes and authority boundaries for market, service, and economy evidence. |
| 19L | Market/services warehouse staging | Stage market/service/economy evidence as warehouse/report-only data. |
| 19M | Colonisation/construction evidence inventory | Inventory colonisation and construction source evidence before staging. |
| 19N | Colonisation/construction warehouse staging | Stage colonisation/construction evidence as warehouse/report-only data. |
| 19O | Dashboard coverage/freshness v2 | Improve operator dashboard coverage and freshness views from reviewed artifacts. |
| 19P | Retention/cleanup policy | Define retention, cleanup, compression, checksums, and artifact storage rules. |
| 19Q | Scheduled warehouse dry-run jobs disabled by default | Define dry-run refresh jobs that are off unless explicitly enabled. |
| 19R | Maintenance-container scheduler wiring disabled by default | Wire scheduler mechanics in a maintenance container, still disabled by default. |
| 19S | Operator-controlled scheduled refresh pilot | Pilot operator-controlled scheduled warehouse refreshes with no canonical apply. |
| 19T | Full warehouse coverage report v2 | Produce a cross-domain coverage/freshness/report-only status model from reviewed artifacts. |

## Non-Goals

Stage 19A does not authorize:

- production commands,
- production DB access,
- imports,
- reconciliation,
- station-type dry-run,
- production summary generation,
- canonical write plans,
- canonical apply,
- cron or scheduler wiring,
- Stage 18J-P,
- Stage 18K.

## Final Recommendation

Use this taxonomy before opening any broader warehouse stage. Keep each domain
artifact family separate, advance through the chunking rules in order, and keep
canonical apply manual-only behind explicit approval. Stage 18J station-type
work should finish its compact-summary and dry-run review sequence before any
tiny apply is considered; Stage 19 should broaden warehouse evidence without
quietly starting Stage 18K or scheduler-driven writes.

## Stage 19A.1 Follow-Up

Stage 19A.1 adds operator path guardrails for this taxonomy. The key rule is
that Codex/local repo work and Hetzner operator work are separate command
contexts:

- Codex/local: edit scripts and docs, run local tests, open PRs.
- Hetzner operator shell: run `/opt/ed-finder`, `/var/lib/ed-finder`, Docker
  Compose production service checks, production artifact reads, and
  operator-approved production commands.

Stage 19A.1 adds `scripts/operator/require_hetzner_operator_env.sh` and
`scripts/operator/stage18j_run_compact_summary.sh`. Server-only scripts should
call the shared guard and fail fast outside the expected Hetzner host/path.
This does not run production commands from Codex, touch production DBs, run
imports, run reconciliation, run station-type dry-run, run apply, implement
scheduler wiring, start Stage 18J-P, or start Stage 18K.
