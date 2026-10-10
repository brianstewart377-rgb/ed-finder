"""The wide-row footprint measurement script may only ever target a disposable loopback database."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "measure_wide_archetype_footprint.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_wide_archetype_footprint", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_loopback_uri_is_accepted_and_connection_uses_validated_keywords():
    module = _load()
    keywords = module.disposable_conninfo("postgresql://u:secret@127.0.0.1:55418/ratings_v4_validation")
    assert keywords["host"] == "127.0.0.1"
    assert keywords["port"] == "55418"
    assert keywords["dbname"] == "ratings_v4_validation"
    assert "hostaddr" not in keywords


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:p@localhost/db?hostaddr=203.0.113.9",  # libpq honours hostaddr over host
        "postgresql://u:p@localhost/db?service=prod",
        "postgresql://u:p@localhost/db#fragment",
        "postgresql://u:p@db.example.com/db",
        "postgresql://u:p@/db",  # no host -> would fall back to PGHOST/socket
        "postgresql://u:p@localhost",  # no database
        "mysql://u:p@localhost/db",
    ],
)
def test_overrides_and_non_loopback_targets_are_refused(dsn):
    module = _load()
    with pytest.raises(ValueError):
        module.disposable_conninfo(dsn)


def test_script_connects_only_through_the_validated_keywords():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "psycopg.connect(**_disposable_conninfo_from_env()" in source
    assert "psycopg.connect(dsn" not in source
