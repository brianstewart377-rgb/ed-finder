# SSH Deploy From Windows

> **RETIRED — 2 September 2026**
>
> The former Hetzner V2 production host has been decommissioned. The deployment path described below is no longer a current ED-Finder production procedure and must not be redirected to the V3 replacement host.
>
> See `docs/operations/infrastructure-status.md` for the current infrastructure boundary.

## Historical goal

This runbook described how to run the former Hetzner production deploy from Windows without pasting long shell blocks into SSH.

It used:

- a local SSH alias such as `ed-finder-prod`;
- the repo's former remote deploy script `scripts/deploy_main.sh`;
- the Windows-friendly launcher `scripts/deploy-hetzner-over-ssh.ps1`.

## Do not use this for V3

Do not:

- create a new SSH alias pointing the old `ed-finder-prod`/Hetzner workflow at the replacement host;
- set `EDFINDER_DEPLOY_TARGET` to the replacement host and run the retired wrapper;
- run `scripts/deploy-hetzner-over-ssh.ps1` as a V3 production deployment;
- assume `/opt/ed-finder` on another machine has the same safety meaning as it had on V2;
- copy the former server-side Docker/NGINX deployment model onto V3 merely to preserve this runbook.

Any V3 production deploy must use a current replacement-host procedure with an explicit V3 safety boundary.

## Historical procedure

The former procedure created an SSH config entry similar to:

```sshconfig
Host ed-finder-prod
  HostName <hetzner-ip-or-hostname>
  User root
  Port 22
  IdentityFile C:/Users/<you>/.ssh/<key-file>
```

and then used commands such as:

```powershell
ssh ed-finder-prod "hostname"
ssh ed-finder-prod "cd /opt/ed-finder && git rev-parse --abbrev-ref HEAD"
```

The default target could be configured with:

```powershell
setx EDFINDER_DEPLOY_TARGET ed-finder-prod
```

and the former production deploy launched with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-hetzner-over-ssh.ps1
```

The wrapper opened one SSH session, ran `bash scripts/deploy_main.sh` inside `/opt/ed-finder`, and checked the public application/API routes.

The former full release wrapper was:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release-main-to-prod.ps1
```

These commands are preserved here only so historical deployment evidence remains understandable.

## Credential cleanup

Do not retain obsolete Hetzner SSH keys, aliases, known-host entries, or deployment-target environment variables merely because this documentation still records them. Remove them through the normal credential-cleanup process once they have no current dependency.

Never commit private keys or credential-bearing configuration.

## Historical record rule

Older PRs, receipts, and operations documents may correctly state that a deployment occurred using the Hetzner wrapper. Leave those records intact. This runbook itself is no longer execution authority.
