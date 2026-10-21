# Elite Dangerous Colonization Mega Guide — v2.3.0 text reference

This folder holds a plain-text copy of the community guide that
[`source-priority.md`](../../source-priority.md) names as ED-Finder's primary
colonisation mechanics authority. It is reference material for citation and
review. It is not ED-Finder execution authority and does not change any
mechanics, scoring or frozen ruleset by being here.

## What it is

| Field | Value |
|---|---|
| Title | Elite Dangerous Colonization Mega Guide |
| Author | Written by CMDR Mechan, with input from dozens of CMDRs ("with input/additions/comments/suggestions/corrections from dozens of CMDRs across a large number of communities") |
| Version | 2.3.0 (title page) |
| Revision table, top row | 2.4.0, status "WIP", game version 4.2.2.0 (10/11/25) |
| Last released row | 2.3.0, October 31, 2025, game version 4.2.1.2 (16/10/25) |
| Supplied | By the repository owner, 2026-10-21, as a 121-page PDF |
| Licence | CC BY-SA 4.0 — <https://creativecommons.org/licenses/by-sa/4.0/> |

The guide's own caveat on its title page: the 4.2.2.0 patch-note change (a
nerf announced at -70% and later revised to -25%) is **not incorporated** in
this version, pending news on whether it will be withdrawn. Treat any figure the
4.2.2.0 patch touches as possibly out of date.

## Licence and attribution (quoted from the guide)

> This Elite Dangerous Colonization Mega Guide was created using assets and
> imagery from Elite Dangerous, with the permission of Frontier Developments
> plc, for non-commercial purposes. It is not endorsed by nor reflects the views
> or opinions of Frontier Developments and no employee of Frontier Developments
> was involved in the making of it. This guide is made available to you under
> CC BY-SA 4.0.

ED-Finder redistributes the text below under the same licence (CC BY-SA 4.0),
with attribution to CMDR Mechan and the contributing CMDRs. ED-Finder is not
endorsed by Frontier Developments either. No Elite Dangerous assets or imagery
from the guide are included here (see below).

## The files

| File | What it is | SHA-256 |
|---|---|---|
| Source PDF (not committed, 95,643,300 bytes; `Elite_Dangerous_Colonization_Mega_Guide-1.pdf`) | The owner-supplied original | `aaabd23cf5ed6161a9b2dadb76a6a7d6b385e4d8c73e87de3bca0339087b69d5` |
| [`mega-guide-v2.3.0.txt`](./mega-guide-v2.3.0.txt) | Text extracted from that PDF | `359e8fd00d3df3da0f10562f19012c7f71d06cf82933d09bfcf89d1fb296fbd3` |

The PDF itself is not committed because of its size (about 95 MB). Anyone
holding a copy can confirm it is the same document by comparing its SHA-256 with
the value above.

`.gitattributes` marks the `.txt` as `-text` so Git never rewrites its line
endings; its checksum therefore stays the one listed above on every checkout.

The `.txt` is registered in [`assets/PROVENANCE.json`](../../../../../assets/PROVENANCE.json)
with this SHA-256 and its rights chain, and credited in
[`THIRD_PARTY_NOTICES.md`](../../../../../THIRD_PARTY_NOTICES.md). CI runs
`scripts/checks/asset_provenance.py`, which fails if the file's checksum
drifts from the manifest.

## How the text was made, and what is missing

- It is an **unmodified machine extraction**: `pdftotext -layout` (poppler
  24.02.0) run on the PDF above. Nothing was corrected, reflowed or removed.
- Layout spacing is kept as the extractor produced it, so tables made of text
  come out as columns of spaces and can be hard to read.
- Every page except the title page ends with the guide's own footer line
  (`Elite Dangerous Colonization Mega Guide ... Page N`), and each of the 121
  pages ends with a form-feed character. The guide's typography also leaves zero-width
  spaces (U+200B) in many lines.
- **Images are not included.** Screenshots, diagrams, and any table that is an
  image in the PDF are absent from the text. When a claim depends on one of
  those, check the PDF itself.

## Page numbers

Page numbers cited anywhere in this repository for the Mega Guide (for example
"guide p50") are **PDF page numbers**. They match each page's own "Page N"
footer and the form-feed page breaks in the `.txt`. The guide's table of
contents is off by one in places, so do not use it to look up a cited page.
