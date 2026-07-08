# Hosted Hetzner Review Environment

This runbook activates and operates the persistent hosted review lane at:

```text
https://review.ed-finder.app
```

The review lane is for manually testing draft PR branches before they merge. It uses the production Dockerised Nginx edge, but its API, Postgres, Redis, volumes, and synthetic corpus are isolated from production data.

## Safety Boundary

- Do not deploy this automatically from GitHub, Git pushes, or PR changes.
- Do not use production database URLs, Redis URLs, volumes, credentials, API containers, or logs.
- Review data is synthetic and review-only.
- Review drafts live in browser storage for `review.ed-finder.app`.
- Review cannot alter Elite Dangerous or any live game state.
- Only one active hosted review branch/ref is supported at a time.
- The Raspberry Pi is not the primary PR review environment.

## DNS And Edge Prerequisite

`review.ed-finder.app` must point to the same Hetzner host as production and use the same Cloudflare/proxied Flexible SSL posture as `ed-finder.app`.

Do not add a new public Nginx container, host-level Nginx config, Certbot workflow, or additional public host ports. Production `ed-nginx` remains the only public edge.

## Initial Activation

Run these commands manually on the Hetzner host. They are intentionally not automated by Git push or PR state.

```bash
cd /opt/ed-finder
git fetch origin
git checkout main
git pull --ff-only origin main
```

Create the dedicated edge network that only production `ed-nginx` and hosted `review-api` may join:

```bash
docker network create edfinder-review-edge
```

Create the review auth file. The helper prompts without echoing the password, writes a bcrypt htpasswd entry as `root:<nginx-worker-group>` with mode `640`, and keeps the file non-public while allowing production Nginx to read it:

```bash
cd /opt/ed-finder
scripts/ops/create_review_auth_file.sh --user review
```

Deploy PR #271 as the first candidate only after the hosted review infrastructure is on `main`:

1. Merge PR #272.
2. Update Hetzner `main` with the merged hosted-review infrastructure.
3. Rebase PR #271 onto the updated `main`.
4. Push the rebased PR #271 branch.
5. Deploy that rebased branch into `review.ed-finder.app`.

```bash
cd /opt/ed-finder
scripts/ops/deploy_hosted_review.sh deploy \
  --ref stage-25d-a2-planner-clarity \
  --confirm-hosted-review
```

The deploy command creates `/opt/ed-finder-review/.review/nginx-logs` before production Nginx needs the review log mount.

Before recreating the live production Nginx edge, validate the assembled production Compose and Nginx configuration in a throwaway Nginx container:

```bash
cd /opt/ed-finder
docker compose config -q
docker compose run --rm --no-deps nginx nginx -t
```

Only after both preflight commands pass, expose the review virtual host by recreating only production Nginx with the new mount/network configuration:

```bash
cd /opt/ed-finder
docker compose up -d nginx
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```

Verify the public review host and production health:

```bash
curl -I -H 'Host: review.ed-finder.app' http://127.0.0.1/
curl -I -u review https://review.ed-finder.app/
curl -fsS http://127.0.0.1/api/health
curl -fsS https://ed-finder.app/api/health
docker compose ps nginx api postgres redis
```

The first command should challenge with HTTP basic auth. The second command prompts for the review password and should reach the review React app after authentication.

## Switching The Review Ref

Deploy a different branch, PR ref, tag, or commit by running the same script with a new `--ref`. The script refuses dirty review checkout state outside `.secrets/` and `.review/`, records the requested ref and resolved commit, rebuilds the review frontend with `VITE_PUBLIC_BASE=/`, and updates only the hosted review compose project.

```bash
cd /opt/ed-finder
scripts/ops/deploy_hosted_review.sh deploy \
  --ref origin/some-review-branch \
  --confirm-hosted-review
```

Deployment metadata is written to:

```text
/opt/ed-finder-review/.review/deployment.json
```

## Browser Review

Open:

```text
https://review.ed-finder.app
```

Authenticate with the review-only HTTP basic-auth account. The review frontend is served from `/opt/ed-finder-review/frontend/dist` at the hostname root. `/api/` is proxied only to the isolated `review-api` container on `edfinder-review-edge`.

## Teardown And Rollback

Standard review teardown stops only the isolated review Postgres, Redis, and API:

```bash
cd /opt/ed-finder
scripts/ops/deploy_hosted_review.sh teardown --confirm-hosted-review
```

The review hostname remains configured on production Nginx and remains protected by HTTP basic auth. While review services are stopped, the review application or its API may be unavailable; production application traffic remains unaffected.

Remove review-owned containers and volumes only when explicitly intended:

```bash
cd /opt/ed-finder
scripts/ops/deploy_hosted_review.sh teardown \
  --confirm-hosted-review \
  --remove-volumes
```

Switching review branches uses `deploy`, which rebuilds the selected ref and starts a fresh review stack with clean synthetic volumes.

Removing the review virtual host from the public edge is a separate, deliberate Nginx configuration rollback. It is not part of ordinary review teardown. Do not stop production Nginx as a review rollback step.

Do not delete `/opt/ed-finder`. Do not run `docker compose down` for the production project as part of review rollback.

## Implementation Notes

- `docker-compose.review.yml` remains the disposable local Review Lab contract.
- `docker-compose.review-hosted.yml` is the hosted overlay and adds only hosted concerns: exact review CORS, conservative limits, and the review edge network for `review-api`.
- `docker-compose.yml` attaches only `nginx` to `edfinder-review-edge`, mounts the review frontend/auth files read-only, and mounts review-only Nginx logs under `/opt/ed-finder-review/.review/nginx-logs`.
- `config/nginx.conf` serves only `review.ed-finder.app` from `/var/www/review` and proxies `/api/` to `review-api`, never to `api_backend`.
- Review admin/cache mutation endpoints are blocked at the review vhost.
- Hosted deploy resets the hosted review Compose project with `down -v --remove-orphans` only after preflight checks pass, then seeds a clean synthetic review database for the selected ref.

