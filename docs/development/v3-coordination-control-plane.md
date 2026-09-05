# V3 Coordination Control Plane

## Status and purpose

This is supporting process guidance for coordinating V3 integration. It is not
product, architecture, infrastructure, or production authority. Those decisions
remain with the current authority chain in [`../../README.md`](../../README.md).

## Active integration lane

PR #601 is the active integration lane. Its current known exact head is
`12eebac48ca9286e0fd8c180cc5f552dc922d07e`. That head contains the real
Explore/Finder → fresh Babylon → canonical Inspect slice and has landed the
Review Lab rebase to `apps/web` + Babylon.

Exact-head validation at that head is red and stabilizing. It is an integration
candidate, not a green or complete checkpoint. Always establish the actual
latest PR head before acting; this recorded SHA is coordination context, not
permission to accept a stale head.

## Coordination rules

1. Select and attest the exact target branch and immutable base before work.
2. Keep product slices bounded and preserve current authority ownership.
3. Validate the exact latest candidate through both V3 browser lanes.
4. Record failures as stabilization work; never convert red evidence into a
   checkpoint label.
5. Hand an inspected, sealed result to the trusted compare-and-swap writer.
6. Require fresh CI and review on the resulting exact head.

Product E2E/Visual Acceptance and Review Lab are separate. Both use
`apps/web` + Babylon. Product E2E/Visual Acceptance proves the real user
journey; Review Lab changes synthetic data and the isolated environment only.
Neither lane substitutes for the other.

## Runner and checkpoint boundary

Contabo hosts three self-hosted Codex runners. They are unprivileged
implementation/review capacity, not production, and not automatically a
live-checkpoint host.

Checkpoint destination is a later explicit decision. It must define purpose,
target, trust boundary, retention, validation, and recovery semantics before
any workflow or document treats a host as authoritative checkpoint storage.
