# Stage 26A — Isolated Hosted Review Authority and Migration Contract

## Status

**Draft authority contract. It is not active execution authority until accepted and merged.**

Stage 25 remains the current ED-Finder product programme and product-control authority. This Stage 26A contract is a bounded enabling contract subordinate to `docs/colonisation-redesign/stage-25-roadmap.md`; it does not create a general Stage 26 product programme, replace Stage 25, or authorise a product release.

This contract exists because the useful hosted-review engineering in closed PR #275 cannot be treated as current implementation authority.

## Authority order

For isolated hosted-review work, read in this order:

1. `docs/ai/CURRENT_STAGE.md`;
2. `docs/DOCUMENTATION_INDEX.md`;
3. `docs/colonisation-redesign/stage-25-roadmap.md`;
4. this contract, after it is accepted and merged;
5. live GitHub branch and PR state;
6. historical records, including closed PR #275.

No historical PR, implementation branch, chat instruction, or deployment note may override the records above.

## Historical reference: PR #275

`PR #275 — Stage 26A hosted review contract` is closed and unmerged. Its historical head is `2746658aa77a01c04c77db2dc357bc17fda865ee`.

PR #275 is retained as engineering reference only. Its runtime-guard approach, isolated review-database design, feature-availability manifest, and excluded-surface model may be examined and selectively reused only after fresh verification against current control documents and code. PR #275 cannot authorise implementation, deployment, database writes, Redis writes, infrastructure creation, or a hosted-review environment.

## Purpose

This contract defines the authority boundary required before a later fresh implementation PR may propose an isolated hosted-review environment that permits narrowly scoped, disposable review interactions.

This authority batch does not itself implement code, create an environment, provision a database or Redis instance, deploy hosted review, change production behaviour, or authorise any actual write-capable review runtime.

## Future replacement implementation boundary

A later replacement implementation PR must:

- begin from the then-current head of `work/r1-canonical-body-evidence`;
- be a fresh PR, not a rebase, retarget, revival, cherry-pick-by-default, or incremental repair of PR #275;
- verify any reused idea from PR #275 against current code, current controls, and the exact new base;
- state its exact supported, intentionally unavailable, and excluded surfaces;
- remain bounded to isolated hosted-review behaviour;
- receive one full, proportionate implementation review before owner acceptance.

This contract is not approval to create that implementation PR until this contract has been accepted and merged.

## Narrowly permitted future isolated review writes

A later, separately proposed implementation PR may propose only the following write categories, and only inside a dedicated review environment:

1. disposable scoped Watchlist membership reads and add/remove operations;
2. disposable observed-evidence fact create, update, and delete operations.

Those operations are permissible only when all of the following are true:

- they use a dedicated review PostgreSQL database and dedicated review Redis instance;
- the review data is explicitly non-production, non-canonical, disposable, and resettable;
- no production data, production credentials, canonical evidence record, or durable user state is touched;
- the route-level implementation is explicitly allowlisted and tested;
- the user-facing environment makes the disposable review status clear enough to prevent mistaken reliance on it as production state.

No other write route, persistent behaviour, or operational mutation is authorised by default. Any additional write category requires separate owner authorisation.

## Mandatory fail-closed runtime safeguards

Any future implementation must fail closed before mounting or serving a write-capable review route unless all isolation checks pass.

At minimum, it must require:

- an explicit allowlist for the review database host and review database name;
- an explicit allowlist for the review Redis host;
- refusal for missing, malformed, ambiguous, production-like, or non-allowlisted connection targets;
- no fallback to production configuration, default connection strings, or an unverified local target;
- startup-visible refusal messages that are useful to an operator without exposing secrets;
- automated negative tests proving refusal for production-like, malformed, missing, and ambiguous targets;
- positive tests proving that only the approved dedicated review targets are accepted.

This contract deliberately does not hard-code infrastructure values. A later implementation must verify the then-current approved review target values before encoding them.

## Hosted-review availability boundary

A future implementation must classify every exposed surface as exactly one of:

- `supported`;
- `intentionally_unavailable`;
- `excluded`.

Supported surfaces must be explicitly enumerated, route-scoped, and tested. Intentionally unavailable and excluded surfaces must not mount unsupported operational workflows or issue unsupported API requests.

Unless separately authorised, hosted review must keep the following unavailable or excluded:

- Admin;
- Operator;
- Search Tuning;
- Profile Sync;
- accounts, OAuth, collaboration, and durable user continuity;
- persistence migration and legacy-data migration;
- production operational-management workflows.

## Explicit prohibitions

Neither this authority batch nor a later replacement implementation PR authorises:

- production PostgreSQL or production Redis writes;
- database migrations, schema changes, canonical apply, rebaseline, or source acquisition;
- scheduler, service, timer, background-job, or worker activation;
- accounts, OAuth, Profile Sync, migration, durable continuity, or collaboration;
- Admin, Operator, Search Tuning, or operational-management workflows in hosted review;
- production deployment;
- DNS, Cloudflare, hosting, secrets, infrastructure, or environment creation;
- map redesign, broader planner-rule changes, facility-browser expansion, mission intelligence, or mining/ring work.

## Required evidence before later hosted deployment or write-enabled review acceptance

No future hosted deployment or write-enabled review environment may be accepted without all applicable evidence below:

1. isolated-stack startup using the real runtime guard;
2. positive proof that only the dedicated review database and Redis targets are accepted;
3. negative proof that production-like, malformed, missing, and ambiguous targets are refused;
4. route-level allowlist tests for every supported write operation;
5. browser evidence that supported planner, map, Watchlist, and observed-evidence flows remain inside review scope;
6. browser evidence that unavailable and excluded surfaces do not mount operational routes or emit prohibited requests;
7. proof that review data can be discarded or reset without affecting production;
8. deployment-separation evidence, if any hosted deployment is later proposed;
9. an explicit owner acceptance decision after the evidence and before any hosted deployment.

A blocked Docker, environment, browser, or deployment check is a limitation, not passing validation.

## Non-self-authorisation rule

This contract cannot record its own future merge SHA before it merges. Its merge facts remain recoverable from live GitHub metadata and may be recorded by a later ordinary working-point update. Do not open a self-closeout PR solely to record this contract's merge.
