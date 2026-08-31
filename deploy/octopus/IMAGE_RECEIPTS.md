# Octopus fresh-stack image receipts

Verified from the registry's multi-platform manifests on 2026-09-01:

| Purpose | Immutable image reference |
|---|---|
| Octopus | `ghcr.io/octopusreview/octopus-selfhost:1.0.122@sha256:7a65a6009136376a74ff0a4dd58fae26c10f610879bed7f9c97adb0530c7eb78` |
| PostgreSQL | `postgres:17-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73` |
| Qdrant | `qdrant/qdrant:v1.17.0@sha256:f1c7272cdac52b38c1a0e89313922d940ba50afd90d593a1605dbbc214e66ffb` |
| Migration Bun | `oven/bun:1.3.4-alpine@sha256:7608db4aeb44f1fe8169cc8ec7055376b3013557b106407ccf092b00e426407d` |

The tag remains in each reference for human release readability; the digest is
what makes the pull immutable. Upstream tag `v1.0.122` resolves to commit
`55583ac832472ad8b535f1f678f9c11837f7cfdb` and declares Bun `1.3.4`.
