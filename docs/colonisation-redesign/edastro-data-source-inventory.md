# EDAstro Mapcharts data-source inventory

## Scope and decision

Refreshed 2026-09-14 from EDAstro's published
[file directory](https://edastro.com/mapcharts/files.html), machine-readable
[`spreadsheets.csv`](https://edastro.com/mapcharts/files/spreadsheets.csv), and
[data-source statement](https://edastro.com/datasources.html).

ED-Finder is non-commercial. The owner directed the project to consume useful
purpose-published Mapcharts CSVs and to credit EDAstro, CMDR Orvidius, and the
named upstream data sources where appropriate. Every adopted feed must retain
its source URL, retrieval/freshness metadata, content hash, source attribution,
and the publisher's rights notice. Derived presentation must remain labelled as
derived rather than being promoted to canonical game truth.

The directory currently advertises 136 files, about 343.04 GiB of uncompressed
data and 1,623,408,952 data rows. The totals below exclude each CSV header row.

| Classification  | Files | Advertised size |     Data rows |
| --------------- | ----: | --------------: | ------------: |
| ELWs            |     6 |        0.29 GiB |       681,070 |
| Gas giants      |     8 |        9.68 GiB |    55,316,736 |
| Other           |    23 |        3.15 GiB |    89,543,653 |
| Planet dumps    |    21 |      246.22 GiB | 1,034,199,705 |
| Planets         |    23 |        3.51 GiB |    27,972,891 |
| Star dumps      |    17 |       76.28 GiB |   389,652,341 |
| Stars           |    18 |        0.69 GiB |     6,087,900 |
| Systems         |    17 |        1.38 GiB |    17,940,784 |
| Seven-day dumps |     3 |        1.84 GiB |     2,013,872 |

EDAstro says most data is built from real-time EDDN submissions with periodic
EDSM gap filling. It also names the Catalogue of Galactic Nebulae, DSSA, GMP,
IGAU, Inara, Spansh, and other community sources. The publisher warns that this
is a commander-submission sample, not a complete representation of the game,
and that spreadsheet columns may be reordered or extended. Importers must map
columns by header and preserve the source/update metadata.

## Enrichment decisions

| Priority   | Dataset                          |      Current published size / rows | What it adds to ED-Finder                                                                                    | Decision                                                                                               |
| ---------- | -------------------------------- | ---------------------------------: | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Shipped    | Nebulae Coordinates              |                    461 KiB / 5,842 | Complete inspectable nebula inventory at catalogue coordinates                                               | Adopted as a deterministic browser asset with visible EDAstro / CMDR Orvidius credit                   |
| P1         | Combined Points of Interest      |        1.2 MiB / 11,228 advertised | Named landmarks, scenery, Guardian sites, phenomena, outposts, megaships, and exploration context            | Best next galaxy overlay; build a provenance-aware, deduplicated import before display                 |
| P1         | Codex Life-forms and rarities    |                807 MiB / 4,867,686 | Global discovery context to complement ED-Finder's personal journal-derived Codex and exobiology projections | High-value server-side index; never ship the raw file to the browser                                   |
| P2         | DSSA Carrier Deployments         |                       12 KiB / 101 | Deep-space support status, carrier identity, deployment and last-seen system                                 | Add only as transient exploration support; join system names to canonical coordinates                  |
| P2         | Catalog Systems                  |                   15 MiB / 245,622 | Non-procedural names, EDSM identity, region and coordinates                                                  | Reconciliation/alias input only; do not duplicate the 186M-row canonical systems table                 |
| P2         | Extreme Edges                    |                    282 KiB / 3,000 | Curated navigation targets at the six galactic extremes                                                      | Useful as a Discovery preset or validation set, not canonical system data                              |
| P3         | Fleet Carriers                   |                    20 MiB / 89,888 | Services and last-seen location for mobile infrastructure                                                    | Optional freshness-bound overlay only; existing policy forbids treating carriers as permanent stations |
| Research   | Colonization Candidates          |                   58 MiB / 524,769 | External comparison with ED-Finder's candidate logic                                                         | Validation benchmark only; EDAstro's derived heuristic must not become ED-Finder ranking truth         |
| Validation | Region ID/name keys              |                under 1 KiB / 42-43 | Cross-checks region identity                                                                                 | No product ingest; ED-Finder already has the exact 42-region contract                                  |
| Validation | Region Coordinate Map            |               1.2 GiB / 81,009,000 | 10-LY region lookup reference                                                                                | No product ingest; the existing compressed exact-region asset is materially smaller                    |
| Skip       | Stations                         | 83 MiB / 445,311, dated 2025-04-30 | Station facts                                                                                                | Stale and redundant with the EDSM/Spansh station evidence lanes                                        |
| Skip       | Body/star subsets and full dumps |             KiB to 87 GiB per file | Precomputed rare-body lists or broad catalogue duplication                                                   | Query ED-Finder's canonical bodies/systems where possible; use selected subsets only as QA benchmarks  |
| Skip       | Seven-day JSON dumps             |         98 MiB to 1.4 GiB per file | Recent systems, stars, and planets                                                                           | Redundant with the existing EDDN/EDSM/Spansh ingestion architecture                                    |

## Combined POI findings

The live `edsmPOI.csv` fetched during this audit contained 11,230 rows while the
directory manifest advertised 11,228. That normal publication race is evidence
that an importer must record its own retrieved timestamp, row count and SHA-256
rather than assuming the directory's count is an immutable contract.

The feed columns are `POI Type`, `ID`, `Name`, `X`, `Y`, `Z`,
`Reference System`, and `Notes`. All 11,230 observed rows had coordinates. The
largest observed groups were 5,839 planetary nebulae, 1,752 carriers, 584
nebulae, 460 minor POIs, 362 Guardian entries, 214 megaships and 200 planet
features. There were 123 duplicated `POI Type + ID` groups, so the feed cannot
be copied directly into a unique-ID product layer.

The CSV has no explicit per-row `Source` column even though the publishing page
describes it as a combination of EDSM, GMP, DSSA and IGAU sources. The importer
therefore needs an audited mapping from type/ID namespace to upstream source,
plus a deterministic fallback of `EDAstro combined POI feed / source unknown`
when a row cannot be attributed more narrowly. Nebula rows already supplied by
the dedicated coordinate asset must be reconciled rather than rendered twice.

## Codex and carrier boundaries

ED-Finder already stores personal `CodexEntry`, organism sampling and sale facts
from player journals. The global Codex file is still additive because it can
answer "where has this phenomenon been reported?" rather than only "where have
I observed it?". At 4.87 million rows it needs a staged, indexed server-side
pipeline keyed by Codex ID, region, system address and coordinates.

The dedicated DSSA feed provides carrier callsign, name, commander, status,
deployment location, last-seen location and last-seen time, but no coordinates.
It is suitable for a small transient support overlay after resolving system
names. The general fleet-carrier feed includes coordinates, services and
freshness, but remains mobile evidence and must never be merged into permanent
station or colonisation-slot truth.

## Attribution and ingestion contract

Every future EDAstro feed adopted by ED-Finder must:

1. retain the Mapcharts catalogue URL and exact CSV URL;
2. record retrieval time, upstream timestamp/`Last-Modified`, byte size, row
   count and SHA-256;
3. map columns by header and fail closed on missing required columns;
4. preserve stable source identity and distinguish source facts from derived
   ED-Finder fields;
5. display `EDAstro / CMDR Orvidius` near user-visible Mapcharts-derived data;
6. additionally credit named upstream sources such as EDDN, EDSM, GMP, DSSA,
   IGAU or the Catalogue of Galactic Nebulae when the feed or row identifies
   them;
7. retain the publisher's displayed rights notice without relabelling a feed as
   Creative Commons unless that specific feed has such terms; and
8. keep browser payloads bounded, using server-side indexed tables for large or
   volatile feeds.

## Recommended next slice

Build the Combined POI layer first. It has the best value-to-size ratio and
directly enriches the new Babylon galaxy map. The bounded slice should define
the source namespace mapping, deduplicate the current feed, suppress nebula
duplicates, expose category toggles and click-to-info, and show EDAstro plus
upstream source credits. Follow it with a separately designed global Codex
server index; do not combine the 4.87-million-row work with the small POI slice.
