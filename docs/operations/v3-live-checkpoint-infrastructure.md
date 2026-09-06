# V3 live-checkpoint infrastructure

The first persistent checkpoint lives on the non-production Contabo host `vmi3542235`. It is deliberately separate from production.

The governed provisioning workflow installs Docker Engine/Compose and PostgreSQL 18, creates the persistent `edfinder-v3-checkpoint-app` bridge network, builds a fresh checkpoint database from the current migration manifest plus `sql/seed_preview.sql`, creates a dedicated read-only application role, prepares the secure API env file, local Docker context, durable receipt store, and an nginx route from the Contabo FQDN to the loopback checkpoint origin.

The provisioning path must preserve all three Codex runner services. It must not copy production data, touch production DNS/routing, provision Redis/Valkey or NATS, deploy application images, or leave application database write authority behind.

Provisioning is triggered only by an exact `{ "operation": "provision" }` request on the dedicated `v3-checkpoint-ops-requests` control branch. The workflow uses the existing `v3-live-checkpoint` SSH trust boundary and returns a sanitized target-authority candidate. That candidate must be reviewed and committed before the canonical immutable release/deploy workflow is allowed to run.
