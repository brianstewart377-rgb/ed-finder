# V3 production backup schedule

Host-level pgBackRest schedule for the retained PostgreSQL 18 container. This
directory is the versioned source of truth for files that previously existed only
on the production host, where their bugs were invisible to CI.

For the release-promotion path see
[the production application release runbook](../../../docs/operations/v3-production-application-release.md).
This schedule is **not** part of that promotion: it is a separate host operation.

## Layout and install paths

| File here | Installed on the host at |
|---|---|
| `pgbackrest-operation.sh` | `/opt/ed-finder-v3-runtime/pgbackrest-operation.sh` |
| `edfinder-v3-pgbackrest@.service` | `/etc/systemd/system/edfinder-v3-pgbackrest@.service` |
| `edfinder-v3-backup-full.timer` | `/etc/systemd/system/edfinder-v3-backup-full.timer` |
| `edfinder-v3-backup-diff.timer` | `/etc/systemd/system/edfinder-v3-backup-diff.timer` |
| `edfinder-v3-backup-verify.timer` | `/etc/systemd/system/edfinder-v3-backup-verify.timer` |
| `edfinder-rclone-mount.logrotate` | `/etc/logrotate.d/edfinder-rclone-mount` (owner-installed; see "Storage Box mount" below) |
| `backup-heartbeat.sh` | `/opt/ed-finder-v3-runtime/backup-heartbeat.sh` (mode `0700`; see "Backup heartbeat") |
| `edfinder-v3-backup-heartbeat.service` | `/etc/systemd/system/edfinder-v3-backup-heartbeat.service` |
| `edfinder-v3-backup-heartbeat.timer` | `/etc/systemd/system/edfinder-v3-backup-heartbeat.timer` |

For an existing schedule, update only the wrapper through the allowlisted
`v3-backup-wrapper-install` operation in `chatgpt-ed-new-ops.yml`. Apply migrations
`016_v3_governed_derived_purge.sql` and `019_v3_purge_copy_and_drop.sql` first: the
installer refuses unless both migration-ledger entries, the purge-event relation
and `v3_meta.purge_copy_backup_skip()` exist. The action streams
trusted-main code with its source SHA, verifies the committed wrapper SHA-256,
holds the schedule lock, refuses active backup/verify processes, and atomically
renames a mode-`0700` temporary file into the fixed destination. It re-reads the
installed hash and emits a receipt with both hashes and explicit write flags.
Commit that receipt before making a purge plan. It changes no timer or unit.

Initial schedule installation is a separate governed host operation; the wrapper
installer does not authorize installing units or enabling timers.

## Schedule

| Timer | When (UTC) | Operation |
|---|---|---|
| `…-backup-diff.timer` | Mon–Sat 02:30 | `pgbackrest --type=diff backup` |
| `…-backup-full.timer` | Sun 02:30 | `pgbackrest --type=full backup` |
| `…-backup-verify.timer` | Sun 12:00 | `pgbackrest verify` |

All three are randomised by 10–15 minutes and use `Persistent=false`, so a run
missed while the host is down is **not** caught up afterwards.

## Prerequisites the wrapper enforces

The wrapper refuses to run, and exits **0** with a `SKIP:` line, when any of these
is untrue:

- `/mnt/ed-storagebox` is a mount point — so a failed mount can never silently
  write backups onto the underlying local disk;
- its filesystem type is exactly `fuse.rclone`;
- the retained PostgreSQL container exists;
- another scheduled operation does not already hold the host lock;
- no `pgbackrest` backup or verify process is already running in the container.

Before starting any backup or verify it also queries the operating database
through `docker exec`, with pinned `--username edfinder_v3` and
`--dbname edfinder_v3_phase4c_full_20260827_r5`. The fixed read-only SQL reuses
migration 016's open-event definition. An unresolved `BATCH_STARTED` or
`REWRITE_STARTED` causes `SKIP` only while both its recorded PID and
`backend_start` still match a live backend in that database. Each skipped open
record is logged with its purge ID, event sequence, relation and backend identity.
A dead backend or no open record lets the schedule continue. A missing ledger
relation or any query error exits nonzero before starting a backup or verify.
The SQL is embedded because installed timer jobs have no repository checkout.

Since migration `019_v3_purge_copy_and_drop.sql` the wrapper then runs a second
fixed read, `SELECT v3_meta.purge_copy_backup_skip();`, through the same pinned
`psql` identity. It `SKIP`s (exit 0, logged) while the result is exactly `t`:
a relation of the copy-and-drop purge sits between its `COPY_STARTED` and its
`DROPPED` or abandonment, or a `v3_purge_staging`/`v3_retired` table exists
(owner answer 8 of `docs/development/v3-purge-copy-and-drop-design.md`: the
Storage Box write cache exceeds the free-space margin and the first diff after
a copy would carry the whole new table). Exactly `f` continues; any other
value or a failing query exits non-zero before pgBackRest starts. Because the
read runs on every scheduled backup, the installer refuses to install this
wrapper until 019 is applied and the function exists. WAL archiving is never
skipped. A copy left staged or swapped therefore suspends scheduled backups
until it is finished, swapped back or abandoned: the runbook's 24-hour rule
and the backup heartbeat (below) cover that.

It then requires pgBackRest itself to report `status: ok` before starting.

## Backup heartbeat

A dead-man's switch on healthchecks.io. Every hour the timer runs
`backup-heartbeat.sh`, which reads `pgbackrest info` and takes the newest
finished `full`/`diff`/`incr` backup that has no error flag:

- the stanza reports `ok` and that backup finished within **36 hours**: it
  pings the check URL (healthy);
- anything else it can read (too old, none at all, stanza not `ok`, a backup
  dated in the future, unreadable `info`): it pings the URL's `/fail` path, so
  healthchecks alerts at once;
- no usable URL file, or no CPython 3.14: it sends nothing, so the check's own
  silence alerts after its period and grace.

It never trusts the wrapper's exit status, which is 0 on every `SKIP`. Daily
backups run at 02:30 UTC (plus up to 15 minutes) and a full backup takes about
three hours, so the longest healthy gap between finished backups is about 27
hours. 36 hours keeps headroom and still alerts the same day a backup is missed.
This also covers the copy-and-drop purge: scheduled backups skip while a
relation is being copied, and a stalled copy shows up here.

The ping URL is a credential: anyone holding it can fake liveness. It lives
only in `/etc/ed-finder/v3-production/backup-heartbeat.url` (root, mode
`0600`, one line `https://hc-ping.com/<uuid>`) and is never printed or recorded.

### Install (owner, once)

1. On healthchecks.io, add a check named `ED-Finder V3 backup age` with
   **Period 1 hour** and **Grace 1 hour**, and copy its ping URL.
2. Command, production server. Paste the ping URL, press Enter, then press
   `Ctrl+D`. The URL does not go into the shell history:

   ```
   sudo sh -c 'umask 077; cat > /etc/ed-finder/v3-production/backup-heartbeat.url'
   ```
3. Dispatch `.github/workflows/chatgpt-ed-new-ops.yml` on `main` with operation
   `v3-backup-heartbeat-install` (manual dispatch on `main` only). It installs
   the three committed files with pinned SHA-256s, refuses unless the URL file
   is a private root file of the right shape, runs `systemctl daemon-reload` and
   `systemctl enable --now edfinder-v3-backup-heartbeat.timer`, runs the
   heartbeat once and records its exit status. The receipt (artifact
   `v3-backup-heartbeat-install-receipt`) must show `status: passed`, equal
   source and installed hashes, `timer_enabled: true` and
   `first_run_exit_status: 0`; it never contains the URL.
4. The check on healthchecks.io turns green after that first run.

## Fixed on 2026-09-10: twelve days of silent failure

The wrapper's "already active" guard ran `docker top <container> -eo args`.
Docker parses that output and requires a PID column, so it answered
`Error response from daemon: Couldn't find PID field in ps output`. Because the
call also redirected stderr to `/dev/null` and the script runs under
`set -euo pipefail`, the failure aborted the script before any backup and left
nothing in the journal except systemd's own lines. Every scheduled run since
installation had failed; the only two backups in the repository were taken
manually during the 2026-08-29 rehearsal.

The guard now reads `docker top "$c" -eo pid,args` and no longer discards
stderr. A regression test asserts both properties.

Two related weaknesses remain, deliberately not changed here because each is its
own decision:

- **No receipt.** The wrapper prints `START`/`PASS` but writes no durable
  receipt. `/var/lib/pgbackrest/receipts/last-backup.json` exists and is a
  leftover from the 2026-08-29 rehearsal, so it currently understates the newest
  backup rather than being maintained.
- **`Persistent=false`.** A missed run is skipped rather than caught up.

## Running one manually

```bash
systemctl start --no-block edfinder-v3-pgbackrest@diff.service
systemctl status edfinder-v3-pgbackrest@diff.service
journalctl -u edfinder-v3-pgbackrest@diff.service -n 40
```

Confirm the outcome in the repository rather than trusting the exit status:

```bash
docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres \
  pgbackrest --stanza=edfinder_v3 info
```

## Current state (2026-10-18): offsite repository restored

The retired Storage Box was replaced by a new Hetzner BX box on 2026-10-18
through `docs/operations/v3-storage-box-restoration.md` (SSH-key rclone
remote, pinned host-key fingerprints, container restarted to see the mount).
`pgbackrest stanza-create` and `check` succeeded, WAL archiving resumed, the
ledger-aware wrapper (`b20b8009…`) was reinstalled, and the first full backup
completed: label `20261018-152336F`, 1,252.9 GB, 3,233 files, 5 h 6 min, with
the WAL range archived (`pgbackrest info`: one full backup, status ok). The
Sunday full / daily diff / verify timers run against this repository from now
on. Backups taken before the retirement are unavailable; the repository holds
only what was written from 2026-10-18 onwards. A restore has still never been
rehearsed (next section).

## Storage Box mount: local write cache and log

`/opt/ed-finder-v3-runtime/mount-storagebox.sh` (host-only, not in this
repository) runs `rclone mount storagebox: /mnt/ed-storagebox` with
`--vfs-cache-mode writes`, `--log-file /root/backup-v3/rclone-mount.log` and
`--log-level INFO` (owner inspection, 2026-10-24). Two consequences:

- **Backups borrow local disk while they upload.** Each file pgBackRest writes
  lands in rclone's write cache under `/root/.cache/rclone` on the root
  filesystem before it is uploaded. The cache is uncapped; the largest size the
  log has ever recorded is 77.9 GiB, and it was 592 KB when idle. Anything that
  plans on free space on `/` (the purge's gate 2 in particular) must not run
  beside a backup, or must count that peak.
- **The log grows without bound.** It had reached 392 MB (about 1.6 million
  INFO lines, mostly per-file upload records). `edfinder-rclone-mount.logrotate`
  rotates it weekly or past 200 MB and keeps four compressed copies, using
  `copytruncate` so nothing is restarted.
  Owner-installed 2026-10-24: a forced first rotation compressed the 392 MB
  log to a 26.5 MB `rclone-mount.log.1.gz`, and rclone's next line landed at
  offset 0 of the truncated file (170 bytes), confirming it appends.

Changing the mount's own flags (a quieter `--log-level NOTICE`, a
`--vfs-cache-max-size` cap) needs the mount restarted, and the PostgreSQL
container binds `/mnt/ed-storagebox` with `rprivate` propagation, so it would
also need restarting to see the new mount
(`docs/operations/v3-storage-box-restoration.md`). That is deferred to the next
planned container restart. Note that a cap is advisory: rclone cannot evict a
file that has not finished uploading.

Every ERROR/CRITICAL line in the log dates from 2026-09-26 to 2026-10-18, the
period the retired box was unreachable and its replacement was mounted; there
have been none since.

## Still unproven: a restore

The repository holds full and diff backups, encrypted with AES-256-CBC, plus a
continuous WAL archive. **No restore from this repository has ever been
rehearsed**, which is the project's own stated bar — a backup that has not been
test-restored is a hypothesis. The daily diffs are cheap (seconds, single-digit
megabytes) because the database is read-mostly; the weekly full is the expensive
one at roughly three hours.
