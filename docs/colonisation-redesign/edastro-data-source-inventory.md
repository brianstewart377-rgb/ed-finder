# ED Astro Data-Source Inventory

## Scope

Recorded 2026-07-22 from ED Astro's published
[file directory](https://edastro.com/mapcharts/files.html), machine-readable
[`spreadsheets.csv`](https://edastro.com/mapcharts/files/spreadsheets.csv), and
[data-source statement](https://edastro.com/datasources.html). This is a source
assessment, not authorization to ingest or redistribute the files.

The directory currently lists 134 files and about 335.58 GiB of advertised
uncompressed source data. It spans nine classifications:

| Classification | Files | Advertised size | Rows |
| --- | ---: | ---: | ---: |
| ELWS | 6 | 0.28 GiB | 671,489 |
| Gas giants | 8 | 9.47 GiB | 54,132,992 |
| Other | 22 | 3.11 GiB | 89,306,590 |
| Planet dumps | 21 | 240.46 GiB | 1,012,435,747 |
| Planets | 23 | 3.45 GiB | 27,428,549 |
| Star dumps | 17 | 74.67 GiB | 381,025,454 |
| Stars | 18 | 0.69 GiB | 5,965,778 |
| Systems | 16 | 1.38 GiB | 17,934,744 |
| Seven-day dumps | 3 | 2.07 GiB | 2,269,699 |

ED Astro says most data is built from EDDN submissions with periodic EDSM gap
filling, plus named community sources including the Catalogue of Galactic
Nebulae, DSSA, GMP, IGAU, Inara, and Spansh. It warns that discovery data is
not a representative sample of the full game galaxy and that spreadsheet
columns may be reordered or expanded. Any importer must therefore identify
columns by header and preserve source/update metadata.

## Product-Value Triage

| Priority | Dataset | Current size / rows | ED-Finder use | Decision |
| --- | --- | ---: | --- | --- |
| A | Nebulae coordinates | 460 KiB / 5,835 | Optional Explore landmark layer and orientation | Evaluate after reuse terms and coordinate schema are confirmed |
| A | Combined POIs | 1.3 MiB / 11,243 | Optional inspectable landmarks and exploration context | Require row-level source/provenance handling before use |
| A | Region ID keys | under 1 KiB / 42-43 | Cross-check the existing 42-region contract | Validation-only; ED-Finder already has the canonical names |
| B | Colony candidates | 55 MiB / 493,674 | External comparison against ED-Finder candidate logic | Research/validation input, never canonical ranking truth |
| B | Sector list and discovery dates | about 2 MiB / 12,034 each | Coverage and freshness context | Consider server-side research, not a browser payload |
| B | Extreme edges and catalog systems | 0.3-15 MiB | Galaxy orientation and named-system discovery | Later optional layer after provenance review |
| C | Seven-day JSONL dumps | 111 MiB-1.5 GiB each | Freshness/reconciliation research | Importer-side only; redundant with existing EDDN/EDSM lanes |
| C | Full body/star/planet dumps | up to 85 GiB per file | Offline research | Do not add to Stage 26 map scope or ship to clients |
| C | 10-ly region coordinate map | 1.2 GiB / 81,009,000 | Region lookup cross-check | Do not ship; the current RLE source is far smaller and sufficient |

## Catalogue Of Galactic Nebulae

The owner-supplied workbook contains five sheets. Its published lists hold 167
procedurally generated nebulae, 5,492 procedurally generated planetary nebulae,
and 189 real nebulae, plus the 42-region crosswalk and a 1,465-row work-in-
progress sheet. The catalogue records reference-system names rather than map
coordinates; ED Astro's derived coordinates file is therefore the practical
map-layer candidate. WIP rows must not be presented as accepted catalogue
entries.

## Rights Boundary

ED Astro's general data-source page carries an All Rights Reserved footer. Its
GEC pages separately state CC BY-NC-SA 3.0, and individual map images may carry
their own CC notices; those narrower notices must not be assumed to cover every
Mapcharts CSV. Before ED-Finder vendors, republishes, or routinely mirrors a
file, record explicit file-level reuse terms or obtain permission from ED
Astro/CMDR Orvidius and retain the upstream source credits. Until then, these
files are evaluation and comparison inputs only.

## Next Bounded Check

Start with the two small, high-value candidates: inspect the nebula-coordinate
and combined-POI schemas, identify every source/credit field, and request or
locate explicit reuse terms. Do not open a bulk-download or production-ingest
lane as part of Stage 26E map cutover.
