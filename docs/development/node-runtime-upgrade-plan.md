# Node runtime upgrade plan

**Audit date:** 2026-09-21

**Audited baseline:** `89408bf12c0035baff0fd6d70cb1159e13b56092`

**Implementation branch:** `chore/node-22-upgrade`

**Scope:** local Node tooling alignment and validation; production actions below
require separate owner approval and were not performed.

## Confirmed target and conflicts

The [V3 application stack decision](v3-application-stack-decision.md), dated
2026-09-04 and marked current technology authority, locks **Node.js 24 LTS**
as the tooling runtime. It selects a major, not an exact patch. The project
engine range is `>=24 <25`; Node 22 is not the target despite the branch name.

The task described production as running Node 20. At the audited baseline,
all active application/CI/container runtime pins were already on Node 24.
The stack decision specifies static SvelteKit output with no Node application
server in production: `apps/web/Dockerfile` uses Node only to build assets and
nginx to serve them. Production Node 20 is therefore an unverified discrepancy
with the documented application topology, not evidence for changing a host
runtime. No production host or database was accessed. The owner must reconcile
that report against governed inventory and durable accepted-release receipts;
see [infrastructure status](../operations/infrastructure-status.md).

## Complete pin inventory at the audited baseline

Paths below are repository-relative; line numbers describe the baseline.
Search covered tracked files, hidden workflows, manifests, version-manager
files, Dockerfiles, Compose, deploy/operator/Octopus configuration, scripts,
tests and documentation.

| File / location | Before | Disposition |
|---|---|---|
| `apps/web/package.json:8` | `engines.node: >=24 <25` | Already correct; unchanged |
| Root `package.json` | Absent | No root package/workspace introduced |
| `packages/api-client/package.json`, `packages/planner-core/package.json`, `frontend/package.json` | No `engines.node` | No runtime pin to bump |
| `.nvmrc`, `.node-version` anywhere | Absent | Add both at repository root with `24` for local version managers |
| `.github/workflows/ci.yml:393` | `node-version: "24"` (Svelte checks) | Unchanged |
| `.github/workflows/ci.yml:509` | `node-version: "24"` (OpenAPI generation) | Unchanged |
| `.github/workflows/coverage.yml:139` | `node-version: "24"` | Unchanged |
| `.github/workflows/cypress-parity.yml:153` | `node-version: "24"` | Unchanged |
| `.github/workflows/review-lab.yml:41` | `node-version: "24"` | Unchanged |
| All five `actions/setup-node` uses above | SHA `820762786026740c76f36085b0efc47a31fe5020` (`v7.0.0`) | Preserve action pins; action versions are distinct from the selected project Node version |
| `.github/workflows/cypress-parity.yml:165` | `actions/cache` v6.1.0, documented Node 24 action runtime | Preserve SHA `55cc8345863c7cc4c66a329aec7e433d2d1c52a9` |
| `apps/web/Dockerfile:2` | `node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf` | Only Node base image; already correct, preserve immutable digest |
| Other `Dockerfile*`, root/`deploy/` Compose, deployment and Octopus-related files | No Node version pin | No edit; release workflow builds the web Dockerfile above |
| `frontend/scripts/bench-journal-parse.mjs:83` | esbuild output target `node20` | Align to `node24`; this is a syntax target in retained historical tooling, not an active runtime selector |

There were **zero active runtime pins on 20 or 22**. Existing engine, CI and
container pins require no numeric bump. The one Node 20 build target above is
aligned without making the retired React benchmark a validation/release gate.

Documentation inventory:

| File / baseline lines | Statement and disposition |
|---|---|
| `docs/development/v3-application-stack-decision.md:54-57` | Static delivery, Node.js 24 LTS, pnpm 11; authority retained |
| `CLAUDE.md:152,159` | Node 24 / pnpm 11.25.0; retained |
| `CHANGES.md:57,73` | Node 24 history; retained |
| `docs/development/windows-dev-environment.md:45` | Node 24 / Corepack; retained |
| `docs/development/local-review-test-environment.md:124` | CI Node 24 / pinned pnpm 11; retained |
| `docs/development/evidence/v2-account-ui/README.md:23` | Local Node 24 / pnpm 11.25.0 validation receipt; retained |
| `docs/superpowers/plans/2026-09-15-frontier-capi-identity-journal-import.md:9,14` | Node 24 / pnpm 11.25.0; retained |
| `docs/superpowers/plans/2026-08-08-pr446-frontend-dependency-upgrade.md:17,63,275,289` | Historical Node 20/22 instructions/results; add explicit historical status and link to current Node 24 authority |
| `docs/superpowers/specs/2026-08-08-pr446-frontend-dependency-upgrade-design.md:14-16` | Historical CI Node 20 / dependency minimum 22.22; add current-authority note, preserve facts |
| `frontend/.gitignore:9` | Historical explanation of Node 20/Vite sidecars, not setup guidance; retained |

The active `@types/node` package is already `24.10.0`. Retired frontend type
packages (`^26.1.2`, including historical 22-to-26 upgrade notes) and third-party
`engines.node` ranges inside lockfiles describe dependencies, not project runtime
pins. Rewriting those to 24 would falsify upstream metadata. Existing Node 24
assertions in repository contract tests remain valid.

## pnpm compatibility

Keep `pnpm@11.25.0` in `apps/web/package.json`, the Dockerfile and CI. Published
[pnpm 11.25.0 package metadata](https://registry.npmjs.org/pnpm/11.25.0) reports
`engines.node: >=22.13`, verified with:

```text
npm view pnpm@11.25.0 version engines --json --registry=https://registry.npmjs.org
```

Node 24 satisfies this requirement; Node 20 does not. The official
[pnpm compatibility table](https://pnpm.io/installation#compatibility) also lists
Node 24 support for pnpm 11. No package-manager or dependency upgrade is needed.

## Files changed

- `.nvmrc`: select Node major 24 for nvm-compatible local tooling.
- `.node-version`: select the same major for other local version managers.
- `README.md`: state Node 24/pnpm 11.25.0 prerequisites and link this plan.
- `frontend/scripts/bench-journal-parse.mjs`: align retained esbuild syntax target
  from `node20` to `node24` only.
- `docs/superpowers/plans/2026-08-08-pr446-frontend-dependency-upgrade.md`: label
  old runtime instructions historical and link the current authority.
- `docs/superpowers/specs/2026-08-08-pr446-frontend-dependency-upgrade-design.md`:
  distinguish historical CI runtime evidence from the current target.
- `docs/development/node-runtime-upgrade-plan.md`: this inventory, validation
  record and owner-gated migration/rollback plan.

Already-correct Dockerfile, CI and package-engine pins remain unchanged. No
schema, application dependency, package-manager, or lockfile change is intended.

## Local validation

Environment: Windows x64, Node `v24.15.0`, pnpm `11.25.0`. The strict repository
state check (`make state-check PYTHON=python`, CPython 3.14.4) passed on the
requested branch before edits.

Required commands were run from `apps/web`:

```text
pnpm install --frozen-lockfile
pnpm check
pnpm build
pnpm test
```

| Command | Result |
|---|---|
| `pnpm install --frozen-lockfile` | Passed; 513 packages installed with pnpm 11.25.0; lockfile unchanged; no network/install blocker |
| `pnpm check` | Passed; zero errors and zero warnings |
| `pnpm build` | Passed; adapter-static wrote `build/`; Rolldown emitted plugin timing advisories only |
| `pnpm test` | Passed; 38 test files, 314 tests |

The version-selector/engine/CI/Docker consistency check and
`node --check frontend/scripts/bench-journal-parse.mjs` also passed. The retained
React app/benchmark was not built or executed. Linux/Alpine release-image and
protected browser validation were not run locally and remain required before
any production promotion.

## Owner-gated production procedure (not performed)

The current authority is the
[V3 production application release runbook](../operations/v3-production-application-release.md),
`deploy/v3-production/target-authority.json`, and the protected workflows it
names. This plan grants no production authorization.

1. A trusted writer publishes the local branch and opens the review. Complete
   the [PR acceptance policy](pull-request-acceptance-policy.md), including
   required CI and reviewer dispositions for the exact head. An authorized
   owner arranges merge; this coding task does not push or change `main`.
2. The owner separately authorizes governed `inventory` through
   `.github/workflows/v3-production-application-deploy.yml`, from exact current
   `main`, confirming the literal target `ed-finder-prod/nb79a3d.mevnode.com`.
   Review durable accepted-release identity, topology and schema/rollback
   evidence, and resolve the reported Node 20 discrepancy. Do not install Node
   on production or revive legacy Octopus/root-Compose deployment procedures.
3. Require passing Node 24 Linux CI, Cypress Product E2E, Review Lab and actual
   release-image validation. No migration is introduced by this change. If
   unrelated existing schema prerequisites are unmet, stop for their separately
   reviewed migration process rather than applying them within this upgrade.
4. Use `.github/workflows/v3-application-release.yml` to build immutable images
   off-host with `source_sha` equal to the exact current `main` SHA. Supply
   reviewed schema compatibility, evidence, any compatible migration-set
   identities, and rollback eligibility. Retain the successful run ID,
   manifest/checksum, image digests and OCI revision. Production must not run
   builds, dependency installs/resolution or `git pull`.
5. Separately authorize `operation=preflight`, `deployment_mode=upgrade`, the
   successful `release_run_id` and literal target confirmation in the production
   workflow. Review the receipt and existing protected-environment gates. If
   `main` has advanced, re-establish an accepted release of the exact current
   head; do not bypass the SHA check.
6. Only after owner approval, dispatch `operation=promote` with the same reviewed
   inputs. The existing deployer stages the inactive application slot, validates
   it, switches the application origin and verifies origin/public health,
   frontend and API build identity, database connectivity, and existing smoke
   routes (`/`, `/api/health`, `/openapi.json`, `/api/v1/auth/session`). Cypress
   supplies representative navigation coverage. Preserve the public edge and
   protected services. Retain
   the immutable promotion receipt and updated `current.json`, and review the
   existing post-promotion health evidence.

## Rollback

Before promotion, identify the checksum-bound previously accepted manifest and
prove its compatibility with the actual current schema. Retain its images and
the durable receipt; absent proof means stop, not assume rollback eligibility.

The governed deployer's failure-time rollback revalidates the previous release
against a fresh schema snapshot and restores its application slot with
`--pull never`. It does not roll back the database. The production workflow has
only `inventory`, `preflight` and `promote`; it has **no manual rollback action**.
For a regression discovered after acceptance, the owner must approve a supported
recovery procedure or a reviewed revert followed by a newly built, accepted
current-main release. An arbitrary old release run cannot bypass the exact-main
gate. Do not improvise host commands, database restores or a Node 20 downgrade;
Node 20 is incompatible with the pinned pnpm 11 toolchain.

Local rollback of this change is a reviewed revert of its branch commit.
Historical application rollback evidence remains governed by the runbook.

## Risks and remaining release gates

- **Native modules:** the frozen graph includes Rolldown, Tailwind Oxide and
  Lightning CSS platform binaries. Windows x64 validation does not establish
  Linux glibc/Alpine musl compatibility. Use fresh platform-appropriate installs
  and the actual `linux/amd64` release-image build; do not reuse `node_modules`
  across Node majors or platforms.
- **CI/base images:** `ubuntu-latest` and setup-node major `24` can resolve newer
  runner/Node patches while the Alpine builder is digest-pinned. Record resolved
  versions in release evidence and retain the image digest. Any future digest
  refresh is a separately reviewed dependency change, not an unpinned tag swap.
- **Browser tooling:** Cypress needs platform/browser dependencies. Its binary
  is intentionally skipped in the static Docker build via
  `CYPRESS_INSTALL_BINARY=0`; protected Cypress CI is still required.
- **Installation policy:** preserve the frozen lock and existing pnpm
  `allowBuilds`, trust and release-age policies. Native-module problems do not
  justify arbitrary lifecycle-script approval or unrelated dependency upgrades.
- **Production discrepancy/schema:** source pins alone cannot prove a deployed
  build's tooling provenance. Owner inventory/receipts must resolve that gap;
  unrelated schema requirements and rollback compatibility can block promotion.
