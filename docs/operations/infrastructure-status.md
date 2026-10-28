# Infrastructure Status

## Current production boundary

ED-Finder production is `ed-finder-prod` at `nb79a3d.mevnode.com` on the V3
replacement infrastructure.

It served `edfinder-v3-api:release-6a4fe0ef` with
`edfinder-v3-production-web:release-1dc4d099` from an in-place release on
2026-09-09T20:02Z made outside the governed workflow. Read-only inventory run
`34493285192` (2026-09-10) confirmed the running containers, the
`edfinder-v3-production` application network, exact loopback ownership of
`58080` and `58081`, and the live schema `edfinder_v3_phase4c_full_20260827_r5`.
Since then the promotion authority has moved to `authorized`. The first governed
`bootstrap` promotion was accepted on 2026-09-10 (leaving a durable promotion
receipt and a checksum-bound rollback target), recorded in the release authority
linked below; ROADMAP's programme status additionally records the 2026-09-16
identity release deployed via the governed path. The release currently in
production is the one recorded by the durable promotion receipt store, which is
the source of truth for the deployed build; deploys still run **only** through
the governed application-promotion workflow and its fail-closed target authority.
See [`v3-production-application-release.md`](v3-production-application-release.md).

The current environment uses PostgreSQL 18, the current backup/PITR design, the Frontier identity service, and the replacement-host operator boundary. **Backup state (2026-10-18):** a new Hetzner Storage Box was mounted on 2026-10-18 (`docs/operations/v3-storage-box-restoration.md`), WAL archiving resumed and the first full pgBackRest backup completed that evening (label `20261018-152336F`, 1,252.9 GB); the scheduled full/diff/verify timers now run against it. Copies older than the retirement are unavailable, and no restore has yet been rehearsed. See `deploy/v3-production/backup/README.md`. **Server settings (2026-10-19):** the owner moved the production PostgreSQL 18 server off its default memory/checkpoint settings and repaired the `economy_opportunity.system_id64` statistics; see `docs/operations/v3-postgres-server-settings.md`. Production actions must use only current V3 runbooks and workflows that explicitly target this environment. **SSH (2026-10-24, owner-run):** password logins are disabled on `ed-finder-prod` — `/etc/ssh/sshd_config.d/00-hardening.conf` sets `PasswordAuthentication no`, `KbdInteractiveAuthentication no` and `PermitRootLogin prohibit-password` (it sorts before any other drop-in, so it wins); `sshd -T` confirmed `passwordauthentication no` / `permitrootlogin without-password`, and a fresh key login succeeded. Key-based workflow SSH is unaffected. **fail2ban (2026-10-24, owner-run):** installed with `python3-systemd`; `/etc/fail2ban/jail.d/sshd.local` enables the `sshd` jail on the systemd backend (5 failures in 10 min → 1 h ban, increasing to at most 1 week; the owner's home address and loopback are ignored). The OpenSSH on this host logs failures as `sshd-session`; the jail's `_SYSTEMD_UNIT=ssh.service` match covers them, and `fail2ban-client status sshd` was counting failures shortly after start. **Disk clean-up (2026-10-24):** free space on `/` went from 109 GB (94% used) to 295 GB (83% used). The governed `v3-host-cleanup` operation first refused the Spansh and benchmark directories (`protected_docker_path`, run 40116592227, which removed only the unused `/root/.codex` (0.2 MB)) because retired containers still bind-mounted them; after the owner-run container removals below, run 40117493133 succeeded and removed `/data/v3/source-artifacts/spansh/2026-08-24T205426Z` (about 116 GB, the 2026-08-24 Spansh dump that fed the live generation — it is not kept anywhere else, so a future build needs a fresh dump) and `/root/edfinder-v3-benchmark` (about 23.5 GB). Owner-run on the host, each approved item by item: `docker rm` of the stopped one-shot workers `edfinder-ratings-v4-prod-p4`, `edfinder-ratings-v4-prod-p4-opt1`, `edfinder-ratings-v4-prod-p4-parallel-v1` and the never-started `edfinder-v3-phase4c-full-20260827_r5-worker` (the generations and products they built are in the database and unaffected; `v3-derived-lifecycle-status` treats an absent worker as stopped); stop and removal of the benchmark database `v3-bench-postgres` with volume `edfinder_v3_benchmark_pgdata` (5.7 GB) and of the PostgreSQL 18 trial database `pg18-lab` with volume `pg18-lab-data` (43.9 GB); removal of the exited `v3async-*` architecture-spike containers and their three volumes; `docker image prune -a --filter until=504h` (5.8 GB; images under three weeks old — the current `a031c2da` release and the `0dddc78d` rollback — and every image used by a container were kept); and `docker builder prune` (4.3 GB). The live database volume, the Octopus stack and the running application were not touched. **Schema (2026-10-26):** migration `019_v3_purge_copy_and_drop.sql` was applied through the governed `V3 production schema migration` workflow (plan run 40338574785, apply run 40338736148, owner-approved); the installed schema identity is now through-019 (`0f4a19ad…db65`, migration set `sha256:70468da0…d88d`). It added only the `v3_purge_staging`/`v3_retired` schemas, the copy ledger and executor-only functions; no payload row was copied, swapped or deleted, and no service changed. Receipt: `docs/operations/evidence/2026-10-26-v3-production-migration-apply-019-receipt-run-40338736148.json`. **Schema (2026-10-27):** migration `020_v3_purge_swap_lock_order.sql` was applied the same way (owner-approved; plan run 40551071635 reported pending exactly `[020]` with no writes; apply run 40551173291); the installed schema identity is now through-020 (`55284f7d…1f00`, migration set `sha256:20a57099…a589`). It changed only the locking inside three executor-only purge functions and added one internal helper; no table, view, grant or payload row changed, and no service changed. Receipt: `docs/operations/evidence/2026-10-27-v3-production-migration-apply-020-receipt-run-40551173291.json`. **Schema (2026-10-28):** migration `021_v3_purge_long_phase_bounds.sql` was applied the same way (owner-approved; plan run 40654122650 reported pending exactly `[021]` with no writes; apply run 40654201809); the installed schema identity is now through-021 (`c54f861f…0679`, migration set `sha256:931f8d06…3edf`). It replaced three executor-only purge functions (prepare, index build, verify); no table, view, grant or payload row changed, and no service changed. Receipt: `docs/operations/evidence/2026-10-28-v3-production-migration-apply-021-receipt-run-40654201809.json`. **Edge real-client address (2026-10-26, owner-run):** the public site is behind Cloudflare. The reviewed edge configuration from #896 (`deploy/v3-production/public-auth-edge.nginx.conf` at `3bfdd949`, sha256 `a1a26f42…a906`) replaced the bind-mounted `/etc/edfinder-v3/public-auth-edge/nginx.conf`, which was verified unchanged from the previous reviewed version first (sha256 `457d8ae3…373a`). The new file was tested inside the running edge (`nginx -t -c`), written in place (`cat >`, so the single-file bind mount keeps its inode), confirmed from inside the container and reloaded; the site answered 200 and the access log switched from Cloudflare node addresses to visitor addresses. The prior file is kept at `/root/edge-nginx.conf.before-2026-10-26` for rollback. The edge now trusts `CF-Connecting-IP` only from Cloudflare's published ranges, so per-visitor rate limits take effect when the API half of #896 is released. The origin still accepts direct, non-Cloudflare connections on port 80 (seen in the edge log); restricting it to Cloudflare and loopback is a separate, owner-decided firewall change.

The reviewed V3 application promotion boundary is
[`v3-production-application-release.md`](v3-production-application-release.md).
It has its own app-only blue/green Compose authority and is deliberately
separate from the root/legacy Compose and the Contabo checkpoint. Its committed
target authority is now `authorized`: the reviewed read-only production
inventory, schema identity, network/secret/receipt facts, and exact
unchanged-edge cutover topology are provisioned and pinned. Being authorized is
not blanket permission to deploy — promotions run only through the governed
workflow and its fail-closed target authority.

Do not infer production authority from old Git history, archived artifacts, removed workflows, or obsolete server-side paths.

Hetzner/V2 is decommissioned. Its host, container, cron, database, backup,
maintenance, smoke-test, and rollback receipts are historical only. They do not
describe this V3 environment.

## Contabo runner and checkpoint boundary

Contabo hosts exactly three self-hosted Codex runners. It is not ED-Finder
production. It is now the selected first V3 live-checkpoint target only through
the separate environment-gated application checkpoint boundary; this does not
make it a production target or authorize production credentials/data/routing.

Owner decision 2026-10-16: Docker Engine is installed on Contabo for the
disposable purge rehearsal only. A dedicated fourth runner, running as its own
`rehearsal` user and registered with only the `purge-rehearsal` label
(`--no-default-labels`), is the only account in the `docker` group. The three
Codex runners keep no container runtime access, and no Codex workflow can land
on the rehearsal runner because it has no `self-hosted`/`Linux`/`X64` label.

Owner-run host changes on Contabo, 2026-10-24:
- **needrestart no longer restarts the runners.** The daily `apt-daily-upgrade`
  (06:10 CEST; the host clock is Europe/Berlin) had `needrestart` restart
  `actions.runner.*` services, which cancelled the 1% purge rehearsal run
  40053756082 mid-job (and fits the 2026-10-17 run 39024371827).
  `/etc/needrestart/conf.d/50-github-runners.conf` now sets
  `$nrconf{override_rc}{qr(^actions\.runner\..+\.service$)} = 0;`. Updates
  still install; runners pick them up on their next restart.
- **Key-only SSH.** `50-cloud-init.conf` (`PasswordAuthentication yes`) had been
  overriding the earlier `60-cloudimg-settings.conf` (`no`), because sshd keeps
  the first value it reads; internet password-guessing was visible in the
  journal. `/etc/ssh/sshd_config.d/00-hardening.conf` sets
  `PasswordAuthentication no`, `KbdInteractiveAuthentication no` and
  `PermitRootLogin prohibit-password`; `sshd -T` confirmed it and a fresh key
  login succeeded.
- **fail2ban** with the same `sshd` jail settings as production
  (`/etc/fail2ban/jail.d/sshd.local`, systemd backend); it banned its first
  address within a minute of starting.
- The leftover rehearsal container and volume from the cancelled run were
  removed by label (`io.ed-finder.purge-rehearsal=true`).

Read-only inspection on 2026-09-06 proved host identity
`vmi3542235` / `vmi3542235.contaboserver.net`, `x86_64`, 8 logical CPUs,
24,608,576 KiB RAM (23,340,792 KiB then available), and 268,809,076,736 bytes
free on the root filesystem. Exactly three runner services were active. Only
SSH on TCP 22 and loopback DNS on TCP 53 were listening. No container runtime,
Compose installation, containers, container networks or volumes were present.
Provision run `34066816058` subsequently reached `contabo-codex-worker` on that
host, but job `101576958599` stopped at the immutable provision step with
`sudo: a password is required`. It performed no provisioning mutation. The
current checkpoint runbook defines the one-time narrow host-interface install
required before retrying provisioning; it does not grant broad sudo authority.

The reviewed checkpoint namespace is `edfinder-v3-checkpoint`, limited to the
`api` and `web` application services and 2 CPUs/2 GiB combined. Its lifecycle
is persistent: application upgrades never rebuild or tear down infrastructure.
The exact stopped facts and external-authority blockers live in
`deploy/v3-live-checkpoint/target-authority.json`. In particular, there is no
authorized checkpoint database/data source, origin/edge wiring, secret mount,
GHCR pull authority or durable receipt store yet, so first-deployment mutation
remains stopped. Production PostgreSQL/data must not fill that gap.

Ollama was experimental residue used to test local inference for Octopus. It
has been removed from production and is not part of the V3 architecture.

## V3 database recovery boundary

This repository **does not currently contain an executable PostgreSQL 18 backup/restore/PITR recovery runbook**. This file records the infrastructure boundary; it is not itself a recovery procedure.

Until a reviewed V3 database recovery runbook is added or an already-authorized current V3 operator procedure is explicitly identified, repository-driven production database backup restoration, PITR execution, or disaster-recovery commands are **not authorized**. Stop rather than adapting the retired V2 PostgreSQL/Compose procedures.

The absence of an in-repo execution runbook must remain visible; do not fill it with guessed hostnames, storage targets, credentials, PostgreSQL paths, or recovery commands.

## Legacy migration vault

A validated custom-format PostgreSQL dump is retained offsite solely as a selective legacy migration source for genuinely irreplaceable/private/manual/history data.

Validated dump identity:

- source filename: `edfinder_20260823T021001Z.dump`
- size: `75,931,356,521` bytes
- SHA-256: `20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1`
- offsite sync recorded successful: `2026-08-23T05:32:41Z`

The dump is not the operating database. Do not restore it wholesale into production and do not copy an older PostgreSQL physical data directory into PostgreSQL 18.

## Current sources of truth

- Application and infrastructure code: reviewed GitHub branches and PRs.
- Programme authority: `docs/ROADMAP.md`.
- Engineering/agent constraints: `CLAUDE.md`.
- Current operator boundary: this document plus current V3 operator workflow documentation.
- Public/reconstructable galaxy data: reimport/rebuild through the current data path.
- Legacy irreplaceable/private/manual/history data: selectively migrate from the validated offsite dump only when justified.
- Redis/cache state: disposable and rebuildable.
- NATS/JetStream transport state: not canonical domain truth; rehydrate from authoritative state when required.

## Operator rule

Before any production or recovery action, identify the target environment and the current V3 runbook explicitly. If an instruction is not present in current V3 documentation, stop rather than adapting an obsolete procedure.
