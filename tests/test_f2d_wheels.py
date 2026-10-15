"""The attested F2d dependency graph must authenticate every installed wheel."""

from pathlib import Path
import re

from scripts.operator.lib import f2d_operator_identity


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = "deploy/v3-production/f2d-wheels.txt"


def test_f2d_wheels_are_exact_pinned_and_hash_locked() -> None:
    text = (REPO_ROOT / LOCK_PATH).read_text(encoding="utf-8")
    requirements = []
    for line in text.replace("\\\n", " ").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        assert re.fullmatch(r"[a-z0-9-]+==[0-9]+(?:\.[0-9]+)+", fields[0]), line
        assert len(fields) >= 2, f"Missing wheel hash: {line}"
        assert all(re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", item) for item in fields[1:]), line
        requirements.append(fields[0])
    # CPython 3.14 Linux resolves no typing-extensions or Windows tzdata dependency.
    assert sorted(requirements) == ["psycopg-binary==3.3.4", "psycopg==3.3.4"]


def test_f2d_wheel_lock_is_bound_to_operator_identity() -> None:
    assert LOCK_PATH in f2d_operator_identity.manifest_entries(REPO_ROOT)
