# R1 Canonical Body Subtype Mapper — Completion

Date: 2026-08-31
Branch: `chatgpt-ed-new-ops-requests`
Status: **bounded mapper/manifest/test slice complete**

## Scope

This completion covers only the Review-2-authorised pure body-subtype mapper stage.

No database schema, retained normalized V3 generation, capability generation, Finder/API/frontend path, importer integration, or legacy Ratings/archetype code was changed.

## Repository checkpoints

```text
Review-2 base:
991fc59abbf5587e4a0102674f43a95a0fa2558c

Tested implementation head before this completion document:
19324bc3cb3ff23ca957067764b59ca6b719bb7e
```

The completion document is the fourth authorised file and is committed after the tested implementation head above.

## Exactly changed files

Review 2 authorised exactly:

```text
apps/importer/src/body_subtypes_v1.json
apps/importer/src/v3_body_subtypes.py
tests/test_v3_body_subtypes.py
docs/research/r1-canonical-body-subtype-mapper-completion-2026-08-31.md
```

No other file is part of this implementation slice.

## Manifest identity

```text
manifest revision:
v3-body-subtype-map-1

canonical manifest SHA-256:
1a4b19585c9e20a73a4e93ea54078c18696456f1b41bef540eef0aae150c1662

canonical entries:
61

Planet entries:
18

Star entries:
43

resolved explicit aliases in audited corpus:
72

explicit unresolved:
M
N
Y
```

Canonical numeric ranges are exactly:

```text
Planet: 1001..1018
Star:   2001..2043
```

## Real-corpus coverage

The regression corpus is the exact set of 75 non-empty subtype strings observed by the earlier indexed read-only audit of legacy/public `bodies.subtype`.

Result:

```text
audited distinct values:      75
resolved:                     72
explicitly unresolved:         3
unmapped audited values:       0
type-mismatch audited values:  0
```

The only explicitly unresolved audited values are:

```text
M
N
Y
```

They are not guessed into richer stellar identities.

## Focused test evidence

Command:

```text
python -m pytest -q tests/test_v3_body_subtypes.py
```

Result:

```text
40 passed in 0.05s
```

The same exact local files used for the focused run were verified against their committed Git blob IDs:

```text
apps/importer/src/body_subtypes_v1.json
  3532bcb328864f193a869b82e09c3abf02863857

apps/importer/src/v3_body_subtypes.py
  b5be4e974e251cc481d37409693dd3b486ec6adb

tests/test_v3_body_subtypes.py
  3293b90309bca6eb75371bd4bac43561d8a0d442
```

Those blob IDs matched the branch files returned by GitHub after commit, so the tested local bytes and committed bytes are identical.

Python compilation also passed for the mapper and focused test module.

## Required semantic proofs

### 75-value accounting

The focused suite proves every audited value is classified as either:

- `resolved`, or
- `explicit_unresolved`.

Exactly 72 resolve and exactly three are explicitly unresolved.

### HMC identity and composability boundary

Both explicit source aliases:

```text
High metal content world
High metal content body
```

resolve to:

```text
body_subtype_id = 1002
public_code = high_metal_content_world
```

The mapper has no geological/biological/ring/terraforming input and no modifier identity in the manifest.

For example:

```text
High metal content world geological
```

is `unmapped`, not transformed into a different body identity.

This preserves the R1 rule that an HMC can separately carry geological, biological, ring, TF, atmosphere, and other modifier facts without any modifier replacing the HMC identity.

### True-Ammonia regression

Only the explicit class alias:

```text
Ammonia world
```

resolves to:

```text
body_subtype_id = 1008
public_code = ammonia_world
```

These do not become Ammonia World:

```text
Ammonia-world
Ammonia atmosphere
Gas giant with ammonia-based life
```

The punctuation/atmosphere-like values are unmapped, while the gas-giant value resolves independently to:

```text
body_subtype_id = 1016
public_code = gas_giant_ammonia_life
```

No atmosphere, volcanism, life, composition, or substring inference is present.

### Explicit alias-only normalization

Automatic preprocessing is limited to:

1. Unicode NFKC;
2. trim;
3. case-fold.

The implementation does not automatically:

- remove punctuation;
- add/remove hyphens;
- replace `body` with `world`;
- translate Sudarsky terminology;
- expand stellar letters;
- auto-slug unknown strings.

Where two spellings are equivalent, both spellings are present explicitly in the manifest.

### Body-type mismatch

A known Planet alias presented with a Star body type is `type_mismatch`.

A known Star alias presented with a Planet body type is `type_mismatch`.

`frontier_planet_class` accepts Planet aliases only and rejects Star identities.

### Source-lineage boundary

Production-eligible mapper source kinds are currently:

```text
spansh_subtype
frontier_planet_class
```

`legacy_subtype_inventory` exists only for regression/audit coverage and is explicitly not production canonical lineage.

Raw Frontier `StarType` is not supported in manifest revision 1.

## Determinism proof

The module exposes canonical manifest serialization and SHA-256.

Repeated proof:

```text
same input:
(spansh_subtype, planet, "High metal content body")

repetitions:
1000

unique canonical resolution JSON byte strings:
1
```

Manifest digest remained:

```text
1a4b19585c9e20a73a4e93ea54078c18696456f1b41bef540eef0aae150c1662
```

No timestamps, randomness, DB lookups, network calls, locale-dependent mappings, or environment-dependent identity rules participate in resolution.

## Forbidden import/source scan

The mapper imports only Python standard-library modules:

```text
dataclasses
hashlib
json
pathlib
unicodedata
typing
```

Focused source scan found no references/imports for:

```text
psycopg
psycopg2
asyncpg
redis
requests
httpx
urllib
socket
aiohttp

build_ratings
build_archetype_scores
slot_prediction
colonisation_rules

r1_finder_compare
r1_evidence_bridge
```

It therefore does not call DB, network, Ratings/archetype scoring, R1 fit evaluation, economy heuristics, slot prediction, atmosphere/composition classification, or body-signal classification.

## Manifest validation

Manifest loading is fail-closed and verifies:

- exact revision;
- exact 61-entry cardinality;
- exact 18/43 Planet/Star split;
- exact numeric ID ranges;
- signed SMALLINT bounds;
- unique IDs;
- unique public codes;
- non-empty display names and aliases;
- no alias collision within supported source/body-type domains;
- exact M/N/Y unresolved inventory;
- unresolved/resolved collision rejection;
- absence of modifier identities.

## Source-boundary confirmation

This slice changed no:

```text
apps/importer/src/import_spansh.py
apps/api/src/ingest/journal_normaliser.py
sql/r1_v3/001_structural_shell.sql
live v3_* schema
retained canonical generation
R1 capability generation
Finder/API/frontend code
legacy Ratings/archetype code
```

No database or network access is performed by the mapper.

## Database / runtime state

```text
DB writes performed by this implementation slice: false
schema migration performed: false
new V3 generation built: false
retained V3 generation altered: false
R1 capability generation built: false
Finder cutover performed: false
legacy Ratings deleted: false
```

The previously created empty additive R1 persistence shell remains separate and unchanged.

## Decision

The pure subtype mapper is now proven against the real 75-value vocabulary audit and is suitable as an input contract for the next separately reviewed canonical-schema/new-generation stage.

This completion does **not** authorise a full canonical generation rebuild or capability generation.
