# Always-On Review Lab on the Contabo Box — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the committed artifacts (compose override, refresh script, systemd unit, host runbook) that let the user run a persistent, browsable, SSH-tunnel-only ED-Finder Review Lab on the existing Contabo box, capped so the Codex runners keep headroom.

**Architecture:** Layer a `docker-compose.lab.yml` override on the untouched `docker-compose.review.yml` (so the CI `Review Lab` gate is unaffected). The override adds an nginx **web** service (the existing `apps/web/Dockerfile`, serving the SPA and proxying `/api` to the api container), resource caps, `restart: unless-stopped`, and loopback host bindings. A `lab_refresh.sh` script checks out a ref, builds, brings the stack up, and seeds synthetic review data (+ the V3 generation once PR #777 lands). A systemd unit makes it survive reboots. The user executes all host-side steps per the runbook; this repo change only produces the artifacts.

**Tech Stack:** Docker Engine + compose plugin, `docker-compose.review.yml` base (PG18-alpine, redis7-alpine, `review_main:app` from `apps/api/Dockerfile`), `apps/web/Dockerfile` (node build → nginx:1.29-alpine, listens 8080, proxies `/api` to `${EDFINDER_API_UPSTREAM}`), `scripts/dev/review_environment_seed.py` (reads `DATABASE_URL`), `scripts/dev/seed_cypress_v3_generation.py` (present only after #777), systemd, bash.

## Global Constraints

- **Branch:** `ops/contabo-review-lab` (off `main`). This is a separate PR from F3 (#777); never pull F3 commits in.
- **Never modify `docker-compose.review.yml`** — the CI `Review Lab` gate consumes it as the base; the lab adds only the override file.
- **Loopback only** — every host port binding is `127.0.0.1:<port>`; the runbook never opens a firewall port. Reachability is SSH tunnel only.
- **Synthetic data + non-prod credentials only** — the lab uses the Review Lab DB/creds (`review_user` / `review_password` / `edfinder_local_review`); no production credentials, URLs, or data ever touch the box. Preserves the CLAUDE.md Codex-credential boundary and the box's "not production" status.
- **Resource cap ≤ 3 CPU / 8 GB total** across lab services, leaving headroom for the 3 Codex runners and the future checkpoint namespace (2 CPU / 2 GiB) on the 8-core / 24 GB box.
- **`BUILD_SHA`** passed to the web image MUST be a 40-char lowercase hex git sha (the Dockerfile hard-fails otherwise).
- **`EDFINDER_API_UPSTREAM`** is `host:port` with no scheme (the nginx template prepends `http://`): use `review-api:8000`.
- **V3 seed is conditional** — `scripts/dev/seed_cypress_v3_generation.py` only exists on `main` after #777 merges. The refresh script runs it only if present, so the lab works today (legacy search path) and auto-seeds V3 once #777 lands.
- Host-side execution (Docker install, clone, `compose up`, tunnel, systemd enable) is the **user's**, via the runbook. No coding session mutates the governed host.

## File structure

- Create `docker-compose.lab.yml` — the override (web service, caps, restart, loopback bindings, CORS).
- Create `scripts/dev/lab_refresh.sh` — checkout ref → build → up → wait-healthy → seed synthetic (+ conditional V3) → smoke check → write `.lab.env`.
- Create `deploy/contabo-review-lab/edfinder-review-lab.service` — systemd unit (boot survival).
- Create `docs/operations/contabo-review-lab.md` — copy-pasteable host runbook.

---

### Task 1: Compose override (`docker-compose.lab.yml`)

**Files:**
- Create: `docker-compose.lab.yml`

**Interfaces:**
- Consumes: the base `docker-compose.review.yml` services `review-postgres`, `review-redis`, `review-api` (network `review`, api command `uvicorn review_main:app ... :8000`, api bound `127.0.0.1:8001:8000`).
- Produces: a `review-web` service on `127.0.0.1:4174:8080`; `up`/`config` work via `docker compose -f docker-compose.review.yml -f docker-compose.lab.yml`.

- [ ] **Step 1: Write the override file**

```yaml
# docker-compose.lab.yml — always-on Review Lab override for the Contabo box.
#
# Usage (always with the base review compose first):
#   BUILD_SHA=$(git rev-parse HEAD) \
#     docker compose -f docker-compose.review.yml -f docker-compose.lab.yml up -d
#
# The base docker-compose.review.yml is NEVER modified: the CI `Review Lab`
# gate consumes it alone. This override only ADDS the web service, resource
# caps, restart policy, loopback bindings, and CORS for the tunneled origin.
services:
  review-postgres:
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 2g

  review-redis:
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512m

  review-api:
    restart: unless-stopped
    environment:
      # The web service proxies /api same-origin, so CORS is mostly moot; these
      # cover direct API access over the tunnel (http://localhost:8001) for
      # debugging. review_main already includes the product search router.
      CORS_ORIGINS: http://localhost:4174,http://127.0.0.1:4174,http://localhost:8001,http://127.0.0.1:8001
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 3g

  review-web:
    build:
      context: .
      dockerfile: apps/web/Dockerfile
      args:
        BUILD_SHA: ${BUILD_SHA:?set BUILD_SHA to a 40-char git sha (scripts/dev/lab_refresh.sh does this)}
    depends_on:
      review-api:
        condition: service_started
    environment:
      EDFINDER_API_UPSTREAM: review-api:8000
    ports:
      - "127.0.0.1:4174:8080"
    networks:
      - review
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512m
```

- [ ] **Step 2: Validate the merged compose config**

Run: `BUILD_SHA=$(git rev-parse HEAD) docker compose -f docker-compose.review.yml -f docker-compose.lab.yml config >/dev/null && echo OK`
Expected: `OK` (no YAML/interpolation errors; the `review-web` service and `127.0.0.1:4174:8080` binding appear if you drop the `>/dev/null`).

- [ ] **Step 3: Confirm the base file is untouched**

Run: `git diff --name-only` → must list only `docker-compose.lab.yml` (never `docker-compose.review.yml`).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.lab.yml
git commit -m "feat(ops): review-lab compose override (web + caps + loopback bindings)"
```

---

### Task 2: Refresh script (`scripts/dev/lab_refresh.sh`)

**Files:**
- Create: `scripts/dev/lab_refresh.sh`

**Interfaces:**
- Consumes: Task 1 override; `scripts/dev/review_environment_seed.py` (reads `DATABASE_URL`, in-container `review-postgres:5432`); optionally `scripts/dev/seed_cypress_v3_generation.py` (present only post-#777).
- Produces: a brought-up, seeded lab; writes `.lab.env` (BUILD_SHA) for the systemd unit in Task 3.

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# Refresh the always-on Review Lab to a git ref: checkout, build, up, seed.
# Usage: scripts/dev/lab_refresh.sh [git-ref]   (default: main)
set -euo pipefail

REF="${1:-main}"
cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f docker-compose.review.yml -f docker-compose.lab.yml)
IN_DB="postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review"

echo "==> fetch + checkout ${REF}"
git fetch --prune origin
git checkout "${REF}"
git pull --ff-only origin "${REF}" 2>/dev/null || true  # no-op for detached PR refs

export BUILD_SHA="$(git rev-parse HEAD)"
echo "BUILD_SHA=${BUILD_SHA}" > .lab.env
echo "==> BUILD_SHA=${BUILD_SHA}"

echo "==> build"
"${COMPOSE[@]}" build

echo "==> up"
"${COMPOSE[@]}" up -d

echo "==> wait for Postgres"
until "${COMPOSE[@]}" exec -T review-postgres pg_isready -U review_user -d edfinder_local_review >/dev/null 2>&1; do
  sleep 2
done

echo "==> seed synthetic review data"
"${COMPOSE[@]}" exec -T -e DATABASE_URL="${IN_DB}" review-api python scripts/dev/review_environment_seed.py

if [ -f scripts/dev/seed_cypress_v3_generation.py ]; then
  echo "==> publish V3 derived generation (F3 Finder)"
  "${COMPOSE[@]}" exec -T -e DATABASE_URL="${IN_DB}" review-api python scripts/dev/seed_cypress_v3_generation.py
else
  echo "==> V3 seed absent on ${REF} (pre-#777); Finder uses the legacy path"
fi

echo "==> smoke check"
curl -sf http://localhost:4174/ >/dev/null && echo "  web ok"
curl -sf http://localhost:4174/api/health >/dev/null && echo "  api ok"
echo "==> lab is up on http://localhost:4174 (tunnel from your laptop)"
```

> NOTE for the implementer: the two `compose exec ... review-api python scripts/dev/*.py` lines assume the script path + Python imports resolve inside the api container. The base compose mounts `review_environment_seed.py` into the container; confirm the working directory and `PYTHONPATH` during Task 5's local bring-up and, if an import fails, prefix with `-e PYTHONPATH=/workspace/apps/api/src:/workspace` and/or adjust the path to the mounted location. Fix here, do not guess.

- [ ] **Step 2: Lint + syntax-check**

Run: `bash -n scripts/dev/lab_refresh.sh && shellcheck scripts/dev/lab_refresh.sh`
Expected: no syntax errors; resolve any shellcheck warnings (quote variables, etc.).

- [ ] **Step 3: Make executable + commit**

```bash
chmod +x scripts/dev/lab_refresh.sh
git add scripts/dev/lab_refresh.sh
git commit -m "feat(ops): lab_refresh.sh — build/seed/up the review lab to a ref"
```

---

### Task 3: systemd unit (`deploy/contabo-review-lab/edfinder-review-lab.service`)

**Files:**
- Create: `deploy/contabo-review-lab/edfinder-review-lab.service`

**Interfaces:**
- Consumes: Task 1 override + `.lab.env` (written by Task 2's script). Assumes the repo is checked out at `/opt/ed-finder` on the box (runbook documents this path).
- Produces: boot-survivable always-on stack.

- [ ] **Step 1: Write the unit**

```ini
[Unit]
Description=ED-Finder always-on Review Lab (Contabo)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/ed-finder
# .lab.env (written by scripts/dev/lab_refresh.sh) provides BUILD_SHA so the
# web service's build-arg interpolation resolves even when `up` reuses images.
EnvironmentFile=/opt/ed-finder/.lab.env
ExecStart=/usr/bin/docker compose -f docker-compose.review.yml -f docker-compose.lab.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.review.yml -f docker-compose.lab.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Validate unit syntax (best-effort local)**

Run: `systemd-analyze verify deploy/contabo-review-lab/edfinder-review-lab.service 2>&1 || echo "systemd-analyze unavailable locally — review by eye"`
Expected: no errors, or the fallback message on a non-systemd dev box (the box itself is the real check — covered in the runbook).

- [ ] **Step 3: Commit**

```bash
git add deploy/contabo-review-lab/edfinder-review-lab.service
git commit -m "feat(ops): systemd unit for the always-on review lab"
```

---

### Task 4: Host runbook (`docs/operations/contabo-review-lab.md`)

**Files:**
- Create: `docs/operations/contabo-review-lab.md`

**Interfaces:**
- Consumes: Tasks 1-3 artifacts. No code depends on this; it is the user-facing execution doc.

- [ ] **Step 1: Write the runbook**

````markdown
# Always-On Review Lab (Contabo)

A persistent, browsable ED-Finder Review Lab on the Contabo box
(`vmi3542235`), reachable only over an SSH tunnel. Synthetic data only; no
production credentials or data. Capped so the Codex runners keep headroom.
Design: `docs/superpowers/specs/2026-10-02-contabo-review-lab-design.md`.

## One-time host setup (sudo)

```bash
# 1. Install Docker Engine + compose plugin (Debian/Ubuntu example)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker   # run docker without sudo

# 2. Clone the repo to the lab path
sudo mkdir -p /opt/ed-finder && sudo chown "$USER" /opt/ed-finder
git clone https://github.com/brianstewart377-rgb/ed-finder /opt/ed-finder
cd /opt/ed-finder
```

## Bring it up / refresh to a ref

```bash
cd /opt/ed-finder
scripts/dev/lab_refresh.sh main        # or a PR branch name
```
This builds images, starts the stack, seeds synthetic review data (and
publishes a V3 generation once PR #777 is on the ref so the Finder returns
results), and runs a smoke check. It writes `.lab.env` (BUILD_SHA) for systemd.

## Always-on across reboots

```bash
sudo cp deploy/contabo-review-lab/edfinder-review-lab.service \
  /etc/systemd/system/edfinder-review-lab.service
sudo systemctl daemon-reload
sudo systemctl enable --now edfinder-review-lab.service
```

## Browse from your laptop (SSH tunnel)

```bash
ssh -L 4174:localhost:4174 <you>@vmi3542235.contaboserver.net
# then open http://localhost:4174  (nginx serves the SPA and proxies /api)
```
Nothing listens off-loopback on the box; the tunnel is the only way in.

## Disk hygiene

```bash
# prune dangling images/build cache (safe); schedule weekly if desired
docker image prune -f && docker builder prune -f
# inspect lab disk use
docker system df
```

## Teardown

```bash
cd /opt/ed-finder
sudo systemctl disable --now edfinder-review-lab.service
docker compose -f docker-compose.review.yml -f docker-compose.lab.yml down -v
```

## Boundaries

- Loopback + SSH tunnel only; never open a firewall port for this.
- Synthetic data + `review_user` creds only; never point it at prod.
- The Codex runners stay as host services; the lab is capped at
  ~3 CPU / ~6 GB so it cannot starve them.
- Backups (Hetzner Storage Box) are unrelated and untouched.
````

- [ ] **Step 2: Commit**

```bash
git add docs/operations/contabo-review-lab.md
git commit -m "docs(ops): host runbook for the always-on review lab"
```

---

### Task 5: Local end-to-end smoke test (verification)

**Files:** none (verification; commit only fixes it surfaces).

This is the real test: a full local bring-up using the dev box's Docker (available in this environment), proving the stack builds, serves the SPA, proxies `/api`, and seeds — before the user runs it on Contabo.

- [ ] **Step 1: Build + bring up locally**

Run:
```bash
cd <repo>
export BUILD_SHA=$(git rev-parse HEAD)
docker compose -f docker-compose.review.yml -f docker-compose.lab.yml up -d --build
```
Expected: `review-postgres`, `review-redis`, `review-api`, `review-web` all start. (First build is a few minutes — the web stage runs `pnpm install`/`build`.)

- [ ] **Step 2: Seed + verify the endpoints**

Run:
```bash
IN_DB="postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review"
docker compose -f docker-compose.review.yml -f docker-compose.lab.yml exec -T \
  -e DATABASE_URL="$IN_DB" review-api python scripts/dev/review_environment_seed.py
curl -sf http://localhost:4174/ | grep -qi "<!doctype html" && echo "web OK"
curl -sf http://localhost:4174/api/health && echo "  api proxy OK"
```
Expected: seed prints a counts dict; `web OK`; a health JSON body + `api proxy OK`. If the `exec ... python` import fails, apply the PYTHONPATH/path fix from Task 2's NOTE and re-run.

- [ ] **Step 3: Exercise a product journey**

Run: open `http://localhost:4174` in a browser (or `curl` an API route the SPA uses, e.g. `curl -sf http://localhost:4174/api/local/search -X POST -H 'content-type: application/json' -d '{"reference_coords":{"x":0,"y":0,"z":0},"filters":{"distance":{"min":0,"max":1000}},"size":5}'`).
Expected: on `main` (legacy search) a 200 with results; post-#777 a 200 from the V3 path (after the conditional V3 seed ran).

- [ ] **Step 4: Tear down + record**

Run: `docker compose -f docker-compose.review.yml -f docker-compose.lab.yml down -v`
Record the clean run in the PR description. Commit any fixes the smoke test required (compose/script/path), else nothing to commit.

---

## Self-review

**Spec coverage:**
- Always-on Review Lab → Tasks 1-3 (compose + refresh + systemd).
- SSH-tunnel-only / loopback → Task 1 bindings + Task 4 tunnel step; no firewall step anywhere.
- Compose-override approach, base untouched → Task 1 Step 3 guard + Global Constraints.
- ≤ 3 CPU / 8 GB cap → Task 1 `deploy.resources.limits` (1+0.5+1+0.5 CPU, 2+0.5+3+0.5 GB = 3 CPU / 6 GB).
- V3-seeded Finder → Task 2 conditional seed + Global Constraints dependency note.
- Synthetic data / non-prod creds / no public surface → Global Constraints + Task 4 boundaries.
- Artifacts vs. host execution → Global Constraints + Task 4 runbook.
- Backups untouched → stated; no task touches the Storage Box.
- CI Review Lab gate unaffected → base file never modified (Task 1 Step 3).

**Placeholder scan:** none — every artifact has complete content. The two runtime-verify points (in-container seed path; systemd-analyze availability) are explicit, bounded, and assigned to Task 5 / Task 3 with the exact fix to apply.

**Type/name consistency:** compose service names (`review-postgres`, `review-redis`, `review-api`, `review-web`), the override filename, `EDFINDER_API_UPSTREAM=review-api:8000`, `BUILD_SHA`, `.lab.env`, `/opt/ed-finder`, and the `4174`/`8080`/`8001`/`5432` ports are used identically across Tasks 1-5.

## Dependency note

The V3 Finder payoff depends on **PR #777** (the F3 search repoint + `seed_cypress_v3_generation.py`) reaching the ref the lab tracks. Until then the lab runs on `main`'s legacy search path and the refresh script skips the V3 seed automatically. No task here blocks on #777; the lab is useful immediately and upgrades itself when #777 merges.
