# Ratings V4 compatible parser resume

This is a reviewable implementation and isolated PostgreSQL proof of an upgrade
that preserves progress. It is not a production cutover operation. The running
worker stays on its original bundle until the remaining deployment gates below
are satisfied.

## What remains the same

The derived generation UUID and key, immutable original manifest and its hash,
canonical generation, saved ratings/mechanics/opportunities, chunk ordinals and
all three checkpoint hashes are retained. Search continues to refer to that same
derived generation. No ratings are copied to a replacement generation, and no
published pointer is changed.

Ordinary restart already preserves committed chunks. Previously it also repeated
canonical reads and scoring for every saved chunk before reaching new work. The
upgrade path parses and hashes the saved source prefix, compares every chunk's
source projection and inventories with its checkpoint, then continues the same
stream at the first uncommitted chunk. It skips only canonical reads and encoding
for that verified prefix. It does not seek into gzip, trust a byte offset, omit
the compressed checksum at EOF, or skip the final full stored-output validation.

Canonical relations are immutable and are pinned against the original manifest
before prefix replay. Final validation still reads every saved chunk, checks its
content hash and inventories, and recomputes every rating and opportunity with
the frozen scorer. Corrupted saved output cannot reach READY.

## Explicit compatibility, not a version-name exception

Only the exact four-file identity of production builder
`fe0c058134b6fec33690fa937c2ac74338b401dc` is an eligible origin. A new generation
or any other historical identity is not eligible for this transition. Scorer,
mechanics, adapter, importer and freeze identity are checked before replay.

An explicit `--upgrade-parser-actor` initiates the transition. The proposed
additive SQL in `sql/v3/proposals/007_ratings_v4_code_upgrade.sql` must already be
installed by a reviewed operator. It adds one append-only attestation per derived
generation, containing the old and actual new code hashes, original manifest
hash, verified checkpoint frontier/digest, system count and actor. The original
manifest is never edited or relabelled as having used the new code throughout.

Registration occurs only after every saved source chunk has matched. The
generation row is then locked and its identity, lifecycle and complete checkpoint
frontier are rechecked. A concurrent frontier change aborts without registering
or writing new chunks. Subsequent writes, source sealing, validation and
explanations require the recorded target identity to equal the actual code. The
new identity also covers the upgrade implementation, proposed SQL, scorer,
canonical adapter and freeze verifier. Changed target files fail closed.

This detects a writer that advanced during verification; it is not a replacement
for stopping the old writer. The old binary does not know about a new advisory
lock. A deployment operator must establish sole writer ownership before starting
the upgrade and must preserve the old container/bundle for rollback.

## Interruption and rollback

Before the attestation is registered, an interrupted attempt has only read the
existing generation. Restarting either the old worker or another upgrade attempt
retains its committed progress.

After registration, the same new code can resume without registering another
upgrade. It verifies all chunks now present, including any committed after the
first handoff. Pending encodes or failed transactions are not checkpoints.

The old code can also resume the same generation because its original manifest
is intact and the new parser produces identical chunk data. The isolated test
executes that rollback using the actual old files, then runs the old full
validator across both old and new chunks. An old-code rollback performs its
original, slower complete prefix replay. Its validation receipt remains truthful
to the code doing that validation; the separate upgrade attestation is retained.

## Proof and deployment gates

The freeze workflow fetches the exact original commit and verifies the four
normalized file hashes before executing it in a separate process. Database
helpers accept only the local `ratings_v4_validation` service and freshly created
`v4_test_*` databases. Neither the old guard nor its manifest is monkeypatched.

The tests cover actual old-code partial build to new-code completion, interrupted
new-code resume, rollback to old code, unchanged saved rows and checkpoints,
source mismatch, different chunk size, a moving frontier, missing migration,
immutable attestation, changed target code and final detection of corrupt saved
rows. The source parser's malformed-input and EOF parity suite remains in place.

Before production cutover:

1. Pass this cross-version PostgreSQL 18 proof and review the exact candidate.
2. Measure prefix replay against retained production data read-only. Parsing must
   still start at the beginning; a cheap resume is not an instantaneous resume.
   Include the measured catch-up delay in the completion-time comparison, and
   measure production throughput rather than treating fixture speedup as fact.
3. Promote the proposed additive SQL into the declared V3 migration lineage with
   the matching schema identity and a bounded operator. The proposal is expressly
   outside that lineage today, so a normal migration/deploy cannot apply it.
4. The operator must check the exact target, bundle and generation identities,
   acquire the existing start lock, stop the old worker cleanly, retain it, start
   the same-generation upgrade with unchanged chunk boundaries, and prove new
   committed progress. Restore the retained old worker on a failed handoff, after
   stopping the candidate. Do not restart Search or publish either product.

There is no automatic production launch, migration application, manifest edit,
container replacement or pointer publication in this change.
