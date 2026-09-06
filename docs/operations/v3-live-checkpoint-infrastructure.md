# V3 live-checkpoint infrastructure

The first persistent checkpoint lives on the non-production Contabo host `vmi3542235`. It is deliberately separate from production.

The governed provisioning workflow installs Docker Engine/Compose and PostgreSQL 18, creates the persistent `edfinder-v3-checkpoint-app` bridge network, builds a fresh checkpoint database from the current migration manifest plus `sql/seed_preview.sql`, creates a dedicated read-only application role, prepares the secure API env file, local Docker context, durable receipt store, and an nginx route from the Contabo FQDN to the loopback checkpoint origin.

The provisioning path must preserve all three Codex runner services. It must not copy production data, touch production DNS/routing, provision Redis/Valkey or NATS, deploy application images, or leave application database write authority behind.

The unified checkpoint control plane is triggered by one strict JSON request on the dedicated `v3-live-checkpoint-requests` branch. It supports three bounded operations: `provision` creates/verifies persistent Contabo checkpoint infrastructure and emits only a sanitized authority candidate; `release` dispatches the canonical immutable V3 release workflow for an exact current `main` SHA with exact-schema compatibility; `deploy` dispatches the canonical live-checkpoint workflow using an authenticated release run ID. The control workflow never replaces those canonical release/deploy boundaries.

The provision operation uses the existing `v3-live-checkpoint` pinned SSH trust boundary. The sanitized target-authority candidate must be reviewed and committed before application deployment can proceed. Ordinary application deployments then recreate only the digest-pinned `api` and `web` containers; the database, edge route, runner services, network and receipt store persist independently.
