# Always-On Review Lab on the Contabo Box — Design

**Date:** 2026-10-02
**Status:** Approved (brainstorming) — pending implementation plan

## Goal

Stand up a persistent, browsable ED-Finder Review Lab on the existing Contabo
host (the Codex runner box) so PR/review journeys can be exercised in a browser
without depending on a developer laptop's Docker. This avoids provisioning a
third server: backups already live on the Hetzner Storage Box (cheap object
storage, left untouched), and the Codex runners already run on Contabo — the
lab becomes a second, resource-capped tenant on that same box.

## Context

- **Prod:** `ed-finder-prod` / `nb79a3d.mevnode.com`, PostgreSQL 18. Not involved here.
- **Backups:** Hetzner Storage Box (pgBackRest offsite). Not a compute server; **not changed by this work**.
- **Contabo host:** `vmi3542235` / `vmi3542235.contaboserver.net` — 8 logical CPUs,
  ~24 GB RAM, ~250 GB free root disk. Runs exactly three self-hosted Codex
  runner services. Per `docs/operations/infrastructure-status.md` it is **not
  production**, holds **no production credentials/data/routing**, and currently
  has **no container runtime, Compose, containers, networks, or volumes**.
- **Existing Review Lab stack** (`docker-compose.review.yml`): `review-postgres`
  (PG18-alpine, synthetic `edfinder_local_review` DB), `review-redis`,
  `review-api` (built from `apps/api/Dockerfile`, runs `review_main:app`, bound
  to `127.0.0.1:8001`). No web/frontend service; built for CI, not remote
  browsing. Seeded by `scripts/dev/review_environment_seed.py`.
- **V3 Finder seed** (`scripts/dev/seed_cypress_v3_generation.py`, this branch):
  publishes a real V3 derived generation so the F3-repointed `/api/local/search`
  returns results instead of 404.
- **Governance:** `docs/operations/infrastructure-status.md` (Contabo boundary),
  `CLAUDE.md` (Codex execution context must never hold production credentials;
  `docker-compose.review.yml` must stay isolated from production credentials,
  URLs, and data). The Contabo host is also the designated first V3
  live-checkpoint target (scoped 2 CPU / 2 GiB) — the lab must leave headroom.

## Decisions

1. **Shape:** an **always-on Review Lab** (persistent, browsable), not an
   ephemeral per-run env and not a bare shared database.
2. **Reachability:** **SSH tunnel only.** All services stay bound to the box's
   loopback; the only way in is authenticated SSH (`ssh -L`). No new public
   surface on a host that runs Codex runners.
3. **Structure:** **compose override (Approach A).** Keep
   `docker-compose.review.yml` untouched (so the CI `Review Lab` gate is
   unaffected) and add a `docker-compose.lab.yml` override that layers on a web
   service, resource limits, restart policy, and loopback bindings. CI uses only
   the base file; the lab uses base + override.
4. **Resource budget:** the lab is capped at **≤ 3 CPU / 8 GB total** across its
   services so the three Codex runners (and the future checkpoint namespace)
   keep headroom on the 8-core / 24 GB box.
5. **Host-side execution is the user's.** This repo change produces reviewable
   artifacts only; installing Docker, cloning, `compose up`, and the SSH tunnel
   run on the box by the user (coding sessions do not mutate the governed host).

## Architecture

### Runtime & footprint
- One-time host prep (user, sudo): install Docker Engine + the compose plugin.
- The lab runs `docker compose -f docker-compose.review.yml -f docker-compose.lab.yml up -d`.
- Per-service `deploy.resources.limits` keep the lab total at ≤ 3 CPU / 8 GB.
- Postgres uses a named volume; images/build cache are pruned on a schedule
  (documented cron/`docker system prune` guidance) so the lab can't fill the disk.
- A small `systemd` unit brings the stack up on boot (always-on), depending on
  `docker.service`.

### Compose topology (the `docker-compose.lab.yml` override adds)
- **web** service: builds the Svelte bundle and serves it via Vite preview
  (mirroring `cypress-parity.yml`) on `127.0.0.1:4174`, `VITE_DEV_API_TARGET`
  pointed at the lab API. `restart: unless-stopped`, resource-capped.
- **Loopback port bindings:** `127.0.0.1:4174` (web) and `127.0.0.1:8001` (api);
  Postgres and Redis stay internal to the `edfinder-review-network` only.
- `restart: unless-stopped` added to `review-postgres`, `review-redis`,
  `review-api`.
- CORS on the API extended to allow the tunneled `http://localhost:4174` origin.

Running shape over the tunnel: `localhost:4174` (web) → `localhost:8001` (api)
→ internal Postgres/Redis. Nothing listens off-loopback.

### Data & a working Finder
- Synthetic Review Lab data via `scripts/dev/review_environment_seed.py` (as today).
- **Plus** a published V3 generation via `scripts/dev/seed_cypress_v3_generation.py`
  so the F3 Finder returns real results in the browser (not 404). The seed is
  idempotent and applies only the V3 migrations missing from the lab DB.
- `scripts/dev/lab_refresh.sh`: checkout a chosen ref (`main` or a PR branch) →
  rebuild images → re-seed synthetic + V3 generation → `compose up -d`. This is
  how the lab is updated to new code on demand.

### Security & trust boundary
- **Synthetic data + non-prod credentials only** (`review_user`, Review Lab DB).
  No production credentials, URLs, or data ever enter the lab — preserving the
  CLAUDE.md Codex-credential boundary and the box's "not production" status.
- **Loopback + SSH tunnel:** no new listening ports; entry is authenticated SSH.
- **Isolation from the runners:** the lab has its own Docker network and volumes;
  the Codex runners stay as host services. Neither can read the other's secrets,
  and the CPU/memory caps prevent a runaway lab from starving a Codex job (or
  vice versa).
- **Backups untouched:** the Storage Box is not involved; the lab holds no data
  that needs backing up (fully rebuildable from code + seeds).

## Deliverables (committed to the repo, reviewed)

- `docker-compose.lab.yml` — the override (web service, loopback bindings,
  resource limits, restart policy, CORS for the tunneled origin).
- A web service definition (Dockerfile or build stanza) that builds + serves the
  Svelte bundle via Vite preview.
- `deploy/contabo-review-lab/edfinder-review-lab.service` — systemd unit for boot.
- `scripts/dev/lab_refresh.sh` — checkout-ref → build → seed → up.
- `docs/operations/contabo-review-lab.md` — copy-pasteable host runbook:
  Docker install, clone, first bring-up, seeding, the `ssh -L` tunnel command,
  update/refresh, prune/disk hygiene, and teardown.

## Host runbook outline (user executes)

1. Install Docker Engine + compose plugin (sudo, one-time).
2. Clone the repo to a lab working directory on the box.
3. `docker compose -f docker-compose.review.yml -f docker-compose.lab.yml build`.
4. Bring up + seed via `scripts/dev/lab_refresh.sh <ref>`.
5. Enable the systemd unit for always-on + boot survival.
6. From the laptop: `ssh -L 4174:localhost:4174 -L 8001:localhost:8001 <box>`,
   then browse `http://localhost:4174`.
7. Maintenance: `lab_refresh.sh` to update; prune guidance for disk.

## Risks & mitigations

- **Disk fill from images/PG growth** → named volume + scheduled prune + capped
  retention; documented in the runbook.
- **Resource contention with runners** → hard CPU/memory caps (≤ 3 CPU / 8 GB).
- **Accidental public exposure** → loopback-only bindings enforced in the
  override; runbook never opens a firewall port.
- **CI Review Lab gate regression** → the base `docker-compose.review.yml` is
  not modified; CI uses only the base file.
- **Governed-host provisioning** → all host mutation is the user's via the
  runbook; no coding-session SSH/credential use.

## Success criteria

- From the laptop, over an SSH tunnel, `http://localhost:4174` serves the Review
  Lab web app and the F3 Finder returns real results (published V3 generation).
- The stack survives a box reboot (systemd) and a laptop sleep/disconnect.
- The three Codex runners keep running with headroom throughout.
- No new public ports; no production credentials/data on the box.
- The CI `Review Lab` workflow is unchanged and still green.

## Out of scope

- Any change to backups / the Storage Box.
- Any production (mevnode) change or the V3 live-checkpoint deployment.
- Public exposure, TLS, or multi-user auth (SSH tunnel only).
