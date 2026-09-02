# Hosted Hetzner Review Environment

> **RETIRED — 2 September 2026**
>
> This hosted review lane depended on the former Hetzner V2 production host and its production Nginx edge. That host has been decommissioned, so this runbook is no longer executable as written.
>
> Do not recreate the old Hetzner production edge solely to revive this review environment and do not redirect these commands at the V3 replacement host. See `docs/operations/infrastructure-status.md`.

## Historical purpose

This runbook operated the former persistent review lane at:

```text
https://review.ed-finder.app
```

The lane was used for manually testing draft PR branches before merge. It shared the former production Dockerised Nginx edge while keeping its API, Postgres, Redis, volumes, and synthetic corpus isolated from production data.

## Current status

The Hetzner-hosted implementation described here is retired with the V2 host.

Before using `review.ed-finder.app` again, establish a new V3-era review design and document its target host, DNS/edge boundary, authentication, data isolation, deployment path, teardown path, and production-safety proof. Do not assume the old hostname currently points to, or is safely wired into, any replacement environment.

## Historical safety boundary

The retired lane followed these rules:

- no automatic deployment from Git pushes or PR changes;
- no production database URLs, Redis URLs, volumes, credentials, API containers, or logs;
- synthetic review-only data;
- review drafts stored in browser storage for `review.ed-finder.app`;
- no ability to alter Elite Dangerous or live game state;
- one active hosted review branch/ref at a time;
- the Raspberry Pi was not the primary PR review environment.

Those principles remain useful design constraints for any future replacement, but they do not authorize reuse of the old infrastructure.

## Historical DNS and edge design

The former configuration pointed `review.ed-finder.app` to the same Hetzner host as production and used the same Cloudflare/proxied edge posture as `ed-finder.app`.

Production `ed-nginx` was the only public edge. Review used a dedicated `edfinder-review-edge` Docker network and isolated review API/data services.

That topology no longer exists as a supported production architecture.

## Historical activation procedure

The former activation began on the Hetzner host with:

```bash
cd /opt/ed-finder
git fetch origin
git checkout main
git pull --ff-only origin main
```

It created the dedicated edge network:

```bash
docker network create edfinder-review-edge
```

and a review-only HTTP basic-auth file with:

```bash
cd /opt/ed-finder
scripts/ops/create_review_auth_file.sh --user review
```

A review ref was deployed with:

```bash
cd /opt/ed-finder
scripts/ops/deploy_hosted_review.sh deploy \
  --ref <review-ref> \
  --confirm-hosted-review
```

The former production Nginx configuration was then validated/reloaded to expose the review virtual host.

These commands are retained only for historical understanding. **Do not run them against the V3 replacement host.**

## Historical review checkout

The former lane used:

```text
/opt/ed-finder-review
```

with deployment metadata under:

```text
/opt/ed-finder-review/.review/deployment.json
```

and served the built review frontend from the hostname root while proxying `/api/` to the isolated `review-api` container.

Those paths are not current V3 review authority.

## Historical teardown

The former review teardown used:

```bash
cd /opt/ed-finder
scripts/ops/deploy_hosted_review.sh teardown --confirm-hosted-review
```

with an optional explicit volume-removal mode.

Do not interpret those commands as the teardown process for any future V3 review environment.

## Repository artifacts

The following files may remain in the repository because they document or implement the former lane:

- `docker-compose.review.yml`;
- `docker-compose.review-hosted.yml`;
- `scripts/ops/deploy_hosted_review.sh`;
- `scripts/ops/create_review_auth_file.sh`;
- relevant Nginx review-vhost configuration and historical tests.

Their continued presence does not mean the hosted Hetzner review lane is active.

A future V3 review implementation should either deliberately reuse and re-review individual pieces or archive/remove them as part of its own migration PR.

## Historical record rule

Do not rewrite old PRs or Stage 25 evidence that accurately records testing through the Hetzner-hosted review lane. This document is retained to explain that history while clearly preventing new execution against infrastructure that no longer exists.
