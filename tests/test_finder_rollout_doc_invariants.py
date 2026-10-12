"""The Finder rollout's shared invariants must read the same in every document.

`docs/ROADMAP.md` controls the rollout; the F2d design, the capacity decision and the
rollout-state record restate parts of it. Each restatement is a chance to drift, and
a drifted copy is an operator instruction that contradicts the controlling one. These
tests extract the invariants every document states and fail on any disagreement, so a
change to one copy has to be made to all of them in the same pull request.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "ROADMAP.md"
F2D = (
    ROOT
    / "docs"
    / "superpowers"
    / "specs"
    / "2026-10-10-v3-finder-f2d-wide-archetype-and-product-attachment-design.md"
)
CAPACITY = ROOT / "docs" / "operations" / "v3-finder-capacity-decision-2026-10-10.md"
ROLLOUT = ROOT / "docs" / "operations" / "v3-finder-production-rollout-state.md"

TARGET_GENERATION = "ratings_v4_prod_p4_parallel_v1"
# Any bracketed list of migration ordinals, with any spacing and either spelling of
# the rewritten 011 (`011-rewritten` or `011'`).
MIGRATION_LIST = re.compile(r"\[\s*0\d\d[^\]]*\]")


def _normalize(found: str) -> str:
    items = [item.strip() for item in found.strip("[]").split(",")]
    items = ["011-rewritten" if item in {"011'", "011’"} else item for item in items]
    return "[" + ", ".join(items) + "]"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _f2d_current() -> str:
    """The design without its dated review history, which records superseded text."""
    text = _read(F2D)
    history = text.find("### Review round")
    assert history > 0, "the F2d design's review history heading moved"
    return text[:history]


def _roadmap_apply_set() -> str:
    roadmap = _read(ROADMAP)
    match = re.search(r"`apply` of\s+`(\[[^\]]+\])`", roadmap)
    assert match, "ROADMAP step 2 no longer states the governed apply set"
    return match.group(1)


def test_every_planned_apply_set_matches_the_roadmap():
    """A list that includes 015 describes the planned apply; it must be the ROADMAP's.

    Lists without 015 describe earlier states (today's registered pending set, or
    PR1's intermediate identity) and are allowed to differ.
    """
    canonical = _normalize(_roadmap_apply_set())
    assert "015" in canonical
    for name, text, must_state in (
        ("ROADMAP", _read(ROADMAP), True),
        ("F2d design", _f2d_current(), True),
        ("capacity decision", _read(CAPACITY), True),
        ("rollout state", _read(ROLLOUT), False),
    ):
        planned = {
            _normalize(found) for found in MIGRATION_LIST.findall(text) if "015" in found
        }
        if must_state:
            # An empty set must not pass vacuously for a document that states the plan.
            assert planned, f"{name} no longer states the planned apply set"
        assert planned <= {canonical}, (name, planned, canonical)


def test_the_list_parser_normalizes_spelling_and_spacing():
    assert _normalize("[014,010, 011', 013,015]") == "[014, 010, 011-rewritten, 013, 015]"
    assert MIGRATION_LIST.findall("apply [014,  010, 011', 013, 015] now") == [
        "[014,  010, 011', 013, 015]"
    ]


def test_every_sigma_all_limit_is_the_same():
    """Every stated Σ_all limit is 4.0.

    The rollout-state record states no limit today; it is still parsed, so a limit
    added there later must agree (review round 51).
    """
    limits = set()
    comparison = r"Σ_all\s*(?:>|≤|<=|>=|<)\s*([0-9]+(?:\.[0-9]+)?)"
    stops_above = r"stops above Σ_all\s*([0-9]+(?:\.[0-9]+)?)"
    for name, text, phrasings, must_state in (
        ("ROADMAP", _read(ROADMAP), (comparison,), True),
        ("F2d design", _f2d_current(), (comparison,), True),
        ("capacity decision", _read(CAPACITY), (stops_above,), True),
        ("rollout state", _read(ROLLOUT), (comparison, stops_above), False),
    ):
        found = [value for phrasing in phrasings for value in re.findall(phrasing, text)]
        if must_state:
            assert found, f"{name} no longer states the Σ_all limit"
        limits.update(found)
    assert len(limits) == 1, limits
    assert {float(value) for value in limits} == {4.0}


def test_every_document_names_the_same_attach_target():
    for name, text in (
        ("ROADMAP", _read(ROADMAP)),
        ("F2d design", _f2d_current()),
        ("capacity decision", _read(CAPACITY)),
        ("rollout state", _read(ROLLOUT)),
    ):
        assert TARGET_GENERATION in text, name


def test_the_capacity_input_is_a_complete_read_in_both_controlling_documents():
    roadmap = _read(ROADMAP)
    design = _f2d_current()
    assert "complete read of every chunk, never a sample" in roadmap
    assert "The capacity input is a complete read, not a sample" in design


def test_the_design_defers_to_the_roadmap_and_names_this_check():
    design = _f2d_current()
    assert "`docs/ROADMAP.md` controls the rollout order and" in design
    assert "tests/test_finder_rollout_doc_invariants.py" in design


def test_the_checks_fail_on_a_drifted_copy(tmp_path, monkeypatch):
    """The apply-set check must actually reject a document that disagrees."""
    drifted = tmp_path / "rollout.md"
    drifted.write_text(
        _read(ROLLOUT) + "\nApply `[014, 010, 011-rewritten, 015]` instead.\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "ROLLOUT", drifted)
    try:
        test_every_planned_apply_set_matches_the_roadmap()
    except AssertionError:
        return
    raise AssertionError("a drifted apply set was not detected")


def test_a_conflicting_rollout_state_sigma_limit_fails(tmp_path, monkeypatch):
    """A Σ_all limit added to the rollout-state record must agree with the others."""
    drifted = tmp_path / "rollout.md"
    drifted.write_text(
        _read(ROLLOUT) + "\nThe build may proceed while Σ_all ≤ 5.0.\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(globals(), "ROLLOUT", drifted)
    try:
        test_every_sigma_all_limit_is_the_same()
    except AssertionError:
        return
    raise AssertionError("a conflicting rollout-state Σ_all limit was not detected")


def test_the_roadmap_and_capacity_decision_list_the_same_open_owner_questions():
    pattern = re.compile(r"owner questions\s*\*{0,2}\(?([0-9][0-9, and]*[0-9])\)?\*{0,2}")
    roadmap = {m.strip() for m in pattern.findall(_read(ROADMAP))}
    capacity = {m.strip() for m in pattern.findall(_read(CAPACITY))}
    assert roadmap, "the ROADMAP no longer lists the unresolved owner questions"
    assert capacity, "the capacity decision no longer lists them"
    normalize = lambda value: sorted(re.findall(r"[0-9]+", value))  # noqa: E731
    assert {tuple(normalize(v)) for v in roadmap} == {tuple(normalize(v)) for v in capacity}



def test_the_design_and_roadmap_agree_on_the_open_owner_questions():
    design = _f2d_current()
    match = re.search(r"Open questions: \*\*([0-9][0-9, and]*[0-9])\*\*", design)
    assert match, "the design's section 11 status line moved"
    roadmap = re.search(r"owner questions \*\*([0-9][0-9, and]*[0-9])\*\*", _read(ROADMAP))
    assert roadmap, "the ROADMAP no longer lists the open owner questions"
    assert re.findall(r"[0-9]+", match.group(1)) == re.findall(r"[0-9]+", roadmap.group(1))
