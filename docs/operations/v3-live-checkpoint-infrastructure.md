# V3 live-checkpoint infrastructure

The first persistent checkpoint lives on the non-production Contabo host `vmi3542235`. It is deliberately separate from production.

## One-time host privilege interface

After this change merges, the owner must copy the command below from the
reviewed `main` runbook and run it on `vmi3542235` while logged in as `codex`.
It is the single installation path; do not run an installer from a runner
checkout. The root shell resolves the exact current protected `main` head from
GitHub, downloads only immutable-SHA URLs into a fresh root-owned `/run`
directory, and passes that exact SHA to the installer. The installer
independently confirms the SHA is still the GitHub `main` head before changing
the interface and again after its self-test.

```bash
/usr/bin/sudo /bin/bash -ceu '
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C LC_ALL=C
unset BASH_ENV ENV PYTHONHOME PYTHONPATH CURL_HOME XDG_CONFIG_HOME \
  HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy \
  SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE
stage=$(/usr/bin/mktemp -d /run/edfinder-v3-checkpoint-install.XXXXXXXX)
trap '\''/bin/rm -rf -- "$stage"'\'' EXIT
/usr/bin/curl --disable --noproxy "*" --proto "=https" --proto-redir "=https" \
  --tlsv1.2 --fail --location --silent --show-error \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/brianstewart377-rgb/ed-finder/commits/main \
  -o "$stage/main.json"
sha=$(/usr/bin/python3 -I -S -c "import json,sys; print(json.load(open(sys.argv[1]))[\"sha\"])" "$stage/main.json")
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || exit 78
source_root="$stage/source"
/usr/bin/install -d -m 0700 "$source_root/scripts/operator/actions"
for path in scripts/operator/install_v3_checkpoint_host_interface.py scripts/operator/actions/edfinder-v3-checkpoint-launcher scripts/operator/v3_checkpoint_bootstrap.py scripts/operator/v3_checkpoint_host_interface.sha256; do
  /usr/bin/curl --disable --noproxy "*" --proto "=https" --proto-redir "=https" \
    --tlsv1.2 --fail --location --silent --show-error \
    "https://raw.githubusercontent.com/brianstewart377-rgb/ed-finder/$sha/$path" \
    -o "$source_root/$path"
done
/bin/chmod 0600 "$source_root/scripts/operator/install_v3_checkpoint_host_interface.py" \
  "$source_root/scripts/operator/actions/edfinder-v3-checkpoint-launcher" \
  "$source_root/scripts/operator/v3_checkpoint_bootstrap.py" \
  "$source_root/scripts/operator/v3_checkpoint_host_interface.sha256"
(cd "$source_root" && /usr/bin/sha256sum --check scripts/operator/v3_checkpoint_host_interface.sha256)
/usr/bin/python3 -I -S "$source_root/scripts/operator/install_v3_checkpoint_host_interface.py" \
  --reviewed-main-sha "$sha" --source-root "$source_root"
'
```

That interactive, one-time installation is the only manual privilege bootstrap.
It atomically installs the fixed launcher as root:root mode `0755` at
`/usr/local/sbin/edfinder-v3-checkpoint-launcher`, the reviewed bootstrap as
root:root mode `0600` at
`/usr/local/libexec/edfinder-v3-checkpoint/v3_checkpoint_bootstrap.py`, and one
root:root mode `0440` rule at `/etc/sudoers.d/edfinder-v3-checkpoint`. The rule
preserves only `GH_TOKEN` for that command, uses `NOSETENV`, and grants `codex`
passwordless execution of only the fixed launcher. It does not grant
passwordless Python, Bash, `runuser`, Docker, or `ALL` command authority.

The installer validates the complete sudo policy, removes the checkpoint sudo
rule from the active include path, and validates the policy again before either
installed helper changes. Only after the bootstrap and launcher are internally
consistent does it install the narrow sudoers rule and exercise the launcher's
idempotent `--check` through the real
`codex` → `sudo -n` boundary. If any install, final policy validation,
trusted-main recheck, or self-test fails, it first removes checkpoint sudo
authority, restores the prior launcher and bootstrap, restores the prior sudoers
rule last, and validates the restored policy. Re-running the same installer is
safe and does not replace identical files. A deliberate helper change, a stale
installed helper, or repair of this interface requires the owner to rerun the
same reviewed installation command; workflows never update their own root
helper.

The governed provisioning workflow is an explicit establishment/repair
operation. It establishes every host prerequisite required by the canonical
deployer before it can emit an authorized target: exact host/FQDN identity,
exact CPython 3.14, Docker Engine/Compose, PostgreSQL 18, the persistent
`edfinder-v3-checkpoint-app` bridge network, the secure API env file, local
Docker context, durable receipt store, and an nginx route from the Contabo FQDN
to the loopback checkpoint origin. Port `127.0.0.1:18080` must either be free or
be owned by the expected running `edfinder-v3-checkpoint-web` container.
Provision is not part of an ordinary application release and must not be used
to reinstall packages, PostgreSQL, or nginx before each deployment.

Provisioning and application deployment share the durable `/var/lib/edfinder-v3-checkpoint/receipts/deploy.lock`. Provisioning must acquire that same host lock before package, Docker, PostgreSQL, or nginx mutation, so it cannot overlap the canonical deployer's apply/smoke/rollback window even if two workflow runs overlap at GitHub.

Database creation is one-time. The first successful provision creates and seeds `edfinder_checkpoint` from the current migration manifest plus `sql/seed_preview.sql`, then writes its trusted schema-identity receipt. Later provision requests do **not** apply migrations or reseed the persistent database. They require the existing trusted receipt, exact migration-ledger identity, exact preview-dataset counts, and the same database identity; any unrecognized or drifted database stops fail-closed. After a successful verification, provisioning refreshes only the receipt's verification timestamp and checksum so the canonical deployer's 24-hour schema-attestation freshness gate can be satisfied without advancing the schema.

The application database role is read-only and is explicitly denied table writes. The provisioning path also requires exactly the three expected Codex runner services to be active before and after provisioning. It must not copy production data, touch production DNS/routing, provision Redis/Valkey or NATS, deploy application images, or leave application database write authority behind.

The unified checkpoint control plane is driven from dedicated issue #623. Only a newly created, single-line `V3-CHECKPOINT <json>` comment authored by repository owner `brianstewart377-rgb` on that exact issue is eligible. GitHub evaluates `issue_comment` workflows from the trusted default branch, so the request itself cannot supply or replace executable workflow code. The control workflow supports three bounded operations: `provision` creates or verifies persistent Contabo checkpoint infrastructure and emits only a sanitized authority candidate; `release` dispatches the canonical immutable V3 release workflow for an exact `main` SHA with exact-schema compatibility; `deploy` dispatches the canonical live-checkpoint workflow using an authenticated release run ID. The control workflow never replaces those canonical release/deploy boundaries.

## Immutable local handoff

Normal issue #623 requests reuse the existing Contabo runner connection; they do not require new SSH secrets. The host-mutating jobs perform no repository checkout and execute no coding-worktree helper or toolcache interpreter. A GitHub-hosted job archives the exact trusted-main operation source and, for deployment, verifies the release provenance/checksum/manifest before sealing it with the inputs. Its artifact ID and SHA-256 pass through job outputs, not a file on the coding runner.

The hosted prepare job calculates the SHA-256 of both the fixed launcher and the
bootstrap from their exact committed source objects. The fixed launcher clears
the ambient environment, requires root execution through `SUDO_USER=codex`,
verifies the exact host/FQDN/architecture and bounded arguments, and compares
those expected SHAs with both root-owned installed helpers. The installed
bootstrap verifies its own SHA again and requires the sealed operation request
to carry both expected digests. A stale or mismatched launcher or bootstrap
therefore stops with an explicit reinstall error before artifact access instead
of silently running a different helper generation.

The installed bootstrap runs under root-owned OS Python with `-I -S`. It
first resolves the selected artifact through GitHub's API and derives its
workflow run identity from that authenticated record. Before downloading any
operation bytes, it requires the operation-specific artifact name, canonical
workflow path and event, the canonical repository as both repository and head
repository, an active trusted `main` run, and the exact run head SHA carried by
the request. The caller cannot replace that API provenance with command-line or
bundle metadata. The bootstrap then downloads only that authenticated artifact,
verifies its bundle checksum before writing or executing operation files,
rejects traversal, duplicate names, links and oversized contents, and creates a
root-owned staging directory under `/run`. Only the verified entrypoint runs.
The non-root deployer and postgres may read that code but cannot overwrite it.
Tests also exercise a poisoned local checkout: it is never consulted. This
protects the operation-file handoff; it does not claim that an
already-compromised root account or runner service has become a security
sandbox.

The OS Python is a narrow installed-bootstrap dependency, not the application
or deployment runtime. Provisioning establishes system CPython 3.14; canonical
deployment still requires that exact major/minor version. Run `34066816058`
reached runner `contabo-codex-worker` on `vmi3542235`, then job
`101576958599` stopped at the immutable provision step with
`sudo: a password is required`; no provisioning mutation occurred. The narrow
one-time interface above permanently resolves that missing capability without
granting an interpreter or general shell. The operator UID/GID are read from
the existing `codex` account instead of guessing 1001. Host identity, FQDN,
architecture and exactly-three active runners remain runtime checks. No runner
service is restarted by the transport.

## Owner staging sequence

Initial establishment or infrastructure repair is:

1. Run the one-time host-interface installation command above.
2. Comment `V3-CHECKPOINT {"operation":"provision"}` on issue #623.
3. Review and commit the sanitized authority candidate emitted by provisioning.
4. Use the normal release and deployment sequence below.

After establishment, the repeatable staging path is issue #623 `release` →
`deploy` → the canonical workflow's automatic external public smoke. Ordinary
deployments do not invoke provisioning and mutate only the existing digest-pinned
`api` and `web` application services. Provision remains available only when
establishing or deliberately repairing host infrastructure.

GHCR login/logout remains ephemeral around the canonical non-root apply/smoke/rollback operation. The sanitized target-authority candidate must still be reviewed and committed before deployment. Only digest-pinned `api` and `web` containers are recreated; the database, edge route, runners, network and receipt store persist. Explicit opt-in SSH compatibility remains separate from the normal local path.

## Public acceptance

The release image stamps its exact build SHA into both `index.html` and the `200.html` SPA fallback. The external GitHub-hosted smoke checks those actual HTML responses as well as the API health/build/database/session/OpenAPI checks. A missing, duplicate or stale HTML identity stops acceptance even when the API is current. The protected image-parity lane checks both HTML identities inside the real built image. A completed local deployment alone is not evidence of successful public acceptance.
