#!/usr/bin/env python3
"""
ED:Finder — Permanent Exhaustive Audit Script
=============================================
Run after every release to catch field-name mismatches, filter logic bugs,
and schema inconsistencies between:
  - localdb/import_systems.py  (schema + body_row)
  - localdb/local_search.py    (search, normalization)
  - frontend/index.html        (BODY_SLIDERS, BODY_SUBTYPE_MAP, filters, rating, economy)

Usage:
    python3 localdb/audit.py                        # from repo root
    python3 localdb/audit.py --verbose              # show PASS items too
    python3 localdb/audit.py --fix-report           # exit 1 if any bugs found (CI use)

Exit code: 0 = all clear, 1 = bugs found (only with --fix-report)
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
PY   = (ROOT / "localdb"  / "local_search.py").read_text(encoding="utf-8")
IMP  = (ROOT / "localdb"  / "import_systems.py").read_text(encoding="utf-8")


# ── Helpers ──────────────────────────────────────────────────────────────────
bugs:  list[tuple[str, str]] = []   # (id, message)
notes: list[tuple[str, str]] = []   # (id, message) — warnings / limitations


def BUG(bid: str, msg: str) -> None:
    bugs.append((bid, msg))


def NOTE(bid: str, msg: str) -> None:
    notes.append((bid, msg))


def PASS(bid: str, msg: str, verbose: bool) -> None:
    if verbose:
        print(f"  ✅ {bid}: {msg}")


# ─────────────────────────────────────────────────────────────────────────────
def run_audit(verbose: bool = False) -> None:

    # ── A: BODY_SLIDERS / BODY_SUBTYPE_MAP key consistency ───────────────────
    # Extract frontend BODY_SLIDERS keys
    slider_keys = re.findall(r"\{\s*key:\s*'([^']+)'", HTML)
    # Extract BODY_SUBTYPE_MAP values
    subtype_map_values = set(re.findall(r":\s*'([a-zA-Z]+)'\s*,?\s*//.*Spansh|:\s*'([a-zA-Z]+)'\s*[,}]", HTML))
    # Flatten
    stm_values: set[str] = set()
    for pair in re.findall(r"'[^']*'\s*:\s*'([^']+)'", HTML[HTML.find("BODY_SUBTYPE_MAP"):HTML.find("BODY_SUBTYPE_MAP")+3000]):
        stm_values.add(pair)

    # Backend SUBTYPE_MAP values
    backend_map_block = PY[PY.find("SUBTYPE_MAP = {"):PY.find("}", PY.find("SUBTYPE_MAP = {"))+500]
    backend_keys: set[str] = set(re.findall(r":\s*\"([^\"]+)\"", backend_map_block))
    backend_keys.update(re.findall(r":\s*'([^']+)'", backend_map_block))

    # Check ammonia
    if '"Ammonia world": "ammonia"' in PY or '"Ammonia world": "ammonia"' in PY:
        PASS("A1", "Backend 'Ammonia world' → 'ammonia' matches frontend", verbose)
    elif '"Ammonia world": "aw"' in PY:
        BUG("A1", "Backend SUBTYPE_MAP uses 'aw' for Ammonia world — frontend expects 'ammonia'.")
    else:
        # Try alternate quoting
        if re.search(r'"Ammonia world"\s*:\s*"ammonia"', PY) or re.search(r"'Ammonia world'\s*:\s*'ammonia'", PY):
            PASS("A1", "Backend 'Ammonia world' → 'ammonia' ✓", verbose)
        else:
            BUG("A1", "Cannot confirm backend Ammonia world key — check SUBTYPE_MAP in local_search.py")

    # Check White Dwarf substring handling
    if '"White Dwarf" in sub' in PY or "'White Dwarf' in sub" in PY:
        PASS("A2", "Backend White Dwarf uses substring match ✓", verbose)
    else:
        BUG("A2", "Backend _count_body_types lacks substring match for White Dwarf variants.")

    # ── B: Distance slider defaults ────────────────────────────────────────
    # HTML default value
    dist_default_html = re.search(r'id="dist-slider"[^>]+value="(\d+)"', HTML)
    if dist_default_html and dist_default_html.group(1) == "50":
        PASS("B1", "dist-slider HTML default = 50 ✓", verbose)
    else:
        BUG("B1", f"dist-slider HTML default is {dist_default_html.group(1) if dist_default_html else 'NOT FOUND'} — expected 50.")

    # getSearchParams fallback
    gsp_fallback = re.search(r"dist-slider.*?value.*?\|\|'?(\d+)'?", HTML[HTML.find("getSearchParams"):HTML.find("getSearchParams")+500])
    # simpler check
    if "'15'" in HTML[HTML.find("getSearchParams"):HTML.find("getSearchParams")+500]:
        BUG("B2", "getSearchParams() has fallback '15' — should be '50'.")
    else:
        PASS("B2", "getSearchParams distance fallback not '15' ✓", verbose)

    # countActiveFilters max-dist default
    caf_block = HTML[HTML.find("countActiveFilters"):HTML.find("countActiveFilters")+800]
    if "!== 15" in caf_block or "!= 15" in caf_block:
        BUG("B3", "countActiveFilters maxDist comparison uses 15 — should be 50.")
    else:
        PASS("B3", "countActiveFilters maxDist comparison ≠ 15 ✓", verbose)

    # Active-filter strip fallback
    filter_strip = HTML[HTML.find("activeItems"):HTML.find("activeItems")+1500] if "activeItems" in HTML else ""
    if "||15)" in filter_strip or "|| 15)" in filter_strip:
        BUG("B4", "Active-filter strip maxDist fallback uses ||15 — should be ||50.")
    else:
        PASS("B4", "Active-filter strip fallback ≠ 15 ✓", verbose)

    # ── C: Toggle element IDs ────────────────────────────────────────────
    required_toggles = ["tog-bio", "tog-geo", "tog-ring", "tog-terra",
                        "tog-volc", "tog-notidal", "tog-pop-zero"]
    for tid in required_toggles:
        if f'id="{tid}"' in HTML:
            PASS(f"C-{tid}", f"Toggle {tid} present ✓", verbose)
        else:
            BUG(f"C-{tid}", f"Toggle element id='{tid}' missing from HTML.")

    # ── D: Quick-filter pill IDs ─────────────────────────────────────────
    # smin-elw and smin-ww are generated dynamically by renderBodySliders
    if "smin-${s.key}" in HTML or 'id="smin-${s.key}"' in HTML:
        PASS("D1", "Quick-filter smin-elw/smin-ww generated dynamically ✓", verbose)
    else:
        BUG("D1", "renderBodySliders does not generate 'smin-${s.key}' IDs — quick-filter pills will fail.")

    # ── E: Rating slider IDs ─────────────────────────────────────────────
    if 'id="min-rating-slider"' in HTML and 'id="max-rating-slider"' in HTML:
        PASS("E1", "Rating slider IDs min/max-rating-slider present ✓", verbose)
    else:
        BUG("E1", "Rating slider IDs missing — expected min-rating-slider / max-rating-slider.")

    # _attachIncrementalSearch uses correct IDs
    inc_block = HTML[HTML.find("_attachIncrementalSearch"):HTML.find("_attachIncrementalSearch")+500]
    if "'min-rating'" in inc_block and "'min-rating-slider'" not in inc_block:
        BUG("E2", "_attachIncrementalSearch uses 'min-rating' — should be 'min-rating-slider'.")
    elif "'min-rating-slider'" in inc_block:
        PASS("E2", "_attachIncrementalSearch uses correct 'min-rating-slider' ✓", verbose)

    # ── F: tidal lock field propagation ──────────────────────────────────
    # Schema column
    if "is_tidal_lock" in IMP:
        PASS("F1", "import_systems bodies schema has is_tidal_lock column ✓", verbose)
    else:
        BUG("F1", "bodies table schema missing is_tidal_lock column in import_systems.py.")

    # _body_row extracts it
    if "rotationalPeriodTidallyLocked" in IMP:
        PASS("F2", "import_systems _body_row extracts rotationalPeriodTidallyLocked ✓", verbose)
    else:
        BUG("F2", "import_systems _body_row does NOT extract rotationalPeriodTidallyLocked.")

    # local_search SELECTs is_tidal_lock
    if "is_tidal_lock" in PY:
        PASS("F3", "local_search.py SELECTs is_tidal_lock ✓", verbose)
    else:
        BUG("F3", "local_search.py does not SELECT is_tidal_lock — togNotidal/economy scoring broken.")

    # local_search normalizes it to is_rotational_period_tidally_locked
    if "is_rotational_period_tidally_locked" in PY:
        PASS("F4", "local_search.py normalizes to is_rotational_period_tidally_locked ✓", verbose)
    else:
        BUG("F4", "local_search.py does not output is_rotational_period_tidally_locked in body dicts.")

    # ── G: surface_temp normalization ────────────────────────────────────
    if "surface_temperature" in PY:
        PASS("G1", "local_search.py normalizes surface_temp → surface_temperature ✓", verbose)
    else:
        BUG("G1", "local_search.py never renames surface_temp → surface_temperature — body pill temp shows '—'.")

    # ── H: walkable count consistency ────────────────────────────────────
    # countBodyTypes (line ~3821) should check is_rotational_period_tidally_locked
    walkable_line = ""
    for line in HTML.splitlines():
        if "counts.walkable" in line and "is_landable" in line:
            walkable_line = line
            break
    if "is_rotational_period_tidally_locked" in walkable_line:
        PASS("H1", "countBodyTypes walkable checks tidal lock ✓", verbose)
    else:
        BUG("H1", "countBodyTypes walkable does NOT check tidal lock — mismatch with _showMapDetail walkable count.")

    # ── I: b.landable vs b.is_landable ────────────────────────────────────
    if "(b.landable ||" in HTML or "(b.landable||" in HTML:
        BUG("I1", "Frontend uses b.landable (bare) — should be b.is_landable. Affects suggestEconomy tidal penalty.")
    else:
        PASS("I1", "No bare b.landable references ✓", verbose)

    # ── J: rings display in body pill ────────────────────────────────────
    if "b.rings.join(" in HTML:
        BUG("J1", "Body pill uses b.rings.join() — rings are {type:'...'} objects not strings → shows '[object Object]'.")
    else:
        PASS("J1", "rings display handles object array correctly ✓", verbose)

    # ── K: volcanism dual-key check ──────────────────────────────────────
    if "volcanism_type || b.volcanism" in HTML or "b.volcanism_type || b.volcanism" in HTML:
        PASS("K1", "togVolc checks both volcanism_type and volcanism ✓", verbose)
    else:
        BUG("K1", "togVolc volcanism check may not cover both field names (volcanism_type vs volcanism).")

    # ── L: atmosphere dual-key check ─────────────────────────────────────
    if "(b.atmosphere || b.atmosphere_type)" in HTML:
        PASS("L1", "countBodyTypes walkable checks both atmosphere field names ✓", verbose)
    else:
        BUG("L1", "walkable check may miss atmosphere_type field name.")

    # ── M: _flush_galaxy_batch column count vs INSERT columns ────────────
    # Count VALUES placeholders vs listed columns
    flush_match = re.search(
        r"INSERT OR REPLACE INTO bodies\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
        IMP, re.DOTALL
    )
    if flush_match:
        cols = [c.strip() for c in flush_match.group(1).split(",") if c.strip()]
        vals = [v.strip() for v in flush_match.group(2).split(",") if v.strip()]
        if len(cols) == len(vals):
            PASS("M1", f"_flush_galaxy_batch column count ({len(cols)}) matches placeholder count ({len(vals)}) ✓", verbose)
        else:
            BUG("M1", f"_flush_galaxy_batch column count ({len(cols)}) ≠ placeholder count ({len(vals)}) — INSERT will fail.")
    else:
        BUG("M1", "Could not find INSERT OR REPLACE INTO bodies in import_systems.py.")

    # ── N: _body_row tuple length vs INSERT column count ─────────────────
    # Count return tuple items in _body_row (count commas at same indentation level)
    br_section = ""
    if "def _body_row" in IMP:
        start = IMP.find("def _body_row")
        end = IMP.find("\ndef ", start + 10)
        br_section = IMP[start:end]
    br_return_match = re.search(r"return \((.*?)\)\s*$", br_section, re.DOTALL | re.MULTILINE)
    if br_return_match and flush_match:
        # Strip inline comments before counting commas
        ret_body = re.sub(r"#[^\n]*", "", br_return_match.group(1))
        # Count top-level commas in the return tuple
        depth = 0
        top_commas = 0
        for ch in ret_body:
            if ch in "([": depth += 1
            elif ch in ")]": depth -= 1
            elif ch == "," and depth == 0:
                top_commas += 1
        # Python allows trailing comma in tuple — last comma doesn't add an element
        # Check if ret_body ends with a trailing comma (after stripping whitespace/newlines)
        trailing_comma = ret_body.rstrip().endswith(",")
        tuple_len = top_commas + 1 - (1 if trailing_comma else 0)
        cols_count = len([c.strip() for c in flush_match.group(1).split(",") if c.strip()])
        if tuple_len == cols_count:
            PASS("N1", f"_body_row tuple length ({tuple_len}) == INSERT columns ({cols_count}) ✓", verbose)
        else:
            BUG("N1", f"_body_row tuple length ({tuple_len}) vs INSERT columns ({cols_count}) mismatch — check order.")

    # ── O: distance-slider must NOT auto-trigger search ─────────────────
    # Fix v3.30: distance sliders must NOT be wired to _debouncedSearch at all.
    # Wiring them caused silent card replacement ("distances changed") because a
    # full new search ran on release, fetching a different set of systems for the
    # new distance range. Users must press Search to apply a new distance.
    attach_fn = HTML[HTML.find("function _attachIncrementalSearch"):HTML.find("function _attachIncrementalSearch")+1000]
    if "dist-slider" in attach_fn and "addEventListener" in attach_fn:
        # Check if it's actually adding an event listener for dist-slider
        dist_listener = re.search(
            r"dist-slider.*?addEventListener|addEventListener.*?dist-slider",
            attach_fn, re.DOTALL
        )
        if dist_listener:
            BUG("O1", "_attachIncrementalSearch wires dist-slider to _debouncedSearch — this triggers a "
                "full search on slider release, silently replacing result cards. Remove distance sliders "
                "from this function; users must press Search to apply a new distance.")
        else:
            PASS("O1", "dist-slider NOT wired to _debouncedSearch ✓", verbose)
    else:
        PASS("O1", "dist-slider NOT wired to _debouncedSearch ✓", verbose)

    # ── P: size-slider has onchange for badge update ──────────────────────
    size_slider_line = ""
    for line in HTML.splitlines():
        if 'id="size-slider"' in line:
            size_slider_line = line
            break
    if "onchange" in size_slider_line:
        PASS("P1", "size-slider has onchange handler ✓", verbose)
    else:
        BUG("P1", "size-slider missing onchange handler — filter badge never updates on page-size change.")

    # ── Q: min-rating/max-rating incremental search ───────────────────────
    inc_search_fn = HTML[HTML.find("function _attachIncrementalSearch"):HTML.find("function _attachIncrementalSearch")+800]
    if "'min-rating-slider'" in inc_search_fn:
        PASS("Q1", "_attachIncrementalSearch uses correct min-rating-slider ID ✓", verbose)
    else:
        BUG("Q1", "_attachIncrementalSearch uses wrong rating slider IDs (missing '-slider' suffix).")

    # ── R: passesBodyFilters silent-skip bug ─────────────────────────────
    # OLD broken code: skipBodyFilters = _localDbAvailable && !_localDbHasBodies && bodies.length === 0
    # This silently passed ALL systems through body-type filters when Phase 2 not done.
    # ELW min=1 → got results with 0 ELW because the filter was completely bypassed.
    if "_localDbAvailable && !_localDbHasBodies && bodies.length === 0" in HTML:
        BUG("R1", "passesBodyFilters uses old skipBodyFilters logic — ELW/WW/all body sliders "
            "silently ignored when Phase 2 not imported. CRITICAL: every system passes unfiltered.")
    else:
        PASS("R1", "passesBodyFilters: old silent-skip pattern removed ✓", verbose)

    if "anyBodyFilterActive" in HTML and "bodies.length === 0 && anyBodyFilterActive" in HTML:
        PASS("R2", "passesBodyFilters: correctly rejects empty-body systems when sliders active ✓", verbose)
    else:
        BUG("R2", "passesBodyFilters: does not reject empty-body systems when body filters are set.")

    # ── S: Python walkable count checks tidal lock ────────────────────────
    # BUG-WALK-PY: _count_body_types walkable must exclude tidally-locked bodies
    # to match JS countBodyTypes (fixed in v3.28) which checks
    #   !b.is_rotational_period_tidally_locked
    # If Python omits this, server-side walkable filter count is inflated for
    # systems with tidally locked airless landable bodies.
    py_walkable_block = ""
    for i, line in enumerate(PY.splitlines(), 1):
        if 'counts["walkable"]' in line or "counts['walkable']" in line:
            # Collect surrounding context lines
            chunk = PY.splitlines()[max(0,i-6):i+2]
            py_walkable_block = "\n".join(chunk)
            break
    if ("is_tidal_lock" in py_walkable_block or
            "is_rotational_period_tidally_locked" in py_walkable_block):
        PASS("S1", "Python _count_body_types walkable checks tidal lock ✓", verbose)
    else:
        BUG("S1", "Python _count_body_types walkable does NOT check tidal lock — "
            "inflated walkable counts for systems with tidally locked airless landable planets. "
            "Fix: add `and not is_tidal` guard (mirrors JS v3.28 fix).")

    # ── T: distance-slider change event does NOT call _debouncedSearch ────
    # The HTML onchange for dist-slider calls updateFilterBadge() — that is
    # correct (badge update only). Make sure it does NOT call runSearch or
    # _debouncedSearch directly in the HTML attribute.
    dist_html_line = ""
    for line in HTML.splitlines():
        if 'id="dist-slider"' in line:
            dist_html_line = line
            break
    if "_debouncedSearch" in dist_html_line or "runSearch" in dist_html_line:
        BUG("T1", "dist-slider HTML onchange calls _debouncedSearch/runSearch directly — "
            "this is redundant with _attachIncrementalSearch and causes double-search.")
    else:
        PASS("T1", "dist-slider HTML onchange does NOT call runSearch/debouncedSearch directly ✓", verbose)

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print("═" * 60)
    print("ED:Finder Exhaustive Audit Report")
    print("═" * 60)
    if notes:
        print(f"\n⚠️  NOTES ({len(notes)}):")
        for nid, nmsg in notes:
            print(f"   [{nid}] {nmsg}")
    if bugs:
        print(f"\n🐛 BUGS FOUND ({len(bugs)}):")
        for bid, bmsg in bugs:
            print(f"   [{bid}] {bmsg}")
        print()
    else:
        print("\n✅ ALL CHECKS PASSED — no bugs found.\n")

    checks_run = len(bugs) + len(notes) + (
        # count PASS checks by tracking them
        sum(1 for line in sys.stdout.getvalue().split("\n") if "✅" in line)
        if hasattr(sys.stdout, "getvalue") else 0
    )
    print(f"Bugs: {len(bugs)} | Notes: {len(notes)}")
    print("═" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="ED:Finder exhaustive audit")
    parser.add_argument("--verbose", action="store_true", help="Show PASS items")
    parser.add_argument("--fix-report", action="store_true",
                        help="Exit with code 1 if bugs found (for CI)")
    args = parser.parse_args()

    run_audit(verbose=args.verbose)

    if args.fix_report and bugs:
        sys.exit(1)


if __name__ == "__main__":
    main()
