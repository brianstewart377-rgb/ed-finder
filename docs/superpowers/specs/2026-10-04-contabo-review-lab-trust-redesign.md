# Contabo Review Lab — trust/governance redesign (for review)

Addresses the 3 P1 + 1 correctness finding that paused PR #778. The lab runs on
`vmi3542235`, **the same host as the three Codex workers**, so the governing
principle is: *the lab must not weaken the trust boundary protecting that host.*

## Principle

Treat the lab exactly like the governed checkpoint: **only trusted, immutable
SHAs reach the host daemon, and all host mutation goes through the owner-gated
#623 control plane under its shared lock.** The lab is a *tenant* of that
provisioned host, not a parallel, manually-driven deploy path.

## 1. Untrusted-ref root execution (P1, lab_refresh.sh:49)

**Problem:** `git checkout <REF>` then `docker compose build/up` means an
arbitrary PR branch controls the Compose files + Dockerfiles, which run
root-equivalent containers (host mounts, privileged commands) on the runner host.

**Design — split control plane from payload, restrict to trusted SHAs:**
- Deployment **control files** (`docker-compose.review.yml`, `docker-compose.lab.yml`,
  all Dockerfiles, `lab_refresh.sh` itself) are **always read from trusted `main`**,
  never from the target ref.
- The **only** thing taken from the target ref is the application source that
  `main`'s Dockerfiles build — and the allowed `REF` set is **restricted to
  reviewed/merged SHAs** (main, or a SHA that has landed), matching the
  checkpoint's immutable-main-SHA rule. Open, unreviewed PR branches are refused.
- Mechanism: `lab_refresh.sh` resolves control files via `git show main:<path>`
  (or a sealed copy), and validates `REF` is an ancestor of `origin/main` before
  building. A branch that isn't merged → refuse.

**DECIDED (owner: "as good as possible"): support unmerged refs, sandboxed.**
A review lab's purpose is previewing PRs before merge, so it must run unmerged
refs. Safe because control files come from `main` (an unmerged ref cannot inject
host mounts / privileged flags — those live only in trusted control files), and
the container runtime is hardened: **rootless Docker (userns-remap or a dedicated
unprivileged lab user), `cap_drop: ALL`, `no-new-privileges`, no host bind
mounts, read-only root fs where feasible, isolated bridge network, resource
caps.** The untrusted ref's app/build code therefore executes only inside a
trusted-shaped, unprivileged, mount-less container that cannot reach the host or
the Codex runners. No separate VM required — the control-files-from-main split is
what makes in-host sandboxing sufficient.

## 2. Bypasses the governed provisioner (P1, contabo-review-lab.md:13)

**Problem:** manual-SSH install of a mutable script + broad Docker authority
sidesteps the #623 owner-gated, immutable-main-SHA, mutation-locked control plane.

**Design — make the lab a bounded operation of the #623 provisioner:**
- Lab host prerequisites (Docker, the named volumes, the systemd unit) are
  installed/verified by the **existing checkpoint `provision` operation** (or a
  new bounded `lab` operation on the same control plane), authored only by the
  owner via a `V3-CHECKPOINT`-style comment, under the shared mutation lock, from
  a sealed trusted-main operation source.
- `lab_refresh.sh` becomes the payload the governed op invokes, not something an
  operator runs ad-hoc over raw SSH.

**DECIDED: dedicated bounded `lab` op** on the #623 control plane (keeps lab
lifecycle separate from checkpoint lifecycle; owner-gated, sealed trusted-main
source, shared mutation lock).

## 3. Lab DB reachable by runner jobs (P2, docker-compose.lab.yml:18)

**Problem:** `review-postgres` publishes `127.0.0.1:55435` with fixed committed
creds; any concurrent Codex runner job on the host can connect and mutate/drop
the synthetic DB. The port exists *only* so the host-venv V3 seed can reach it.

**Design — remove the host port; run the seed in-network:**
- Drop the `ports:` publish for `review-postgres` in the lab override.
- Run `seed_cypress_v3_generation.py` **inside a container on the `review`
  network** (a dedicated seed container/image carrying `scripts/` + psycopg, or a
  one-shot `docker compose run` against an image that has them) so it reaches
  Postgres over the compose network, not a host port.
- Net effect: the DB is unreachable from host/runner processes; only compose-
  network peers connect.

## 4. Finder↔Inspect seed mismatch (P1, lab_refresh.sh:95)

**Problem:** the V3 seed publishes the Cypress *fixture* systems
(`9007199254740993`, `158872029`, `10477373803000`); the legacy review seed fills
`systems` with the four `720000000000x` Review systems. Finder (V3) `/inspect?system=`
links hit `/api/system/{id64}` (legacy table) → 404 for every Finder result.

**Design — one system set behind both products:**
- Build the V3 generation **from the Review systems** (the same ids the legacy
  seed uses), instead of the Cypress journey fixtures — so every Finder hit has a
  matching legacy Inspect row. (Alternative: also seed legacy detail rows for the
  Cypress ids; worse, duplicates the fixture.)
- Requires the V3 seed to accept/author its canonical systems from the Review
  fixture set rather than the hard-coded Cypress ids.

## Already handled (no action)

- **Per-ref V3 rebuild (P2):** resolved by the `down -v` volume reset in `5a3ec93c`
  (clean volume each refresh → the seed always rebuilds).
- Robustness batch (smoke/readiness/ff/matview): fixed in `5a3ec93c`.

## Rough implementation order (after you approve the approach)

1. #623 control-plane op for lab provisioning (governance spine).
2. `lab_refresh.sh`: control-files-from-main + trusted-SHA gate.
3. Compose: drop the host DB port; add the in-network seed path.
4. Seed: V3 generation from the Review system set.
5. Runbook rewrite to the governed flow; re-review.
