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

Install by copying the script to the runtime directory with mode `0700`, the units
to `/etc/systemd/system/`, then `systemctl daemon-reload` and
`systemctl enable --now edfinder-v3-backup-{full,diff,verify}.timer`.

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

It then requires pgBackRest itself to report `status: ok` before starting.

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

## Still unproven: a restore

The repository holds full and diff backups, encrypted with AES-256-CBC, plus a
continuous WAL archive. **No restore from this repository has ever been
rehearsed**, which is the project's own stated bar — a backup that has not been
test-restored is a hypothesis. The daily diffs are cheap (seconds, single-digit
megabytes) because the database is read-mostly; the weekly full is the expensive
one at roughly three hours.
