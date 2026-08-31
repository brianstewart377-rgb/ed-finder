# GitHub Actions Hetzner Operator

## Purpose

This manual workflow runs a small allowlisted set of operator checks on Hetzner without pasting large shell blocks into SSH.

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

Repository secrets:

- `HETZNER_OPERATOR_HOST`
- `HETZNER_OPERATOR_PORT`
- `HETZNER_OPERATOR_USER`
- `HETZNER_OPERATOR_SSH_KEY`

## How to run

1. Go to the GitHub repository.
2. Open the **Actions** tab.
3. Select **Hetzner Operator**.
4. Click **Run workflow**.
5. Choose a stage.
6. Enter an artifact stage if needed, for example `stage-18j`.
7. Click **Run workflow**.

## Future stages

Any future production DB write stage must be added by a separate PR and must not use arbitrary command input.

## Separate ed-new V3 recovery lane

The `ChatGPT ed-new Ops` workflow has one narrowly scoped recovery operation:
`recover-v3-runtime-contract`. It targets only the retained container
`edfinder-v3-phase4c-full-20260827_r5-postgres` and derives the source root and
Compose files from Docker Compose labels. Its live Docker query reads labels
only; it does not request the retained container's environment, contact the
database, or write to the remote host. This distinction does not imply that
selected source files are free of historical environment captures.

Before emitting any archive byte, the helper reads and classifies every
selected regular file within the bounded file-count, per-file, and total-size
limits. The versioned manifest records each source file's original path, mode,
size, and SHA-256 plus one of these dispositions:

- `verbatim`: content passed the high-confidence safety scan unchanged;
- `redacted`: a deterministic, reviewable sanitized copy is archived and its
  archive identity is recorded;
- `excluded`: unsafe material that is not eligible for unambiguous redaction
  is recorded by reason code but no file payload is archived.

Credentialed PostgreSQL/Redis URI components, literal sensitive assignments,
and structured JSON environment values use a fixed redaction sentinel. JSON is
parsed and recursively sanitized so the archived result stays valid. Private
key blocks and recognised standalone token formats are excluded; other content
that cannot be sanitized without ambiguity fails closed. Every would-be
payload is scanned again after transformation. Required Compose configuration
must remain present and syntactically reviewable; otherwise the helper fails
closed before producing output. Explicit variable expansions, GitHub/Jinja
expressions, angle-bracket placeholders, and common redaction/change-me
sentinels are treated as templates rather than credentials.

Only successful helper completion can promote a uniquely named temporary
archive set to the upload path. The workflow computes its checksum only after
successful helper completion, then uploads
the archive with its manifest, machine-readable safety receipt, and SHA-256
sidecar. Failure cleanup prevents an earlier or partial archive from being
uploaded.

The lane requires the environment secret `ED_NEW_OPERATOR_KNOWN_HOSTS` to hold
the pinned OpenSSH known-host entry for `ED_NEW_OPERATOR_HOST` and
`ED_NEW_OPERATOR_PORT`. Runtime host discovery (`ssh-keyscan`) is prohibited.

Recovery is limited to Compose YAML, Dockerfile/Containerfile build inputs,
`.sql`, `.sh`, `.py`, and non-secret-name `.md`, `.txt`, and `.json` files.
It still rejects `.env` and secret/credential/token/key/certificate names,
logs, backups, dumps, database data/volumes, pgBackRest or SSH material,
symlinks, special files, paths outside the label-resolved source root, and
file-count or byte limits. Binary/invalid text, ambiguous sanitization,
invalid structured JSON, or preflight bounds failures stop the operation before
output. File contents and matched values are never printed to Actions logs,
manifests, receipts, or errors.

### 2026-08-31 containment status

The recovery artifact produced on 2026-08-31 was structurally intact: its
manifest matched the archived bytes. It was nevertheless unsafe because the
old helper selected files by path/name/suffix without a complete content
preflight, allowing historical files (including a Docker-inspect JSON capture)
to carry literal database credentials. The old receipt's
`docker_inspect_env: false` field described only the helper's live Docker query;
it was not evidence that selected files contained no environment material.

That artifact is not runtime, recovery, or credential authority and must not be
downloaded or used. Its deletion and the active-use/rotation disposition of the
affected credentials are separate owner containment actions tracked in #537;
this read-only helper does not perform either action. A green workflow status,
checksum match, or structurally valid archive alone does not prove that a
recovery artifact is safe. Issue #527 remains explicitly blocked until a fresh
archive produced by this contract is independently inspected and verified safe.
