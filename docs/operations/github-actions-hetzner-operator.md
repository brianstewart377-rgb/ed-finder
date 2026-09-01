# GitHub Actions Hetzner Operator

## Purpose

The Hetzner operator workflows run small allowlisted sets of operator checks
without pasting large shell blocks into SSH. The ChatGPT paths accept both the
existing manual Actions inputs and connector-friendly JSON requests, but
request validation and privileged execution are separate workflow runs.

## ChatGPT request trust boundary

The writable request branches never run an environment-bearing job:

- `chatgpt-ops-requests` accepts one changed
  `.github/ops-requests/*.json` request through
  `chatgpt-ops-dispatch.yml` and dispatches the legacy executor on trusted
  `main`;
- `chatgpt-ed-new-ops-requests` accepts one changed
  `.github/ed-new-ops-requests/*.json` request through
  `chatgpt-ed-new-ops-dispatch.yml` and dispatches the ed-new executor on
  trusted `main`.

The push range is resolved without assuming a two-commit checkout, so
multi-commit pushes and the all-zero `before` SHA used for branch creation are
validated across the full request. Any additional changed path, second request,
unknown JSON key, or non-allowlisted operation fails closed before dispatch.

The request workflows have no operator environment and no operator-secret
references. Their dispatch always targets `ref: main`. The privileged
executors are `workflow_dispatch` only: legacy selects `hetzner-operator`, and
ed-new selects `ed-new-operator`. They never check out or execute code from the
request ref.

Each dispatch includes request ID, file, and commit metadata for correlation.
The executors serialize production access with a FIFO gate ordered by workflow
run ID. They do not use a fixed Actions concurrency group, whose single pending
slot could replace a middle request when a newer request arrives.

## Current stages

| Stage | What it does |
|---|---|
| `context` | Shows hostname, user, repo path, git branch, recent commits, and git status. |
| `git-clean-check` | Confirms the Hetzner repo working tree is clean. |
| `latest-artifacts` | Lists recent JSON artifacts for the selected `artifact_stage`. |
| `latest-artifact-summary` | Summarises the newest JSON artifact for the selected `artifact_stage`. |

## Artifact stage input

The workflow has an `artifact_stage` input.

Examples:

- `stage-18j`
- `stage-19`
- `stage-20a`

The value must start with `stage-` and may only contain letters, numbers, underscores, and hyphens.

The scripts read artifacts from:

`/var/lib/ed-finder/operator-artifacts/<artifact_stage>`

## Hard boundary

The workflow does not accept arbitrary shell commands.

Current stages do not perform:

- DB access;
- DB writes;
- migrations;
- station-type writes;
- canonical apply.

## Required GitHub secrets

Environment secrets (`hetzner-operator`):

- `HETZNER_OPERATOR_HOST`
- `HETZNER_OPERATOR_PORT`
- `HETZNER_OPERATOR_USER`
- `HETZNER_OPERATOR_SSH_KEY`

The legacy lane retains its existing runtime host-key discovery behavior. The
repository does not currently define a pinned known-hosts secret contract for
this environment, so this repair does not invent one or claim pinned host
identity for the legacy connection. Replacing that behavior requires a
separately provisioned, reviewed pinned-known-host contract.

## How to run

1. Go to the GitHub repository.
2. Open the **Actions** tab.
3. Select **Hetzner Operator**.
4. Click **Run workflow**.
5. Choose a stage.
6. Enter an artifact stage if needed, for example `stage-18j`.
7. Click **Run workflow**.

The privileged ChatGPT executors expose equivalent operation choices in their
manual **Run workflow** forms and are loaded from the selected protected
`main` ref. Connector JSON requests instead produce a separate dispatcher run
followed by the trusted-main environment-bearing executor run.

## Future stages

Any future production DB write stage must be added by a separate PR and must not use arbitrary command input.

## Separate ed-new V3 recovery lane

The `ChatGPT ed-new Ops` workflow has one narrowly scoped recovery operation:
`recover-v3-runtime-contract`. It targets only the retained container
`edfinder-v3-phase4c-full-20260827_r5-postgres` and derives the source root and
Compose files from Docker Compose labels. It never inspects container
environment values, contacts the database, or writes to the remote host. The
archive is streamed to the Actions runner and uploaded with a file manifest,
machine-readable safety receipt, and archive SHA-256 sidecar.

The lane requires the environment secret `ED_NEW_OPERATOR_KNOWN_HOSTS` to hold
the pinned OpenSSH known-host entry for `ED_NEW_OPERATOR_HOST` and
`ED_NEW_OPERATOR_PORT`. Runtime host discovery (`ssh-keyscan`) is prohibited.

Recovery is limited to Compose YAML, Dockerfile/Containerfile build inputs,
`.sql`, `.sh`, `.py`, and non-secret-name `.md`, `.txt`, and `.json` files.
It fails closed on `.env` and secret/credential/token/key/certificate names,
logs, backups, dumps, database data/volumes, pgBackRest or SSH material,
symlinks, special files, paths outside the label-resolved source root, and
file-count or byte limits. File contents are not printed to Actions logs.
