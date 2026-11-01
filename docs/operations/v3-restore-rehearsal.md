# V3 restore rehearsal (owner-run, isolated copy only)

This runbook proves that the production PostgreSQL 18 backups can be restored.
It restores the pgBackRest repository onto a **separate, temporary rehearsal
server**, recovers to a chosen point in time, checks the result against
production, records the timings, and then deletes the rehearsal server.

It closes the gap recorded in `deploy/v3-production/backup/README.md` ("Still
unproven: a restore") and in audit finding A5 (2026-10-31): a backup that has
never been test-restored is a hypothesis.

## What this does and does not do

It **never**:

- restores anything into production. The production database, its container,
  its settings and its backup schedule are never stopped, restarted or changed;
- writes to the backup repository. The rehearsal server reads the Storage Box
  through a **read-only** sub-account, and the restored copy has WAL archiving
  switched off;
- exposes the restored copy to the internet. It listens only on its own
  loopback, and the server's firewall allows SSH only.

It changes nothing in `docs/operations/infrastructure-status.md`'s recovery
boundary. Restoring into production is still not authorized; that needs its
own reviewed runbook. A passed rehearsal is the evidence that runbook will
build on.

Production is touched only by:
- read-only commands (Part 1);
- one named restore point plus one `pgbackrest check` (Part 4 step 3). The
  restore point is a single marker record in the WAL; it changes no data. The
  `check`, which the backup README already uses as an owner step, forces a WAL
  switch so that marker is archived. Together they give the rehearsal an exact
  recovery target;
- copying out the pgBackRest configuration and the database image (Part 4).

## The machines

| Name used below | What it is |
|---|---|
| **production server** | `ed-finder-prod` (`nb79a3d.mevnode.com`) |
| **rehearsal server** | a temporary server you rent for the rehearsal and delete afterwards (Part 2) |
| **your PC** | the computer you are typing on |

Every command says which machine it runs on. Run them one at a time, in order.
Paste each output back to Claude before moving on, unless a step says the
output is not needed.

## When to run it

- Not on a Sunday before about 09:00 UTC. The weekly full backup starts at
  02:30 UTC and takes five to six hours.
- Not on a Sunday around 12:00 UTC, when the weekly `verify` runs.
- Best on a weekday after about 04:00 UTC, once the daily diff backup is done.
- Allow one working day. Restoring roughly a terabyte from the Storage Box
  takes hours; measuring exactly how many is one of the results.

## Part 1. Read the facts from production (read-only)

These commands change nothing. Their output has no passwords or keys in it,
so it is safe to paste to Claude. Claude then fills in the values in the table
at the start of Part 4, so every later command is exact.

1. The backups in the repository. Command, production server:

   ```
   docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres pgbackrest --stanza=edfinder_v3 info
   ```

   It lists each backup with its label, start and stop times, database size
   and WAL range. The newest `full` backup decides how big the rehearsal disk
   must be.

2. The database image, start command and mounts. Command, production server:

   ```
   docker inspect --format '{{.Config.Image}} {{.Image}} {{json .Config.Entrypoint}} {{json .Config.Cmd}} {{range .Mounts}}{{.Destination}}={{.Type}} {{end}}' edfinder-v3-phase4c-full-20260827_r5-postgres
   ```

3. The PostgreSQL and pgBackRest versions. Command, production server:

   ```
   docker exec edfinder-v3-phase4c-full-20260827_r5-postgres sh -c 'postgres --version; pgbackrest version'
   ```

4. The data directory and the archiving settings. Command, production server:

   ```
   docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres psql -X --no-psqlrc --no-password --username edfinder_v3 --dbname edfinder_v3_phase4c_full_20260827_r5 -At -c "SELECT name || '=' || current_setting(name) FROM pg_settings WHERE name IN ('server_version','data_directory','archive_mode','archive_timeout','shared_buffers','wal_compression') ORDER BY name"
   ```

   `archive_timeout` decides the recovery point. A value of `0` means WAL
   is only archived when a 16 MB segment fills. A quiet database can then go
   hours between archived segments, and a restore can only reach the last
   archived one.

5. The pgBackRest configuration's settings, with every password-like value
   hidden. Command, production server:

   ```
   docker exec -u root edfinder-v3-phase4c-full-20260827_r5-postgres sh -c "sed -E 's/^([^=]*(pass|key|secret|token)[^=]*)=.*/\1=<hidden>/' /etc/pgbackrest/pgbackrest.conf"
   ```

   Check the output before pasting it. Every line that ends in a secret must
   show `<hidden>`. If any line still shows something that looks like a
   password, do not paste it; tell Claude which setting name it was.

6. The production identity the rehearsal will be compared with. Command,
   production server:

   ```
   docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres psql -X --no-psqlrc --no-password --username edfinder_v3 --dbname edfinder_v3_phase4c_full_20260827_r5 -At -c "SELECT json_build_object('migrations', (SELECT count(*) FROM v3_meta.schema_migration), 'last_migration', (SELECT max(migration_name) FROM v3_meta.schema_migration), 'canonical', (SELECT generation_id || ':' || publication_sequence FROM v3_meta.current_canonical_generation), 'derived', (SELECT derived_generation_id || ':' || publication_sequence FROM v3_meta.current_derived_generation), 'sol_vector_md5', (SELECT md5(v::text) FROM v3_derived.system_rating_vector v WHERE v.derived_generation_id = (SELECT derived_generation_id FROM v3_meta.current_derived_generation) AND v.system_id64 = 10477373803), 'sol_body_mechanics', (SELECT count(*) FROM v3_derived.body_mechanics b WHERE b.derived_generation_id = (SELECT derived_generation_id FROM v3_meta.current_derived_generation) AND b.system_id64 = 10477373803), 'database_bytes', pg_database_size(current_database()))"
   ```

   It reads a handful of small rows (the migration ledger, the two published
   generation pointers, and Sol's rating vector and body facts) through their
   indexes. It is not a full table scan.

## Part 2. Rent the rehearsal server

Use a Hetzner Cloud server with an attached volume, so you are billed by the
hour and can delete both afterwards. Put it in the **same location as the
Storage Box** (Hetzner Robot shows the box's location), so the restore reads
over Hetzner's own network.

In the Hetzner Cloud console:

1. Create a server:
   - at least 8 vCPUs and 32 GB RAM;
   - Ubuntu 24.04;
   - your SSH key;
   - name `ed-finder-restore-rehearsal`.
2. Create a volume:
   - size the newest full backup's **database size** from Part 1 step 1, plus
     30%, rounded up to the next 100 GB;
   - attach it to that server, with **Automatic** mounting and **ext4**.
3. Create a firewall with one inbound rule: TCP port 22 from your home IP
   address and from production's IP address only. Apply it to the server.
   Production's IP address is printed by this command, production server:

   ```
   getent ahostsv4 nb79a3d.mevnode.com | head -n 1
   ```

Note the server's IPv4 address. Below it is written `REHEARSAL_IP`; replace
that with the address everywhere.

Then, from your PC, log in. Command, your PC:

```
ssh root@REHEARSAL_IP
```

Install Docker, rclone, FUSE (for the read-only mount) and `screen` (so a
long command survives a dropped connection). Command, rehearsal server:

```
apt-get update && apt-get install -y docker.io rclone fuse3 screen
```

Give the volume a fixed name. Command, rehearsal server. It links
`/srv/rehearsal` to wherever Hetzner mounted the volume, and fails loudly if
no volume is mounted:

```
v="$(findmnt -rno TARGET | grep -m1 '/HC_Volume_')" && ln -s "$v" /srv/rehearsal && df -h /srv/rehearsal/
```

## Part 3. A read-only way into the Storage Box

The rehearsal server must be able to read the repository and nothing else.

In Hetzner Robot, open the Storage Box, then **Sub-accounts**, and create one:

- base directory `ed-finder/backups/postgres-v3`;
- **read-only** switched on;
- **SSH support** switched on;
- a comment such as `restore rehearsal`.

Robot shows its username (it looks like `u123456-sub1`) and its server name
(`u123456-sub1.your-storagebox.de`). Below, **replace `u123456-sub1` with that
username everywhere**.

1. Create a key for it. Command, rehearsal server:

   ```
   ssh-keygen -t ed25519 -N '' -f /root/.ssh/storagebox_rehearsal -C restore-rehearsal
   ```

2. Check the server's host key against Hetzner's published fingerprints, the
   same way as in `v3-storage-box-restoration.md` step 3. Command, rehearsal
   server:

   ```
   ssh-keyscan -p 23 u123456-sub1.your-storagebox.de 2>/dev/null | ssh-keygen -lf -
   ```

   Compare the `ED25519` line with the one listed under "SSH host keys" at
   `https://docs.hetzner.com/storage/storage-box/general/`. **If it does not
   match, stop.**

3. Install the key on the sub-account. Command, rehearsal server. Type `yes`
   only if the fingerprint shown is the one you just matched. When asked, type
   the sub-account's **password**, at that prompt only:

   ```
   cat /root/.ssh/storagebox_rehearsal.pub | ssh -p 23 u123456-sub1@u123456-sub1.your-storagebox.de install-ssh-key
   ```

4. Create the rclone connection. Command, rehearsal server:

   ```
   rclone config create rehearsalbox sftp host=u123456-sub1.your-storagebox.de user=u123456-sub1 port=23 key_file=/root/.ssh/storagebox_rehearsal known_hosts_file=/root/.ssh/known_hosts
   ```

5. Mount it read-only at the same path production uses, so the copied
   pgBackRest configuration works unchanged. Command, rehearsal server:

   ```
   mkdir -p /mnt/ed-storagebox/ed-finder/backups/postgres-v3 && rclone mount rehearsalbox: /mnt/ed-storagebox/ed-finder/backups/postgres-v3 --read-only --allow-other --daemon
   ```

6. Prove it shows the repository and is read-only. Command, rehearsal server.
   The listing must show `archive` and `backup`, and the last line must be
   `read-only: good`:

   ```
   ls /mnt/ed-storagebox/ed-finder/backups/postgres-v3/v3_main && (touch /mnt/ed-storagebox/ed-finder/backups/postgres-v3/v3_main/write-test 2>/dev/null && echo 'WRITABLE: stop and fix the sub-account' || echo 'read-only: good')
   ```

## Part 4. Bring the configuration and the image across

These values come from Part 1. Claude writes them in here before you start
Part 4. If Part 1 step 2 shows that the image uses its own entrypoint rather
than the standard PostgreSQL one, Claude also adjusts the commands in Parts 5
and 6 before you run them.

| Value | Filled in from Part 1 |
|---|---|
| `IMAGE` | step 2, the image reference |
| `DATA_DIR` | step 4, `data_directory` |
| `TARGET_NAME` | Part 4 step 3 below |

1. Let production send files to the rehearsal server for this rehearsal only.
   Command, production server. It makes a key used only for this rehearsal
   and prints its **public** half, which is not secret:

   ```
   ssh-keygen -t ed25519 -N '' -f /root/.ssh/restore_rehearsal_tmp -C restore-rehearsal-tmp && cat /root/.ssh/restore_rehearsal_tmp.pub
   ```

   Command, rehearsal server. Replace the text between the quotes with the
   line just printed:

   ```
   echo 'PASTE-THE-PUBLIC-KEY-LINE-HERE' >> /root/.ssh/authorized_keys
   ```

2. Copy the pgBackRest configuration straight from the production container
   to the rehearsal server. It contains the repository's encryption password,
   so it is never printed, never stored on production's disk and never
   written to your PC. Command, production server:

   ```
   docker exec edfinder-v3-phase4c-full-20260827_r5-postgres cat /etc/pgbackrest/pgbackrest.conf | ssh -i /root/.ssh/restore_rehearsal_tmp root@REHEARSAL_IP 'umask 077; mkdir -p /etc/pgbackrest-rehearsal; cat > /etc/pgbackrest-rehearsal/pgbackrest.conf'
   ```

   Production's background archiving settings need a spool folder that a fresh
   container does not have, and the restored copy never archives. So remove
   them from the rehearsal copy only. Command, rehearsal server:

   ```
   sed -i -e '/^archive-async=/d' -e '/^spool-path=/d' /etc/pgbackrest-rehearsal/pgbackrest.conf && grep -c '' /etc/pgbackrest-rehearsal/pgbackrest.conf
   ```

   It prints only the number of lines in the file, which must be more than 0.

3. Fix the recovery target. Command, production server. It writes a named
   restore point into the WAL (a marker only; no data changes) and prints
   three values: the point's name, its WAL position and the time. Write down
   the name; it is `TARGET_NAME`:

   ```
   docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres psql -X --no-psqlrc --no-password --username edfinder_v3 --dbname edfinder_v3_phase4c_full_20260827_r5 -At -c "SELECT name, pg_create_restore_point(name), now() FROM (SELECT 'restore-rehearsal-' || to_char(now() AT TIME ZONE 'UTC', 'YYYYMMDD-HH24MI') AS name) n"
   ```

   A named point is used instead of a clock time on purpose. Recovery to a
   clock time can only stop once it meets a change made after that time, and a
   quiet database may make none for hours. A named point is always there.
   If this command reports `permission denied`, stop and tell Claude.

   Then make sure the marker is archived. Command, production server. It
   forces a WAL switch and waits for the archive; it must end with
   `check command end: completed successfully`:

   ```
   docker exec -u postgres edfinder-v3-phase4c-full-20260827_r5-postgres pgbackrest --stanza=edfinder_v3 --log-level-console=info check
   ```

   Then run Part 1 step 6 again on production and keep that output: it is what
   the restored copy must match.

4. Copy the database image. Command, production server. This streams the
   image; nothing is written to production's disk:

   ```
   docker save IMAGE | ssh -i /root/.ssh/restore_rehearsal_tmp root@REHEARSAL_IP 'docker load'
   ```

5. Find the image's `postgres` user and give it the files it needs. Command,
   rehearsal server:

   ```
   u="$(docker run --rm --entrypoint id IMAGE -u postgres)" && g="$(docker run --rm --entrypoint id IMAGE -g postgres)" && mkdir -p /srv/rehearsal/pgdata && chown "$u:$g" /srv/rehearsal/pgdata /etc/pgbackrest-rehearsal/pgbackrest.conf && chmod 700 /srv/rehearsal/pgdata && chmod 600 /etc/pgbackrest-rehearsal/pgbackrest.conf && echo "postgres is $u:$g"
   ```

## Part 5. Restore

Command, rehearsal server. It prints the start time, restores the newest
backup taken before the restore point, sets the copy to recover up to the point
`TARGET_NAME`, then prints the end time.
- `--archive-mode=off` makes sure the restored copy never archives.
- `--process-max=4` keeps the rehearsal under the Storage Box's limit of 10
  simultaneous connections, which production's own archiving also uses.

```
date -u && docker run --rm --name restore-rehearsal-restore -u postgres --entrypoint pgbackrest -v /srv/rehearsal/pgdata:DATA_DIR -v /etc/pgbackrest-rehearsal/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro -v /mnt/ed-storagebox:/mnt/ed-storagebox:ro IMAGE --stanza=edfinder_v3 --log-level-console=info --process-max=4 --type=name "--target=TARGET_NAME" --target-action=promote --archive-mode=off restore; date -u
```

It runs for hours and prints a line per file. If your SSH connection drops,
the restore stops with it. So run the command inside `screen`: type `screen`,
press Enter, paste the command, and press Enter. To reconnect after a drop,
log in again and type `screen -r`.

Paste the first and last 20 lines of its output to Claude. It must end with
`restore command end: completed successfully`.

## Part 6. Start the copy and let it catch up

Command, rehearsal server. The restored settings ask for 32 GB of
`shared_buffers`, more than the rehearsal server has, so this start command
sets smaller memory values. It listens on its own loopback only, and no port
is published:

```
docker run -d --name restore-rehearsal-pg --shm-size=1g -e PGDATA=DATA_DIR -v /srv/rehearsal/pgdata:DATA_DIR -v /etc/pgbackrest-rehearsal/pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro -v /mnt/ed-storagebox:/mnt/ed-storagebox:ro IMAGE postgres -c listen_addresses=localhost -c shared_buffers=8GB -c effective_cache_size=20GB -c max_wal_size=8GB
```

Follow its log. Command, rehearsal server. It replays the archived WAL up to
the restore point, then finishes. Wait for these lines, in this order:
- `consistent recovery state reached`;
- `recovery stopping at restore point "TARGET_NAME"`;
- `archive recovery complete`;
- `database system is ready to accept connections`. An earlier line ends in
  `ready to accept read-only connections`; that one is not the end.

Press `Ctrl+C` to stop following; the database keeps running.

```
docker logs -f -t restore-rehearsal-pg
```

Paste the log lines from the start of recovery to `ready to accept
connections` to Claude. Their timestamps give the replay time.

## Part 7. Check the copy

1. It is a normal, writable database again, and shows how far it got.
   Command, rehearsal server. The first value must be `f`:

   ```
   docker exec -u postgres restore-rehearsal-pg psql -X --no-psqlrc --no-password --username edfinder_v3 --dbname edfinder_v3_phase4c_full_20260827_r5 -At -c "SELECT pg_is_in_recovery(), pg_last_xact_replay_timestamp(), current_setting('archive_mode')"
   ```

   The last value must be `off`.

2. Its identity matches production's at the restore point. Command, rehearsal
   server. This is Part 1 step 6 against the copy. Its output must equal the
   production output kept from Part 4 step 3:

   ```
   docker exec -u postgres restore-rehearsal-pg psql -X --no-psqlrc --no-password --username edfinder_v3 --dbname edfinder_v3_phase4c_full_20260827_r5 -At -c "SELECT json_build_object('migrations', (SELECT count(*) FROM v3_meta.schema_migration), 'last_migration', (SELECT max(migration_name) FROM v3_meta.schema_migration), 'canonical', (SELECT generation_id || ':' || publication_sequence FROM v3_meta.current_canonical_generation), 'derived', (SELECT derived_generation_id || ':' || publication_sequence FROM v3_meta.current_derived_generation), 'sol_vector_md5', (SELECT md5(v::text) FROM v3_derived.system_rating_vector v WHERE v.derived_generation_id = (SELECT derived_generation_id FROM v3_meta.current_derived_generation) AND v.system_id64 = 10477373803), 'sol_body_mechanics', (SELECT count(*) FROM v3_derived.body_mechanics b WHERE b.derived_generation_id = (SELECT derived_generation_id FROM v3_meta.current_derived_generation) AND b.system_id64 = 10477373803), 'database_bytes', pg_database_size(current_database()))"
   ```

   `database_bytes` may differ slightly. A restored copy has no bloat from
   later activity, so the sizes are close but not byte-equal. Every other
   value must be equal.

3. The data pages are sound. Command, rehearsal server. It checks every table
   and index in `v3_meta` (the generation, publication and migration records)
   for corruption, including that every index entry points at a real row. It
   installs PostgreSQL's `amcheck` extension into the copy first, which is
   fine because the copy is thrown away. It must finish without printing any
   error:

   ```
   docker exec -u postgres restore-rehearsal-pg pg_amcheck --no-password --username edfinder_v3 --database edfinder_v3_phase4c_full_20260827_r5 --install-missing --schema v3_meta --heapallindexed --progress
   ```

4. Optional, if there is time: the same check for the whole database, without
   the index-to-row cross-check. It reads all of the roughly 1 TB, so it takes
   hours. Eight jobs run at once. It must finish without printing any error:

   ```
   docker exec -u postgres restore-rehearsal-pg pg_amcheck --no-password --username edfinder_v3 --database edfinder_v3_phase4c_full_20260827_r5 --install-missing --jobs 8 --progress
   ```

## Part 8. Record the result

Paste all the outputs to Claude, who writes the receipt
`docs/operations/evidence/<date>-v3-restore-rehearsal-receipt.json`. It
records:
- the backup label used;
- `TARGET_NAME`, the restore point's time and the last replayed transaction
  time;
- the restore time (Part 5's two `date` lines) and the replay time (Part 6's
  log);
- the total time, which is the recovery time to plan for;
- `archive_timeout`, which bounds the recovery point;
- the identity comparison and the `pg_amcheck` results;
- the versions.

It contains no password, key or ping URL. Claude then updates "Still
unproven: a restore" in `deploy/v3-production/backup/README.md` with the
dated result, in a pull request.

## Part 9. Delete everything

1. Remove the temporary key. Command, production server:

   ```
   rm /root/.ssh/restore_rehearsal_tmp /root/.ssh/restore_rehearsal_tmp.pub
   ```

2. In the Hetzner Cloud console, delete the server `ed-finder-restore-rehearsal`
   **and its volume** (the volume is a separate item; it holds a full copy of
   production's data and the copied configuration, so it must go). Delete the
   firewall.

3. In Hetzner Robot, delete the Storage Box sub-account created in Part 3.

Nothing on production needs undoing. The `pgbackrest check` in Part 4 only
forced one WAL switch.

## If something goes wrong

- **Part 3 step 6 says `WRITABLE`.** Stop. The sub-account is not read-only.
  Fix it in Robot before going further.
- **The restore (Part 5) fails.** Paste the last 40 lines. Production is not
  affected. Delete `/srv/rehearsal/pgdata`'s contents before trying again: a
  restore needs an empty directory.
- **The copy does not reach `ready to accept connections`** (Part 6), or
  recovery stops with `recovery ended before configured recovery target was
  reached` or an error about a missing WAL file. That is a real finding: the
  backups cannot reach the restore point. Paste the log. It is the result this
  rehearsal exists to catch, and is recorded as a failure, not retried until it
  passes.
- **Part 7 step 2 differs.** Paste both outputs. A difference in anything
  except `database_bytes` is a failed rehearsal.
- **Whatever happens, do Part 9**, so no copy of the data is left on a rented
  server.
