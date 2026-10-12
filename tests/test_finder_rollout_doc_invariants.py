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
MIGRATION_LIST = re.compile(r"\[0\d\d(?:-rewritten)?(?:, 0\d\d(?:-rewritten)?)+\]")


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
    canonical = _roadmap_apply_set()
    assert "015" in canonical
    for name, text in (
        ("ROADMAP", _read(ROADMAP)),
        ("F2d design", _f2d_current()),
        ("capacity decision", _read(CAPACITY)),
        ("rollout state", _read(ROLLOUT)),
    ):
        planned = {found for found in MIGRATION_LIST.findall(text) if "015" in found}
        assert planned <= {canonical}, (name, planned, canonical)


def test_every_sigma_all_limit_is_the_same():
    limits = set()
    for text in (_read(ROADMAP), _f2d_current()):
        limits.update(re.findall(r"Σ_all\s*(?:>|≤|<=|>=|<)\s*([0-9]+(?:\.[0-9]+)?)", text))
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
