# V3 production inventory receipt - 2026-09-10

Sanitized, read-only production inventory receipt for `ed-finder-prod` /
`nb79a3d.mevnode.com`, produced by workflow run `34493285192` of
`V3 production application promotion` with `operation=inventory`.

- Operation: `v3-production-inventory` (read-only)
- Schema: `ed-finder/v3-production-inventory/v1`
- Result: `status=stopped` with one recorded failure,
  `origin_root_inventory_failed`
- Mutation facts: `db_writes_performed=false`,
  `migrations_performed=false`, `service_changes_performed=false`,
  `filesystem_writes_performed=false`, `env_files_read=false`,
  `private_keys_read=false`, `read_only=true`

## Why the run reports a failure

`http://127.0.0.1:58080/` returns 404. That is expected: `58080` is owned by
the retained `edfinder-v3-proxy` fronting the api, while the Svelte application
is served by the `edfinder-v3-production-web-blue` slot on `127.0.0.1:58081`.
The receipt records the observation; reconciling that topology with the
reviewed cutover model is tracked in
`docs/operations/v3-production-application-release.md`.

## What this receipt proves

- application network `edfinder-v3-production` and its running members;
- Docker context `default` -> `unix:///var/run/docker.sock`;
- exact loopback ownership of `58080` (`edfinder-v3-proxy`) and `58081`
  (`edfinder-v3-production-web-blue`);
- the live schema `edfinder_v3_phase4c_full_20260827_r5` and its migration
  ledger rows hash, read under `BEGIN READ ONLY`;
- host capacity for the reviewed blue/green peak;
- the running release identity: `edfinder-v3-api:release-6a4fe0ef` with
  `build_sha 6a4fe0ef1cb7b8fd03b4151dc8de4802fd3f4c99`, plus
  `edfinder-v3-production-web:release-1dc4d099`;
- that no `python3.14` exists on the host (the default `python3` interpreter
  reports version 3.13.5).

The receipt deliberately excludes container environments, env-file contents,
DSNs, passwords, tokens, private keys, and Docker credential/configuration
content.
