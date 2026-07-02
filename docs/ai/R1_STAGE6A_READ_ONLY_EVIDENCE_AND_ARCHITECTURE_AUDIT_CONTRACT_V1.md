# R1 Stage 6A — Read-Only Evidence and Architecture Audit Contract v1

**Status:** Accepted by the owner and merged in PR `#295` at `7a4080363a23a0aefe9b68c795d621164b39c9e8` on 2026-07-02. Stage 6A is active within this contract's scope.

## 1. Purpose

Stage 6A is a discovery-only audit. Its purpose is to establish, without changing the project, what the repository and any later approved read-only database access can genuinely support as evidence.

The audit must answer, in plain and traceable terms:

1. What project, schema, source, and galaxy-data information exists.
2. What its provenance, coverage, freshness, gaps, and limitations are.
3. Which clearly stated research questions that information can support, can only partly support, cannot support, or cannot yet test.
4. Which assumptions need counterexamples, further evidence, or real in-game verification.
5. Which architecture choices could safely support later evidence work without weakening the accepted R1 laboratory boundaries.

This contract authorises evidence and architecture reporting only after it is independently reviewed, accepted by the owner, and merged. It does not authorise product changes or a decision to implement any future architecture.

## 2. Governing boundaries

The Stage 5A non-inference rule and the Stage 5B evidence discipline remain fully in force.

Every conclusion must remain no stronger than its evidence chain:

```text
source record
→ normalized evidence fact
→ named programme requirement or constraint
→ bounded conclusion or stated limitation
```

A raw body count is context, not a quality score, a ranking, a recommendation, or proof of capability. A body that is neutral for one named programme may still matter for a different named programme or constraint.

The audit may describe possibilities, trade-offs, and unanswered questions. It may not silently convert a pattern, correlation, owner preference, or incomplete data set into a game fact or accepted project rule.

## 3. Allowed work after acceptance and merge

### 3.1 Read-only repository inspection

The audit may inspect, without modifying anything:

- the canonical repository branch, Git history, project documents, code, tests, schemas, migrations, configuration, scripts, and existing data-handling paths;
- data-model definitions, source/provenance fields, import or normalization logic, and documented data-refresh processes;
- existing R1 laboratory boundaries and the relationship between the R1 lab and any broader research capability already present in the repository.

Repository claims in the audit report must identify the path, immutable commit or ref, retrieval date, and what the material does and does not establish.

### 3.2 Read-only database inspection, only when safe access is supplied

The database portion may begin only after the owner supplies access that is verified to be read-only. This contract does not authorise placing credentials in the repository, source code, project documents, chat transcripts, or generated reports.

Before inspection begins, the analyst must verify the read-only restriction from the database role or permission record, or by another owner-approved technical check that does not attempt a write, and record the method in the audit's access record.

When such access is supplied, the audit may use bounded read-only queries to inspect:

- available schemas, tables, views, fields, and documented source metadata;
- row counts, date ranges, identifiers, coverage patterns, null or missing-value rates, duplicates, and relationships relevant to later evidence work;
- representative limited samples needed to understand field meaning or source quality;
- aggregate and filtered checks needed to determine whether an explicit research question is testable from the available data.

Database access must remain limited to approved read-only endpoints, approved data tables or views, and read-only metadata or catalog views. The analyst may use bounded read-only `SELECT` queries against those approved data tables or views. It must not use data-modification statements, schema changes, write locks, transactions intended to alter state, imports, exports, bulk extraction, credential changes, stored-procedure changes, scheduled jobs, or database administration actions.

A database-derived audit claim must record the dataset or snapshot identity where available, query date/time, relevant tables or views, the query purpose, any material filters or limits, and the caveats needed to understand what the result does and does not prove. Secrets and connection details must never be recorded.

### 3.3 Durable audit report and recovery checkpoint

After the audit work is complete, Stage 6A may create a durable documentation-only audit report and recovery checkpoint on a dedicated documentation branch. The allowed durable files are exactly:

- `docs/ai/R1_STAGE6A_READ_ONLY_EVIDENCE_AND_ARCHITECTURE_AUDIT_REPORT_V1.md`
- `docs/ai/CURRENT_STAGE.md`

The report must contain the required audit outputs in Section 4. The checkpoint must record the audited repository branch and commit, database access verification and scope where database inspection occurred, report commit, material caveats, and the next safe action. The audit may create the dedicated documentation branch and its pull request only for these two files. It may not merge the report or checkpoint; independent review and separate owner acceptance remain required before any merge.

No report or checkpoint conclusion becomes an accepted project rule, architecture decision, implementation authority, or permission for a later stage.

## 4. Required audit outputs

The Stage 6A report must contain these sections.

1. **Baseline and access record**
   - branch and commit inspected;
   - documents, schemas, repositories, and databases actually available;
   - read-only database-verification method and approved scope, or a statement that no database was inspected;
   - access limits and anything not inspected.

2. **Evidence and data inventory**
   - main entities and fields available;
   - source and provenance information;
   - freshness, coverage, missingness, duplication, and uncertainty risks;
   - distinction between direct facts, derived facts, owner-provided intent, and unknowns.

3. **Question and capability map**
   - research questions the current evidence can answer;
   - questions it can only answer with caveats;
   - questions it cannot answer yet;
   - questions that require external evidence or real in-game verification and therefore remain outside Stage 6A.

4. **Assumption and counterexample register**
   - assumptions worth testing;
   - likely counterexamples or confounders;
   - what evidence would strengthen, weaken, qualify, or falsify each assumption.

5. **Architecture options**
   - a careful extension of the existing R1 laboratory;
   - a separate observed-evidence and programme-definition layer that leaves R1 deterministic and fixture-backed;
   - a controlled wider re-baselining later;
   - the invariants, risks, migration cost, and unanswered questions for each option.

6. **Safe next decision**
   - the smallest documentation-only question that the owner should decide next;
   - an explicit statement that no implementation, fixture, external research, database write, deployment, score, rank, recommendation, or product behaviour has been authorised by the audit report.

## 5. Explicit non-goals

Stage 6A does not authorise:

- edits to code, tests, UI, fixtures, configuration, migrations, data, or any documents, branches, or pull requests except the controlled Stage 6A completion documentation in Section 3.3;
- any database write, schema change, data import, export, deletion, mutation, administration action, or persistent query artifact;
- external web research, external data collection, game scouting, or live runtime dependence;
- a new R1 fixture, Assessment behavior, Plan Fit behavior, ranking, score, best-system claim, recommendation, preference, winner, automatic selection, or planning behavior;
- a conclusion that a system is good, best, sufficient, or neutral without a separately defined programme and a traceable evidence chain;
- selection or implementation of an architecture option.

## 6. Required analyst conduct

The lead analyst must:

- report uncertainty, missingness, contradiction, stale information, and access limitations plainly;
- distinguish fact, inference, owner intent, and open question;
- seek counterexamples and competing explanations rather than only confirming an attractive theory;
- stop and ask the owner before any work that would exceed this contract;
- avoid broad data extraction when a bounded aggregate, sample, or coverage check can answer the immediate question;
- state when an answer needs real in-game verification rather than database evidence.

## 7. Stop conditions

The audit must pause the relevant part of its work and report the limitation when:

- the canonical repository state cannot be identified;
- a required source, schema, or provenance record is absent or contradictory;
- database access is not demonstrably read-only or would require sharing credentials in an unsafe place;
- a query would require bulk extraction, unbounded scanning, an external lookup, or a database action outside the allowed scope;
- a conclusion would require a new programme definition, fixture contract, implementation decision, or owner policy decision.

## 8. Completion boundary

A completed Stage 6A report and its allowed documentation-only checkpoint are evidence and architecture discovery only. They do not accept an architecture, create a future stage, authorise a database connection beyond the supplied read-only scope, or permit any implementation work.

Any next stage requires separate owner authorisation, a written scope, independent review, and the normal acceptance and merge process.
