# CRE rulebook — pinned release

This folder holds the colonisation rulebook published by the Colonisation
Research Engine (CRE, repository `brianstewart377-rgb/elite-dangerous-research-engine`).
Owner decision D1 (2026-10-21, [`docs/ROADMAP.md`](../../../ROADMAP.md)) makes the
CRE a versioned rulebook that ED-Finder reads. This is the release ED-Finder
currently reads: `cre-knowledge-v0.5.0`, 29 rules, from immutable CRE commit
`db7ee07066239382b030837337c90d0159152f89`.

It is reference data. Being here does not change any score, mechanic or frozen
ruleset. Rule changes are made in the CRE, approved by the owner, released under
a new tag, and then pinned here.

## Files

| File | What it is |
|---|---|
| `rulebook.json` | A byte-for-byte copy of the CRE's `exports/rulebook.json` at the pinned commit. |
| `apps/api/src/cpe/data/rulebook.json` (repository root) | Byte-identical runtime copy read by the pure CPE module. |
| `pin.json` | The release name (`release_tag`, as written inside `rulebook.json`), the CRE commit the copy was taken from, the source path and the SHA-256 of `rulebook.json`. The commit is authoritative. |

The SHA-256 in `pin.json` must match both this copy and the CRE's own
`exports/export_manifest.json` at that commit. `tests/test_cre_rulebook_parity.py`
refuses a copy that does not match its pin. `tests/test_cpe_rulebook_copy.py`
also requires the runtime copy to match both the pin and these exact bytes.

## How to read a rule

Each rule has a permanent ID (`RB-0003`), a plain-English statement, exact
values where the sources give them, a status, and quoted sources with page
numbers. Statuses:

| Status | Meaning |
|---|---|
| `Confirmed` | A Frontier first-party source states it, or CRE evidence verified it in game. |
| `Likely` | The community guide states it and a first-party source supports part of it. |
| `Extracted` | Only the community guide (or one other non-first-party source) states it. |
| `Disputed` | Sources disagree; the statement gives the working rule and a `C-` contradiction record gives both sides. |

Mega Guide page numbers in the rulebook are PDF page numbers, the same as for
the guide text in [`../sources/mega-guide-v2.3.0/`](../sources/mega-guide-v2.3.0/README.md).

## Parity test

`tests/test_cre_rulebook_parity.py` compares the tables ED-Finder hard-codes
with this rulebook:

- construction-point escalation (`RB-0003`) against `apps/api/src/mechanics/cp_rules.py`;
- link strengths and modifier size (`RB-0015`, `RB-0016`, `RB-0019`) against
  `apps/api/src/mechanics/link_rules.py`;
- body economies and modifiers (`RB-0010`, `RB-0011`) against Ratings V4
  (`apps/api/src/domain/ratings_v4.py`) and the V2 planner's
  `apps/api/src/domain/colonisation_rules.py`;
- inherited strength and stacking (`RB-0012`) against Ratings V4;
- strong-link modifiers (`RB-0018`) against the Ratings V4 rules, by running
  `opportunities_from_facts` on probe bodies.

Every difference is either absent or listed, with its reason, in the test's
`KNOWN_DIFFERENCES`. A new difference fails the test, and so does a listed one
that has gone away. Most listed differences are in the V2 planner code (to be
replaced by the D3 construction-point calculator and the D2 CPE module) or are
frozen Ratings V4.0 decisions recorded in the Mega Guide audit
([`docs/development/evidence/2026-10-21-mega-guide-v2.3-mechanics-audit.md`](../../../development/evidence/2026-10-21-mega-guide-v2.3-mechanics-audit.md))
for Ratings V4.1.

## Updating the pin

1. In the CRE, merge the rule changes (and tag the release
   `cre-knowledge-vX.Y.Z`).
2. Copy that commit's `exports/rulebook.json` here and to
   `apps/api/src/cpe/data/rulebook.json` unchanged.
3. Update `pin.json`: the release name, the CRE commit, and the SHA-256 from
   that commit's `exports/export_manifest.json` (check it with `sha256sum`).
4. Update the SHA-256 in `assets/PROVENANCE.json`.
5. Run `tests/test_cre_rulebook_parity.py` and record every new or resolved
   difference in `KNOWN_DIFFERENCES` with its reason.

## Licence

The rulebook is the repository owner's CRE work. It quotes short passages from
the Elite Dangerous Colonization Mega Guide (CMDR Mechan and contributing CMDRs,
CC BY-SA 4.0) and from Frontier Developments' update notes, and it describes
Elite Dangerous game mechanics. It is held under ED-Finder's Frontier
noncommercial fan-project posture; see
[`THIRD_PARTY_NOTICES.md`](../../../../THIRD_PARTY_NOTICES.md) and
[`assets/PROVENANCE.json`](../../../../assets/PROVENANCE.json).
