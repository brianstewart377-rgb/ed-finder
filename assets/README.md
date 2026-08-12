# Asset Provenance Policy

Every shipped asset needs a per-file rights chain in
[`PROVENANCE.json`](PROVENANCE.json) before merge. The manifest covers every
tracked file under `frontend/public/` and any other asset-like source that is
embedded or redistributed by ED-Finder, including inline shaders, runtime web
fonts, media, data, and adapted third-party snippets.

`approval_date` records the date on which the evidence was accepted for the
stated `rights_status`; it is not a legal opinion. A content change invalidates
the recorded SHA-256 and requires a fresh review. Package-manager dependencies
remain governed by their lockfiles and package notices; copied snippets must be
added here even when their original package is also in a lockfile.

## Shipping rules

1. Add the asset only after recording its exact file path, source URL, creator,
   license, required attribution, Frontier-derived status, approval date, and
   verification evidence. Do not use `unknown` as permission to ship.
2. Prefer project-original geometry, procedural generation, or sources with
   clear CC0, permissive open-source, or SIL OFL rights. Preserve required
   notices and reserved font names.
3. Treat a repository's code license and every media file's rights separately.
   A creator or community catalogue must supply a per-file credit and a license
   or written grant that covers ED-Finder's use.
4. EDAssets is a discovery and provenance catalogue only. Its repository's MIT
   license and its statement about Frontier permission do not automatically
   license individual media files or transfer that permission to ED-Finder.
5. Run `python scripts/checks/asset_provenance.py` before review. CI runs the
   same guard and rejects missing public-file entries, stale entries, invalid
   fields, missing notice references, and SHA-256 drift.

## Frontier material

Frontier's [Elite Dangerous media guidance](https://customersupport.frontier.co.uk/hc/en-us/articles/4404292442642-How-can-I-use-Elite-Dangerous-media)
permits the covered community and fan uses only for noncommercial purposes,
requires clear Frontier attribution, prohibits misleading or impersonating
Frontier, and requires advance permission for promotional or commercial use.
ED-Finder must use the official long-form community-site attribution and must
not imply affiliation or endorsement.

Frontier permission never replaces another creator's rights. A screenshot,
fan illustration, EDAssets file, or other contribution needs both the relevant
Frontier treatment and the named creator's per-file permission and credit.
Every `frontier_derived: true` entry therefore remains
`commercial_use_approved: false` unless a separate written commercial grant is
recorded. Before any commercial use, re-review every manifest row and obtain
all missing creator and Frontier permissions.

## Audit completed 2026-08-12

The audit enumerated tracked public files and media extensions, searched source
and history for font, image, audio, shader, license, copied-code, EDAssets, and
Frontier references, inspected SVG and shader source, calculated SHA-256 hashes,
read image metadata, and checked upstream license/credit pages.

- Images: five public images are recorded. The favicon and PWA icon are
  repository-authored SVGs. The region SVG derives from the audited MIT region
  data and Frontier material. Both Coalsack JPEGs are resized/recompressed
  derivatives of ESO image `eso1539c`, identified by their retained metadata.
- Fonts: no font binaries are bundled. Orbitron, Manrope, and JetBrains Mono
  are loaded from Google Fonts at runtime and are recorded under SIL OFL 1.1.
- Sounds: no bundled or source-referenced audio assets were found.
- Shaders: six inline GLSL programs in two TypeScript files are original,
  procedural source. No standalone shader files or copied shader snippets were
  found.
- Third-party code/data: the region lookup adaptation and its RLE data derive
  from `klightspeed/EliteDangerousRegionMap`; the MIT notice and the separate
  Frontier noncommercial boundary are recorded. The exploration-value module
  is original code implementing a community-researched mathematical formula
  and factual game constants; its source and Frontier boundary are recorded.
  No copied third-party source snippets were identified by source, notice, or
  history searches.
- EDAssets: no EDAssets media file is bundled. Prior EDAssets work in this
  repository is research/catalogue review only and grants no reusable rights.

The extension sweep also found 29 tracked, non-shipping QA screenshots under
`artifacts/map-foundation/`, `docs/development/evidence/`, and
`frontend/map-foundation/e2e/visual.spec.ts-snapshots/`. They are ED-Finder
test/evidence captures, are not read by the application build, and are not
copied into `frontend/dist`. They are excluded from the shipped-asset manifest
and CI inventory. Because some captures depict the Frontier-derived region map
or ESO background, they must not be repurposed for commercial media without a
new per-file review and the applicable credits.

See [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for distributed
credits and license notices. Re-run the audit when asset locations, build
pipelines, remote font imports, or commercial posture changes.
