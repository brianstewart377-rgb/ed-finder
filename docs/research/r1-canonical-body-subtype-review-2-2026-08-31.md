# R1 Canonical Body Subtype — Review 2

Date: 2026-08-31
Status: final pre-code contract for the bounded subtype-mapper stage
Branch: `chatgpt-ed-new-ops-requests`

## 1. Purpose and stage boundary

This Review 2 turns the accepted body-subtype direction into an exact implementation contract.

The immediate implementation slice is deliberately **mapper/manifest/test only**. It does not create a new canonical generation, alter the retained published generation, add a live vocabulary table, build an R1 capability generation, or change Finder.

The first goal is to prove a deterministic explicit-identity mapping contract against the 75 source subtype strings observed in the real legacy/public body store.

Only after this mapper stage passes does a separate reviewed stage create the canonical vocabulary/new-generation schema and then, still later, a separately-authorised full galaxy generation build.

## 2. Evidence fixed by the audits

### 2.1 Normalized V3

Read-only audit of the retained normalized V3 target established:

- target database: `edfinder_v3_phase4c_full_20260827_r5`;
- published generation: `v3_gen_phase4c_full_20260827_r5`;
- `bodies` has 47 typed columns but **no body subtype/class column**;
- `body_type_id` is nullable `SMALLINT`;
- `spectral_class` and `luminosity_class` exist as nullable text;
- `v3_vocab.body_type` contains Star=1, Planet=2, Barycentre=3, Belt Cluster=4;
- there is no `v3_vocab.body_subtype` and no separate star-subtype vocabulary.

Therefore adding an explicit body subtype to the next generation does not duplicate an existing normalized subtype field.

### 2.2 Explicit source fields already exist

The subtype is available explicitly upstream:

- Frontier Journal `Scan.PlanetClass` is preserved by `journal_normaliser.py` as `planet_class`;
- Spansh body records expose `subType` / `subtype`;
- the existing Spansh importer reads that explicit value and stores it in legacy/public `bodies.subtype`.

No physical-property inference is required or permitted.

### 2.3 Real source vocabulary audit

The legacy/public `bodies.subtype` column is nullable TEXT and has a partial B-tree index on non-NULL subtype.

A read-only exact indexed distinct query found **75** non-empty source strings.

The initial canonical mapping below resolves 72 of those strings to 61 canonical identities and intentionally leaves exactly three ambiguous shorthand values unresolved:

```text
M
N
Y
```

Those three must not be guessed from the bare legacy string.

## 3. Canonical storage direction after the mapper stage

A later separately-reviewed canonical schema stage will add:

```sql
v3_vocab.body_subtype (
    body_subtype_id SMALLINT PRIMARY KEY,
    body_type_id    SMALLINT NOT NULL,
    public_code     TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (body_subtype_id, body_type_id),
    FOREIGN KEY (body_type_id)
      REFERENCES v3_vocab.body_type(body_type_id)
)
```

The next immutable generation's `bodies` relation will add:

```text
body_subtype_id                SMALLINT NULL
body_subtype_resolution_state  SMALLINT NOT NULL
```

Resolution-state codes are fixed as:

```text
0 = source_absent
1 = resolved
2 = explicit_unresolved
3 = conflicting
```

Required checks in that future schema:

- state `1` requires non-NULL `body_subtype_id` and non-NULL `body_type_id`;
- states `0`, `2`, `3` require NULL `body_subtype_id`;
- a composite FK `(body_subtype_id, body_type_id)` references `v3_vocab.body_subtype(body_subtype_id, body_type_id)` so a planet subtype cannot be attached to a Star and vice versa.

`unmapped` and `type_mismatch` are **builder failures**, not publishable resolution states.

## 4. Version-controlled manifest is authoritative for aliases

Aliases do **not** live in a JSONB column in the database.

The first implementation creates a version-controlled manifest:

```text
apps/importer/src/body_subtypes_v1.json
```

The manifest is the deterministic source for:

- canonical numeric ID;
- required body type (`planet` or `star`);
- stable `public_code`;
- display name;
- explicit accepted source aliases;
- intentionally unresolved source values;
- manifest revision.

The future `v3_vocab.body_subtype` table is seeded from the canonical entries in this manifest. The DB contains canonical identities only; source spelling variants remain build/config provenance.

The manifest revision is:

```text
v3-body-subtype-map-1
```

## 5. Mapper input/output contract

Implementation module:

```text
apps/importer/src/v3_body_subtypes.py
```

Exact source kinds supported in the first mapper:

```python
SourceKind = Literal[
    'spansh_subtype',
    'frontier_planet_class',
    'legacy_subtype_inventory',
]
```

`legacy_subtype_inventory` exists for regression/audit only and must never be accepted as the production lineage for a new canonical generation.

First mapper deliberately does **not** map raw Frontier `StarType` tokens. That token vocabulary receives a separate explicit audit before use. This prevents bare `M`, `N`, or `Y` from being silently treated as a richer stellar subtype without source-specific proof.

Body type input:

```python
BodyTypeCode = Literal['star', 'planet', 'barycentre', 'belt_cluster']
```

Disposition:

```python
SubtypeDisposition = Literal[
    'resolved',
    'source_absent',
    'explicit_unresolved',
    'unmapped',
    'type_mismatch',
]
```

Result shape:

```python
@dataclass(frozen=True)
class BodySubtypeResolution:
    source_kind: SourceKind
    raw_value: str | None
    normalized_lookup_value: str | None
    body_type_code: BodyTypeCode
    disposition: SubtypeDisposition
    body_subtype_id: int | None
    public_code: str | None
    display_name: str | None
    manifest_revision: str
```

## 6. Normalisation algorithm

The mapper performs only lookup normalisation, not semantic inference.

Allowed preprocessing before alias lookup:

1. reject non-string non-NULL values as `unmapped`;
2. Unicode NFKC normalisation;
3. trim leading/trailing whitespace;
4. if empty after trimming -> `source_absent`;
5. case-fold for lookup.

It must **not** automatically:

- remove punctuation;
- add/remove hyphens;
- singularise/pluralise;
- replace `body` with `world`;
- translate Sudarsky terminology;
- expand star letters;
- derive a slug and auto-create a new identity.

Any equivalence involving those changes exists only because both spellings are explicitly present in the manifest alias list.

Alias keys after NFKC/trim/casefold must be globally unique per supported source/body-type domain. Manifest validation fails if two canonical identities claim the same lookup key.

## 7. Source-kind rules

### 7.1 `spansh_subtype`

May resolve both Star and Planet canonical entries using the explicit aliases in this contract.

Bare `M`, `N`, and `Y` are `explicit_unresolved` in this first revision.

### 7.2 `frontier_planet_class`

May resolve **planet entries only**.

The same explicit planet-class aliases may be used where Frontier emits those exact class names. A Star input with this source kind is `type_mismatch`.

### 7.3 `legacy_subtype_inventory`

Uses the same alias inventory solely to prove coverage against the audited 75-value real corpus.

It is forbidden as production canonical lineage.

## 8. Exact initial canonical planet identities

`body_type_id` will be `2` (Planet) for all rows in this section.

| ID | public_code | display_name | accepted explicit aliases |
|---:|---|---|---|
| 1001 | `metal_rich_body` | Metal-rich body | `Metal-rich body`; `Metal rich body` |
| 1002 | `high_metal_content_world` | High metal content world | `High metal content world`; `High metal content body` |
| 1003 | `rocky_body` | Rocky body | `Rocky body` |
| 1004 | `rocky_ice_world` | Rocky ice world | `Rocky Ice world`; `Rocky ice body` |
| 1005 | `icy_body` | Icy body | `Icy body` |
| 1006 | `water_world` | Water world | `Water world` |
| 1007 | `earth_like_world` | Earth-like world | `Earth-like world`; `Earthlike body` |
| 1008 | `ammonia_world` | Ammonia world | `Ammonia world` |
| 1009 | `water_giant` | Water giant | `Water giant` |
| 1010 | `class_i_gas_giant` | Class I gas giant | `Class I gas giant`; `Sudarsky class I gas giant` |
| 1011 | `class_ii_gas_giant` | Class II gas giant | `Class II gas giant`; `Sudarsky class II gas giant` |
| 1012 | `class_iii_gas_giant` | Class III gas giant | `Class III gas giant`; `Sudarsky class III gas giant` |
| 1013 | `class_iv_gas_giant` | Class IV gas giant | `Class IV gas giant`; `Sudarsky class IV gas giant` |
| 1014 | `class_v_gas_giant` | Class V gas giant | `Class V gas giant` |
| 1015 | `gas_giant_water_life` | Gas giant with water-based life | `Gas giant with water-based life`; `Gas giant with water based life` |
| 1016 | `gas_giant_ammonia_life` | Gas giant with ammonia-based life | `Gas giant with ammonia-based life`; `Gas giant with ammonia based life` |
| 1017 | `helium_gas_giant` | Helium gas giant | `Helium gas giant` |
| 1018 | `helium_rich_gas_giant` | Helium-rich gas giant | `Helium-rich gas giant`; `Helium rich gas giant` |

Hard identity rules:

- `ammonia_world` is produced only from the explicit `Ammonia world` class alias;
- ammonia atmosphere, ammonia-based gas-giant life, ammonia volcanism, or any text in another field never maps to `ammonia_world`;
- HMC remains HMC regardless of geological/biological/ring/terraforming modifiers;
- modifiers are not inputs to subtype mapping.

## 9. Exact initial canonical star identities

`body_type_id` will be `1` (Star) for all rows in this section.

| ID | public_code | display_name / accepted explicit alias |
|---:|---|---|
| 2001 | `o_star` | `O (Blue-White) Star` |
| 2002 | `b_star` | `B (Blue-White) Star` |
| 2003 | `a_star` | `A (Blue-White) Star` |
| 2004 | `f_star` | `F (White) Star` |
| 2005 | `g_star` | `G (White-Yellow) Star` |
| 2006 | `k_star` | `K (Yellow-Orange) Star` |
| 2007 | `m_red_dwarf` | `M (Red dwarf) Star` |
| 2008 | `l_brown_dwarf` | `L (Brown dwarf) Star` |
| 2009 | `t_brown_dwarf` | `T (Brown dwarf) Star` |
| 2010 | `y_brown_dwarf` | `Y (Brown dwarf) Star` |
| 2011 | `t_tauri_star` | `T Tauri Star` |
| 2012 | `herbig_ae_be_star` | `Herbig Ae/Be Star` |
| 2013 | `m_red_giant` | `M (Red giant) Star` |
| 2014 | `m_red_supergiant` | `M (Red super giant) Star` |
| 2015 | `k_yellow_orange_giant` | `K (Yellow-Orange giant) Star` |
| 2016 | `a_blue_white_supergiant` | `A (Blue-White super giant) Star` |
| 2017 | `b_blue_white_supergiant` | `B (Blue-White super giant) Star` |
| 2018 | `f_white_supergiant` | `F (White super giant) Star` |
| 2019 | `g_white_yellow_supergiant` | `G (White-Yellow super giant) Star` |
| 2020 | `c_star` | `C Star` |
| 2021 | `cj_star` | `CJ Star` |
| 2022 | `cn_star` | `CN Star` |
| 2023 | `s_type_star` | `S-type Star` |
| 2024 | `ms_type_star` | `MS-type Star` |
| 2025 | `wolf_rayet_star` | `Wolf-Rayet Star` |
| 2026 | `wolf_rayet_n` | `Wolf-Rayet N Star` |
| 2027 | `wolf_rayet_nc` | `Wolf-Rayet NC Star` |
| 2028 | `wolf_rayet_c` | `Wolf-Rayet C Star` |
| 2029 | `wolf_rayet_o` | `Wolf-Rayet O Star` |
| 2030 | `neutron_star` | `Neutron Star` |
| 2031 | `black_hole` | `Black Hole` |
| 2032 | `supermassive_black_hole` | `Supermassive Black Hole` |
| 2033 | `white_dwarf_d` | `White Dwarf (D) Star` |
| 2034 | `white_dwarf_da` | `White Dwarf (DA) Star` |
| 2035 | `white_dwarf_dab` | `White Dwarf (DAB) Star` |
| 2036 | `white_dwarf_dav` | `White Dwarf (DAV) Star` |
| 2037 | `white_dwarf_daz` | `White Dwarf (DAZ) Star` |
| 2038 | `white_dwarf_db` | `White Dwarf (DB) Star` |
| 2039 | `white_dwarf_dbv` | `White Dwarf (DBV) Star` |
| 2040 | `white_dwarf_dbz` | `White Dwarf (DBZ) Star` |
| 2041 | `white_dwarf_dc` | `White Dwarf (DC) Star` |
| 2042 | `white_dwarf_dcv` | `White Dwarf (DCV) Star` |
| 2043 | `white_dwarf_dq` | `White Dwarf (DQ) Star` |

No richer star alias is inferred from `spectral_class`. That field remains an independent explicit fact.

## 10. Explicitly unresolved observed values

The initial manifest contains exactly:

```json
{
  "spansh_subtype": ["M", "N", "Y"],
  "legacy_subtype_inventory": ["M", "N", "Y"]
}
```

Rationale:

- these bare values were observed in the legacy corpus;
- they may originate from source-specific stellar type tokens rather than the richer Spansh display subtype vocabulary;
- their lineage is not encoded in the legacy value itself;
- Review 2 refuses to collapse them into `m_red_dwarf`, `neutron_star`, or `y_brown_dwarf` merely because that would look plausible.

A later Frontier `StarType` audit may establish source-specific mappings for those tokens. That will be a new manifest revision, not a silent behavior change.

## 11. Manifest invariants

On load, implementation MUST validate:

1. manifest revision exactly `v3-body-subtype-map-1`;
2. exactly 61 canonical subtype entries;
3. exactly 18 Planet canonical entries and 43 Star entries;
4. IDs unique and within signed SMALLINT;
5. planet IDs exactly `1001..1018` as specified;
6. star IDs exactly `2001..2043` as specified;
7. `public_code` unique;
8. every display name non-empty;
9. every alias non-empty;
10. no normalized alias collision across two canonical entries for an applicable source/body type;
11. every intentionally unresolved normalized key does not also occur as a resolved alias in the same source/body-type domain;
12. no canonical entry exists for a modifier such as geological, biological, ringed, terraformable, volcanism, atmosphere, or landable.

Manifest validation is fail-closed at import/test time.

## 12. First production-generation lineage boundary

The real 75-value legacy/public audit is **vocabulary evidence only**.

The legacy `public.bodies.subtype` row itself is not accepted as the production lineage for the next normalized generation because that table is a mixed mutable application store.

The future full generation must consume an explicit retained/re-fetched source record carrying the subtype field, preferably the same Spansh source stream used for the canonical body source run.

Hard precondition before a full generation build:

> The exact raw/source artifact or re-import stream used for subtype population must have source-run identity and provenance compatible with the normalized generation build.

If that source artifact is unavailable, fetch/re-stage a new explicit source run. Do not export 600M mixed legacy subtype values and pretend they are canonical provenance.

## 13. Publication gate for a future canonical generation

The later generation builder must classify every non-empty explicit subtype value as one of:

- resolved alias;
- explicitly unresolved allowlisted token.

Hard publication gates:

```text
unmapped non-empty subtype rows = 0
type-mismatch rows = 0
unreviewed non-empty distinct subtype strings = 0
```

Source-absent subtype rows are allowed and remain state `0`/Unknown; their count and rate must be reported, not converted to a false class.

Explicitly unresolved rows are allowed only for manifest-listed values and remain state `2`/Unknown.

Do not invent an arbitrary maximum source-absent percentage. Completeness is reported as evidence quality; unexpected changes are reviewed against prior source distributions.

## 14. R1 capability consequences

Only `body_subtype_resolution_state = 1` contributes to exact subtype counts.

For a capability row:

```text
body_subtype_unknown_count = count(state != 1 for bodies where subtype identity is applicable)
```

The exact implementation may refine which body types are included in this aggregate during the capability-builder review, but it must never treat unresolved/absent subtype as a known negative.

Examples:

- HMC with geo => HMC count + geological body count;
- true Ammonia World => explicit `ammonia_world` only;
- gas giant with ammonia-based life => gas-giant subtype, never Ammonia World;
- `M` unresolved => Star body remains a Star, subtype-specific count withheld.

## 15. Exact implementation slice authorised after owner acceptance

Only these files may be created/changed:

```text
apps/importer/src/body_subtypes_v1.json
apps/importer/src/v3_body_subtypes.py
tests/test_v3_body_subtypes.py
docs/research/r1-canonical-body-subtype-mapper-completion-2026-08-31.md
```

No other file may change in this implementation slice.

In particular, do not modify:

```text
apps/importer/src/import_spansh.py
apps/api/src/ingest/journal_normaliser.py
sql/r1_v3/001_structural_shell.sql
any v3_* live schema
the retained generation
Finder/API/frontend code
legacy ratings/archetype code
```

If integration into an importer requires changing `import_spansh.py`, that is a later stage after the pure mapper is proven.

## 16. Required test contract

`tests/test_v3_body_subtypes.py` must contain at least:

```text
test_manifest_revision_and_cardinality_are_exact
test_manifest_ids_public_codes_and_aliases_are_unique
test_all_75_audited_source_values_are_accounted_for
test_exactly_72_audited_values_resolve
test_exactly_m_n_y_are_explicitly_unresolved
test_hmc_world_and_body_aliases_resolve_same_identity
test_metal_rich_aliases_resolve_same_identity
test_rocky_ice_aliases_resolve_same_identity
test_earthlike_aliases_resolve_same_identity
test_sudarsky_aliases_resolve_to_same_gas_giant_classes
test_gas_giant_life_hyphen_variants_resolve_same_identity
test_helium_rich_hyphen_variant_resolves_same_identity
test_true_ammonia_world_requires_exact_class_alias
test_ammonia_gas_giant_is_not_ammonia_world
test_unknown_nonempty_string_is_unmapped_not_guessed
test_missing_and_blank_are_source_absent
test_lookup_is_case_insensitive_but_not_punctuation_inferential
test_planet_alias_on_star_body_is_type_mismatch
test_star_alias_on_planet_body_is_type_mismatch
test_frontier_planet_class_rejects_star_aliases
test_frontier_star_type_is_not_supported_by_v1_mapper
test_bare_m_n_y_never_resolve_from_legacy_or_spansh_source
test_modifiers_are_not_present_in_canonical_subtype_manifest
test_repeated_resolution_is_byte_stable
test_manifest_canonical_json_digest_is_stable
```

Additional table-driven tests may cover all canonical aliases.

## 17. Determinism

The module must expose a deterministic canonical manifest serialization and SHA-256 digest.

No timestamps, random IDs, database lookups, network requests, locale-sensitive transforms, or environment-dependent mappings are allowed.

Repeated resolution of the same `(source_kind, body_type_code, raw_value)` must produce byte-identical serialized output.

## 18. Forbidden behavior

The mapper must not import or call:

- database clients;
- network clients;
- legacy Ratings/archetype scorers;
- R1 Fit evaluators;
- source economy heuristics;
- atmosphere/composition classifiers;
- slot prediction;
- body-signal classification.

It is a pure explicit-identity adapter only.

## 19. Completion evidence required after implementation

The completion document must record:

- branch/base/head SHA;
- exactly changed files;
- manifest revision and digest;
- canonical entry count = 61;
- Planet entries = 18;
- Star entries = 43;
- audited distinct source values = 75;
- resolved source values = 72;
- explicit unresolved set = `M`, `N`, `Y`;
- full focused pytest command/result;
- forbidden-import/source scan;
- deterministic repeated-run proof;
- true-Ammonia regression proof;
- HMC alias/composability boundary;
- confirmation that no DB/schema/generation/Finder change occurred.

## 20. What follows this mapper stage

Successful mapper implementation does **not** authorise a full canonical rebuild.

Next sequence:

1. read-only audit availability/provenance of the explicit raw subtype source for a new V3 generation;
2. Review 1 + Review 2 for the tiny additive `v3_vocab.body_subtype` schema/seed and next-generation body-column contract;
3. disposable schema/build tests;
4. separately-authorised creation of a bounded shadow generation or sampled projection;
5. golden/real-system validation;
6. separately-authorised full canonical generation build;
7. only after that, Review 1 + Review 2 for the first R1 capability generation.

The current published V3 generation remains immutable throughout.

## 21. Review-2 acceptance invariants

Before mapper code starts, all of these are locked:

1. subtype identity is explicit-source only;
2. 61 canonical identities account for 72 of the 75 observed strings;
3. bare `M`, `N`, `Y` are intentionally unresolved in v1;
4. no auto-slugging or fuzzy semantic normalisation exists;
5. true Ammonia World is exact explicit identity only;
6. HMC is not replaced by geological/biological/ring/TF modifiers;
7. aliases live in version-controlled manifest, not DB JSONB;
8. future canonical subtype IDs are SMALLINT and type-consistent;
9. source absence remains Unknown;
10. unmapped/type-mismatch values block future publication;
11. legacy/public subtype rows are audit evidence, not canonical production lineage;
12. current retained normalized generation is never altered in place;
13. this implementation slice is pure mapper/manifest/tests/docs only;
14. capability generation and Finder remain untouched.

## 22. Decision

After owner acceptance, implement only the four-file mapper slice above.

No live database write and no canonical generation build is authorised by this Review 2.