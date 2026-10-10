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


@pytest.fixture(autouse=True)
def _no_ambient_libpq_routing(monkeypatch):
    for name in ("PGHOST", "PGHOSTADDR", "PGPORT", "PGSERVICE", "PGSERVICEFILE", "PGDATABASE"):
        monkeypatch.delenv(name, raising=False)


def test_loopback_uri_is_accepted_and_connection_uses_validated_keywords():
    module = _load()
    keywords = module.disposable_conninfo("postgresql://u:secret@127.0.0.1:55418/ratings_v4_validation")
    assert keywords["host"] == "127.0.0.1"
    assert keywords["port"] == "55418"
    assert keywords["dbname"] == "ratings_v4_validation"
    assert keywords["hostaddr"] == "127.0.0.1"  # pinned so PGHOSTADDR/name resolution cannot redirect


def test_localhost_pins_loopback_hostaddr():
    module = _load()
    assert module.disposable_conninfo("postgresql://u:p@localhost/ratings_v4_validation")["hostaddr"] == "127.0.0.1"
    assert module.disposable_conninfo("postgresql://u:p@[::1]/ratings_v4_validation")["hostaddr"] == "::1"


@pytest.mark.parametrize("name", ["PGHOST", "PGHOSTADDR", "PGPORT", "PGSERVICE", "PGSERVICEFILE", "PGDATABASE"])
def test_ambient_libpq_routing_variables_are_refused(monkeypatch, name):
    module = _load()
    monkeypatch.setenv(name, "203.0.113.9")
    with pytest.raises(ValueError, match="ambient libpq routing"):
        module.disposable_conninfo("postgresql://u:p@127.0.0.1/ratings_v4_validation")


class _FakeConn:
    def __init__(self, row):
        self._row = row

    def execute(self, _sql):
        row = self._row

        class _Cur:
            def fetchone(self):
                return row

        return _Cur()


def test_server_check_requires_loopback_address_allowlisted_database_and_postgresql_18():
    module = _load()
    ok = ("127.0.0.1", 180004, "ratings_v4_validation")
    assert module.assert_disposable_server(_FakeConn(ok)) == 180004
    with pytest.raises(ValueError, match="not loopback"):
        module.assert_disposable_server(_FakeConn(("203.0.113.9", 180004, "ratings_v4_validation")))
    with pytest.raises(ValueError, match="not the disposable validation service"):
        module.assert_disposable_server(_FakeConn(("127.0.0.1", 180004, "edfinder_v3_phase4c_full_20260827_r5")))
    with pytest.raises(ValueError, match="PostgreSQL 17, not 18"):
        module.assert_disposable_server(_FakeConn(("127.0.0.1", 170006, "ratings_v4_validation")))
    with pytest.raises(ValueError, match="PostgreSQL 19, not 18"):
        module.assert_disposable_server(_FakeConn(("::1", 190000, "ratings_v4_validation")))


def test_server_check_runs_before_any_ddl():
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.index("assert_disposable_server(conn)") < source.index("CREATE SCHEMA IF NOT EXISTS scratch")


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:p@localhost/db?hostaddr=203.0.113.9",  # libpq honours hostaddr over host
        "postgresql://u:p@localhost/db?service=prod",
        "postgresql://u:p@localhost/db#fragment",
        "postgresql://u:p@db.example.com/db",
        "postgresql://u:p@/db",  # no host -> would fall back to PGHOST/socket
        "postgresql://u:p@localhost",  # no database
        "postgresql://u:p@127.0.0.1/edfinder_v3_phase4c_full_20260827_r5",  # a production-shaped name via a loopback tunnel
        "postgresql://u:p@127.0.0.1/postgres",
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
