from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.operator.lib import f2d_operator_identity as identity


REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_HELPER = REPO_ROOT / "scripts/operator/lib/f2d_operator_identity.sh"
EXPECTED_ACTIVE_ENTRIES = (
    "deploy/v3-production/f2d-operator-code.txt",
    "deploy/v3-production/f2d-wheels.txt",
    "docs/operations/evidence/2026-10-10-v3-derived-lifecycle-status-receipt.json",
    "requirement:psycopg[binary]==3.3.4",
    "scripts/dev/convert_calibration_histogram.py",
    "scripts/dev/measure_search_footprint.py",
    "scripts/dev/measure_wide_archetype_footprint.py",
    "scripts/operator/actions/v3-archetype-calibration-complete.sh",
    "scripts/operator/actions/v3-archetype-plan-probe.sh",
    "scripts/operator/actions/v3-finder-capacity-gate.sh",
    "scripts/operator/actions/v3-publish-derived-products.sh",
    "scripts/operator/actions/v3-system-archetype.sh",
    "scripts/operator/actions/v3-system-search-f1.sh",
    "scripts/operator/lib/f2d_evidence.py",
    "scripts/operator/lib/f2d_operator_identity.py",
    "scripts/operator/lib/f2d_operator_identity.sh",
    "scripts/v3_archetype_calibration_complete.py",
    "scripts/v3_archetype_calibration_probe.py",
    "scripts/v3_archetype_plan_probe.py",
    "scripts/v3_finder_capacity_gate.py",
    "scripts/v3_plan_probe_statements.py",
    "scripts/v3_publish_derived_products.py",
    "scripts/v3_system_archetype.py",
    "scripts/v3_system_archetype_model.py",
    "scripts/v3_system_search.py",
    "scripts/v3_system_search_parallel.py",
    "shared_contracts/__init__.py",
    "shared_contracts/v3_system_archetype_model.py",
    "sql/v3/migration-manifest.txt",
    "sql/v3/migrations/001_v3_baseline.sql",
    "sql/v3/migrations/003_ratings_v4_derived.sql",
    "sql/v3/migrations/004_v3_search_spatial_clusters.sql",
    "sql/v3/migrations/006_v3_derived_product_lifecycle.sql",
    "sql/v3/migrations/011_v3_system_archetype.sql",
)
PLANNED_ACTION_COMMENTS = (
    "scripts/operator/actions/v3-publish-derived-products.sh",
)


def _copy_checkout(destination: Path) -> Path:
    for entry in EXPECTED_ACTIVE_ENTRIES:
        if entry.startswith("requirement:"):
            continue
        source = REPO_ROOT / entry
        target = destination / entry
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return destination


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    return _copy_checkout(tmp_path / "checkout")


def _shell(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SHELL_HELPER), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_committed_manifest_is_complete_sorted_and_names_planned_actions() -> None:
    manifest = REPO_ROOT / identity.MANIFEST_RELATIVE_PATH
    text = manifest.read_text(encoding="utf-8")
    assert identity.manifest_entries(REPO_ROOT) == EXPECTED_ACTIVE_ENTRIES
    assert list(EXPECTED_ACTIVE_ENTRIES) == sorted(EXPECTED_ACTIVE_ENTRIES)
    assert len(EXPECTED_ACTIVE_ENTRIES) == len(set(EXPECTED_ACTIVE_ENTRIES))
    for planned_path in PLANNED_ACTION_COMMENTS:
        # D2a has landed: this formerly planned action must be active exactly once.
        assert text.splitlines().count(planned_path) == 1
        assert planned_path in identity.manifest_entries(REPO_ROOT)


def test_python_uses_canonical_json_pairs(checkout: Path) -> None:
    pairs = []
    for entry in EXPECTED_ACTIVE_ENTRIES:
        if entry.startswith("requirement:"):
            digest = hashlib.sha256(entry.encode()).hexdigest()
        else:
            digest = hashlib.sha256((checkout / entry).read_bytes()).hexdigest()
        pairs.append([entry, digest])
    canonical = json.dumps(pairs, separators=(",", ":")).encode()
    assert identity.compute_operator_code_sha256(checkout) == hashlib.sha256(canonical).hexdigest()


def test_shell_and_python_agree_on_committed_and_changed_tree(checkout: Path) -> None:
    committed_python = identity.compute_operator_code_sha256(REPO_ROOT)
    committed_shell = _shell("compute", str(REPO_ROOT))
    assert committed_shell.returncode == 0, committed_shell.stderr
    assert committed_shell.stdout.strip() == committed_python

    changed = checkout / "scripts/v3_system_search.py"
    changed.write_bytes(changed.read_bytes() + b"\n# changed identity fixture\n")
    changed_python = identity.compute_operator_code_sha256(checkout)
    changed_shell = _shell("compute", str(checkout))
    assert changed_shell.returncode == 0, changed_shell.stderr
    assert changed_shell.stdout.strip() == changed_python
    assert changed_python != committed_python


@pytest.mark.parametrize("entry", EXPECTED_ACTIVE_ENTRIES)
def test_every_manifest_entry_change_is_refused(checkout: Path, entry: str) -> None:
    attested = identity.compute_operator_code_sha256(checkout)
    if entry.startswith("requirement:"):
        manifest = checkout / identity.MANIFEST_RELATIVE_PATH
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace("==3.3.4", "==3.3.5"),
            encoding="utf-8",
        )
    elif entry == identity.MANIFEST_RELATIVE_PATH:
        manifest = checkout / entry
        manifest.write_text(manifest.read_text(encoding="utf-8") + "# identity mutation\n", encoding="utf-8")
    else:
        listed_file = checkout / entry
        listed_file.write_bytes(listed_file.read_bytes() + b"\n# identity mutation\n")

    with pytest.raises(identity.OperatorIdentityError, match="attested_identity_mismatch"):
        identity.require_operator_code_identity(checkout, attested)
    shell = _shell("verify", str(checkout), attested)
    assert shell.returncode == 64
    assert "attested_identity_mismatch" in shell.stderr


def test_unlisted_document_does_not_move_identity(checkout: Path) -> None:
    before = identity.compute_operator_code_sha256(checkout)
    # docs/operations/evidence/ already exists in the copied checkout because the
    # step-0 receipt is manifest-listed; an unlisted document beside it must not
    # move the identity.
    document = checkout / "docs/unlisted.md"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("evidence-only change\n", encoding="utf-8")
    sibling = checkout / "docs/operations/evidence/unlisted-note.md"
    sibling.write_text("evidence-only change\n", encoding="utf-8")
    assert identity.compute_operator_code_sha256(checkout) == before
    assert _shell("verify", str(checkout), before).returncode == 0


def test_attested_environment_value_is_accepted(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attested = identity.compute_operator_code_sha256(checkout)
    monkeypatch.setenv(identity.ATTESTED_ENVIRONMENT_VARIABLE, attested)
    assert identity.require_operator_code_identity(checkout) == attested
    shell = _shell("verify", str(checkout))
    assert shell.returncode == 0, shell.stderr
    assert shell.stdout.strip() == attested


def test_missing_listed_path_refuses_in_python_and_shell(checkout: Path) -> None:
    missing_entry = "scripts/v3_system_search_parallel.py"
    (checkout / missing_entry).unlink()
    with pytest.raises(identity.OperatorIdentityError, match=f"listed_path_missing:{missing_entry}"):
        identity.compute_operator_code_sha256(checkout)
    shell = _shell("compute", str(checkout))
    assert shell.returncode == 64
    assert f"listed_path_missing:{missing_entry}" in shell.stderr


def test_symlinked_listed_path_refuses_in_python_and_shell(checkout: Path) -> None:
    linked_entry = "scripts/v3_system_search_parallel.py"
    linked_path = checkout / linked_entry
    link_target = checkout / "unlisted-target.py"
    link_target.write_bytes(linked_path.read_bytes())
    linked_path.unlink()
    linked_path.symlink_to(link_target)
    with pytest.raises(identity.OperatorIdentityError, match=f"listed_path_symlink:{linked_entry}"):
        identity.compute_operator_code_sha256(checkout)
    shell = _shell("compute", str(checkout))
    assert shell.returncode == 64
    assert f"listed_path_symlink:{linked_entry}" in shell.stderr


def test_unreadable_listed_path_refuses_in_python_and_shell(checkout: Path) -> None:
    unreadable_entry = "scripts/v3_system_search_parallel.py"
    unreadable_path = checkout / unreadable_entry
    unreadable_path.chmod(0)
    try:
        with pytest.raises(identity.OperatorIdentityError, match=f"listed_path_unreadable:{unreadable_entry}"):
            identity.compute_operator_code_sha256(checkout)
        shell = _shell("compute", str(checkout))
        assert shell.returncode == 64
        assert f"listed_path_unreadable:{unreadable_entry}" in shell.stderr
    finally:
        unreadable_path.chmod(0o600)


@pytest.mark.parametrize("attested", [None, "", "A" * 64, "0" * 63, "not-a-digest"])
def test_missing_or_malformed_attested_identity_refuses(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    attested: str | None,
) -> None:
    monkeypatch.delenv(identity.ATTESTED_ENVIRONMENT_VARIABLE, raising=False)
    expected_reason = "attested_identity_missing" if attested in {None, ""} else "attested_identity_malformed"
    with pytest.raises(identity.OperatorIdentityError, match=expected_reason):
        identity.require_operator_code_identity(checkout, attested)

    arguments = ["verify", str(checkout)]
    if attested is not None:
        arguments.append(attested)
    shell = _shell(*arguments)
    assert shell.returncode == 64
    assert expected_reason in shell.stderr


@pytest.mark.parametrize(
    ("replacement", "reason"),
    [
        ("scripts/v3_system_search.py\nscripts/v3_system_search.py\n", "manifest_duplicate_entry"),
        ("scripts/z.py\nscripts/a.py\n", "manifest_not_sorted"),
        ("../outside\n", "manifest_malformed"),
    ],
)
def test_malformed_manifest_refuses_with_named_reason(
    tmp_path: Path,
    replacement: str,
    reason: str,
) -> None:
    checkout = tmp_path / "checkout"
    manifest = checkout / identity.MANIFEST_RELATIVE_PATH
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        f"{identity.MANIFEST_RELATIVE_PATH}\n{replacement}",
        encoding="utf-8",
    )
    with pytest.raises(identity.OperatorIdentityError, match=reason):
        identity.compute_operator_code_sha256(checkout)
    shell = _shell("compute", str(checkout))
    assert shell.returncode == 64
    assert reason in shell.stderr


def test_identity_covers_every_migration_input_the_footprint_measurements_read():
    """A changed measurement DDL input must change the attested identity."""
    from scripts.dev import measure_wide_archetype_footprint as wide

    listed = set(
        (REPO_ROOT / "deploy/v3-production/f2d-operator-code.txt").read_text(encoding="utf-8").splitlines()
    )
    # Search applies every manifest-registered migration, each verified against
    # this manifest's recorded SHA-256, so pinning the manifest pins them all.
    assert "sql/v3/migration-manifest.txt" in listed
    # The Archetype measurement reads these migration files directly.
    for name in (*wide.MIGRATION_PREREQUISITES, "011_v3_system_archetype.sql"):
        assert f"sql/v3/migrations/{name}" in listed

