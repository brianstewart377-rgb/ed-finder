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

This builds images, starts the stack, bootstraps the legacy schema, seeds
synthetic review data, and runs a smoke check. It writes `.lab.env`
(BUILD_SHA) for systemd. The base lab needs **only Docker** — schema + seed
run inside the containers.

### Optional: V3 Finder results (refs that include PR #777)

The F3 Finder reads a published V3 generation. On refs that carry
`scripts/dev/seed_cypress_v3_generation.py`, `lab_refresh.sh` publishes it
automatically — but that seed needs the apps/api **test** venv (it imports
`scripts/*` and uses psycopg, which the production api image does not carry).
Create it once, then refresh:

```bash
python -m pip install uv==0.11.33
uv sync --project apps/api --frozen --group test --no-install-project
scripts/dev/lab_refresh.sh main
```

Without that venv the lab still runs; on a pre-#777 ref the Finder uses the
legacy path, and on a post-#777 ref `lab_refresh.sh` prints the exact command
above and the Finder 404s until you run it.

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
