# V3 Storage Box restoration (owner-run host procedure)

Restores the offsite pgBackRest target behind `/mnt/ed-storagebox` after the
owner retired the previous Hetzner Storage Box (recorded 2026-10-18). It
reconnects the existing, unchanged design: the `edfinder-storagebox.service`
rclone FUSE mount, the retained PostgreSQL 18 container's `rprivate` bind of
`/mnt/ed-storagebox`, and pgBackRest repository
`/mnt/ed-storagebox/ed-finder/backups/postgres-v3/v3_main` (stanza
`edfinder_v3`, `aes-256-cbc`, `repo1-retention-full=2`, `repo1-retention-diff=4`).
Nothing here changes `pgbackrest.conf`, the backup timers, the wrapper, the
database schema or data.

**Prerequisites (both recorded 2026-10-18):** migration `016` is applied
(apply run 39113822236) and the ledger-aware wrapper is installed through the
governed `v3-backup-wrapper-install` operation (run 39115078455, installed hash
equal to the committed source). Do not start this procedure if either receipt
is missing from `docs/operations/evidence/`.

Step 9 additionally needs the wrapper version that admits the **first** full
backup into an empty repository (pgBackRest reports `no valid backups` there,
which older wrappers refuse). Before step 9, the governed
`v3-backup-wrapper-install` operation must have installed the wrapper from a
`main` that contains that change, with `status: passed` and equal source and
installed hashes; it is dispatched by the operator with owner approval, not run
by hand.

The owner runs every command, as `root` on the production server
`ed-finder-prod` (`nb79a3d.mevnode.com`), one at a time, in order. Storage Box
passwords are typed only at interactive prompts and never into a command line,
a file in this repository, a chat or a log. Authentication moves to an SSH key
created on the server, so no Storage Box password is stored on it.

Facts this procedure was written from (read-only owner inspection, 2026-10-18):

- `edfinder-storagebox.service` runs `/opt/ed-finder-v3-runtime/mount-storagebox.sh`,
  which executes `rclone mount storagebox: /mnt/ed-storagebox` (uid/gid 999,
  `--allow-other`), and is ordered `Before=docker.service`.
- The database container binds `/mnt/ed-storagebox` with propagation
  `rprivate`, so it keeps the mount it saw at its last start: a new host mount
  becomes visible inside it only after the container restarts (step 7).
- pgBackRest's last successful WAL archive was 2026-09-24; the database had
  written no WAL since, so `pg_wal` held a normal 992 MB.

## Before you start

In Hetzner Robot, open the new Storage Box and switch **SSH support** on
(external reachability on). Note its username, which looks like `u123456`; its
server name is that username followed by `.your-storagebox.de`. Below,
**replace `u123456` with your own username everywhere it appears** — that is the
only value you change.

## 1. Stop the old mount service

Command, production server:

```
systemctl stop edfinder-storagebox.service
```

## 2. Create an SSH key for the Storage Box

Command, production server (no passphrase, so the mount can start unattended):

```
ssh-keygen -t ed25519 -N '' -f /root/.ssh/storagebox_ed25519 -C ed-finder-prod-storagebox
```

## 3. Install the key on the Storage Box

First check you are talking to the real Storage Box. Command, production server.
It prints the server's key fingerprints and changes nothing:

```
ssh-keyscan -p 23 u123456.your-storagebox.de 2>/dev/null | ssh-keygen -lf -
```

Open Hetzner's published Storage Box fingerprints in your web browser at
`https://docs.hetzner.com/storage/storage-box/general/` (section "SSH host
keys") and check the `ED25519` line above matches the one Hetzner lists.
**If it does not match, stop here.**

Then add the key without removing any key already on the box (Hetzner's
`install-ssh-key` appends to it). Command, production server. It asks you to
confirm the host key — type `yes` only if the `ED25519` fingerprint it shows is
the one you just matched — and then for the Storage Box **password**; type it at
that prompt only:

```
cat /root/.ssh/storagebox_ed25519.pub | ssh -p 23 u123456@u123456.your-storagebox.de install-ssh-key
```

Then check the key works without a password. Command, production server. It
must list the Storage Box's files (an empty listing is fine) without asking for
a password:

```
sftp -P 23 -i /root/.ssh/storagebox_ed25519 -b - u123456@u123456.your-storagebox.de <<< 'ls'
```

## 4. Replace the rclone `storagebox` connection

The old connection holds the retired box's address and password. Delete it.
Command, production server:

```
rclone config delete storagebox
```

Create the new one with the key and the pinned host key from step 3.
Command, production server:

```
rclone config create storagebox sftp host=u123456.your-storagebox.de user=u123456 port=23 key_file=/root/.ssh/storagebox_ed25519 known_hosts_file=/root/.ssh/known_hosts
```

Check it. Command, production server (an empty listing is fine; an error is not):

```
rclone lsd storagebox:
```

## 5. Start the mount and prove it is the Storage Box

Command, production server:

```
systemctl start edfinder-storagebox.service
```

Command, production server. It must print `fuse.rclone`:

```
findmnt -no FSTYPE /mnt/ed-storagebox
```

## 6. Create the empty repository folder

Command, production server:

```
mkdir -p /mnt/ed-storagebox/ed-finder/backups/postgres-v3/v3_main
```

## 7. Restart the database container so it sees the new mount

**Gate:** a restart stops anything running inside the database container. Do not
restart while a governed database operation is in progress. In particular, a
started Search constraint validation must first report `all_validated=true` from
the `v3-system-search-validate-constraints-status` operation (2026-10-18: run
39119560891 reported 18 of 18 validated, runner exited 0). Ask the operator to
confirm no build, validation or purge is running before continuing.

Owner approval is required for this step: PostgreSQL is offline for about a
minute and the API returns errors until it is back. `docker restart` stops and
starts the **same** container; it does not recreate or remove it. The
120-second stop timeout lets PostgreSQL shut down cleanly. Command, production
server:

```
docker restart -t 120 edfinder-v3-phase4c-full-20260827_r5-postgres
```

Command, production server. Wait until it prints `accepting connections`
(repeat after a few seconds if it does not yet):

```
docker exec edfinder-v3-phase4c-full-20260827_r5-postgres pg_isready -h 127.0.0.1 -p 5432
```

Then check the whole application is healthy again, not only the database.
Command, production server. It runs the installed health check (database
container healthy, Redis and NATS up, exactly one active web origin,
`/api/health` reporting `database: connected`, and the sign-in session check)
and must print `V3 runtime health PASS`; repeat after a minute if it does not:

```
/opt/ed-finder-v3-runtime/health-check.sh
```

Command, production server. It must print `fuse.rclone`, proving the container
now sees the Storage Box:

```
docker exec edfinder-v3-phase4c-full-20260827_r5-postgres sh -c "grep ' /mnt/ed-storagebox ' /proc/mounts"
```

## 8. Create the pgBackRest stanza in the new, empty repository

Command, production server:

```
docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres pgbackrest --stanza=edfinder_v3 stanza-create
```

Command, production server. `check` forces a WAL switch and proves archiving
reaches the new repository; it must end without an `ERROR`:

```
docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres pgbackrest --stanza=edfinder_v3 check
```

## 9. Take the first full backup through the governed wrapper

This uses the installed, ledger-aware wrapper and its locks exactly as the
Sunday timer does. It runs for hours (roughly three, last measured). Command,
production server:

```
systemctl start --no-block edfinder-v3-pgbackrest@full.service
```

Follow it. Command, production server (press `Ctrl+C` to stop watching; the
backup keeps running):

```
journalctl -fu edfinder-v3-pgbackrest@full.service
```

When it has finished, confirm the result in the repository rather than trusting
the exit status. Command, production server. It must list one `full` backup and
a WAL archive range:

```
docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres pgbackrest --stanza=edfinder_v3 info
```

## After restoration

Record the dated outcome (the `info` summary, without any secret) in
`deploy/v3-production/backup/README.md` and
`docs/operations/infrastructure-status.md`, replacing the dated "no backup
target" statements they carry until then. A restore has still never been rehearsed; that remains open.

## If something goes wrong

- Step 3 or 4 fails: nothing on the database has changed. Start again from
  step 3 after checking the username and that SSH support is on in Robot.
- Step 5 does not show `fuse.rclone`: do not continue. Read the mount log
  (command, production server: `tail -n 50 /root/backup-v3/rclone-mount.log`).
- The database does not report `accepting connections` within a few minutes
  of step 7: do not run anything else; report the output of
  (command, production server)
  `docker logs --tail 50 edfinder-v3-phase4c-full-20260827_r5-postgres`.
- Step 8 reports an error: backups stay off exactly as before restoration;
  WAL archive attempts will fail and retain WAL until fixed, so resolve it
  before any large write such as the Finder builds.
