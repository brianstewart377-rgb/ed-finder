# SSH Deploy From Windows

## Goal

Run the Hetzner production deploy from this repo with one local command, without
pasting long shell blocks into SSH every time.

This uses:

- a local SSH alias such as `ed-finder-prod`
- the repo's remote deploy script `scripts/deploy_main.sh`
- a Windows-friendly launcher `scripts/deploy-hetzner-over-ssh.ps1`

## 1. Create An SSH Alias

Edit `C:\Users\<you>\.ssh\config` and add a host entry like this:

```sshconfig
Host ed-finder-prod
  HostName <hetzner-ip-or-hostname>
  User root
  Port 22
  IdentityFile C:/Users/<you>/.ssh/<key-file>
```

Do not paste private keys into the repo or chat.

## 2. Prove SSH Works Non-Interactively

From PowerShell:

```powershell
ssh ed-finder-prod "hostname"
ssh ed-finder-prod "cd /opt/ed-finder && git rev-parse --abbrev-ref HEAD"
```

If either command hangs on a password prompt, fix SSH first. The deploy wrapper
assumes key-based auth works already.

## 3. Set A Default Alias Once

This lets the repo scripts use your alias automatically:

```powershell
setx EDFINDER_DEPLOY_TARGET ed-finder-prod
```

Open a new PowerShell window after running `setx`.

## 4. Run The Remote Deploy

From the repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-hetzner-over-ssh.ps1
```

What it does:

- opens one SSH session to the target
- runs `bash scripts/deploy_main.sh` inside `/opt/ed-finder`
- checks public `/api/health`
- checks `/`
- checks `/index.html`
- checks old `/v2/` bookmarks redirect cleanly to the root-served app

Useful flags:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-hetzner-over-ssh.ps1 -SkipPrompt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-hetzner-over-ssh.ps1 -SkipPull
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-hetzner-over-ssh.ps1 -SkipMigrations
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-hetzner-over-ssh.ps1 -SkipFrontend
```

If you do not want to use `EDFINDER_DEPLOY_TARGET`, pass the host directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-hetzner-over-ssh.ps1 -DeployHost <hetzner-ip-or-hostname>
```

## 5. Full Release Flow

If you want one command that also validates the local repo, pushes `main`, and
then deploys remotely, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release-main-to-prod.ps1
```

Recommended with an alias:

```powershell
setx EDFINDER_DEPLOY_TARGET ed-finder-prod
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/release-main-to-prod.ps1 -SkipPrompt
```

That script now assumes the current root-served SPA:

- probes `/` as the live app entrypoint
- validates `/index.html`
- uses `yarn` for frontend install/build/test steps

## 6. Operational Notes

- The SSH alias is better than hardcoding the production IP into commands.
- `scripts/deploy_main.sh` remains the canonical server-side deploy entrypoint.
- The PowerShell wrappers should call the server script, not reimplement the
  deployment logic locally.
- If the server repo has local tracked edits, fix them before normal deploys.
  Avoid using destructive cleanup unless you explicitly mean to discard work.

