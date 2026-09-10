# V3 production private runtime health check

Host-level systemd health check for the retained PostgreSQL and support services
plus the active application origin. Versioned here because it previously lived
only on the production host, where breaking it was invisible.

## Install paths

| File here | Installed on the host at |
|---|---|
| `health-check.sh` | `/opt/ed-finder-v3-runtime/health-check.sh` (mode `0700`) |
| `edfinder-v3-health.service` | `/etc/systemd/system/edfinder-v3-health.service` |
| `edfinder-v3-health.timer` | `/etc/systemd/system/edfinder-v3-health.timer` |

The timer runs two minutes after boot and every five minutes thereafter, with
`Persistent=true`, so a run missed during downtime is caught up.

The public surface is deliberately **not** checked here. That belongs to
`edfinder-v3-public-auth-edge-health`, which already covers the edge. This check
is the private runtime only, matching its unit description.

## Broken on 2026-09-10 by retiring the legacy containers

The check named the legacy `edfinder-v3-api` and `edfinder-v3-proxy` containers,
the API's former host port `58095`, and the legacy proxy's `/_proxy-health`
endpoint. Retiring those containers with the bootstrap cutover turned the check
red on its next five-minute run:

```
health-check.sh[45717]: error: no such object: edfinder-v3-api
```

It failed every five minutes and **nothing alerted**, because this host has no
external heartbeat. That is the second silent failure in the same week, after
twelve nights of failed backups, and it is the reason a heartbeat matters more
than any individual fix here.

The check is now topology-agnostic: it identifies the active origin by requiring
exactly one container with the `edfinder-v3-production` compose project label to
publish `127.0.0.1:58080`, and then exercises `/api/health` and
`/api/v1/auth/session` through that origin. It never names a slot, so a
blue/green cutover cannot break it, and it never names a legacy container, so
retiring one cannot either.

## Missing: a heartbeat

The previous production host ran heartbeats against healthchecks.io. This host
has none, so a failing timer produces only a journal line that nobody reads.

The pattern already exists in this repository: `nightly_update.sh` implements a
dead-man's switch that pings its heartbeat on success and the `/fail` path when
the run fails, reading the URL from configuration rather than the repository.
The same shape should cover, at minimum:

| Check | Period | Notes |
|---|---|---|
| private runtime health | 5 min | this unit |
| public auth edge health | 5 min | `edfinder-v3-public-auth-edge-health` |
| differential backup | daily | Mon–Sat 02:30 UTC |
| full backup | weekly | Sun 02:30 UTC |
| repository verification | weekly | Sun 12:00 UTC |

**One trap to design around.** A heartbeat driven by exit status alone would lie
for the backups: `pgbackrest-operation.sh` exits **0** on every `SKIP` path,
including a missing Storage Box mount, so success-ping-by-exit-code would report
healthy while nothing was backed up — the exact failure that went unnoticed for
twelve nights. The heartbeat must be driven by evidence that the work actually
happened, which is also the argument for the wrapper writing a durable receipt
rather than only printing `PASS`.

Heartbeat URLs are credentials: anyone holding one can fake liveness. They belong
in a root-owned configuration file on the host, never in this repository.
