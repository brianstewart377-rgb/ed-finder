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


def test_fractions_json_drives_the_v4_score_distribution_and_is_validated(tmp_path):
    """The real calibration histogram may replace the declared synthetic distribution."""
    module = _load()
    floors = {key: {"60": 0.3, "76": 0.08, "88": 0.01} for key in module.ARCHETYPE_KEYS}
    expr = module._score_expr(0, "fractions", floors[module.ARCHETYPE_KEYS[0]])
    assert "0.01" in expr and "CASE" in expr
    with pytest.raises(ValueError, match="needs per-floor probabilities"):
        module._score_expr(0, "fractions", None)
    with pytest.raises(ValueError, match="unknown distribution"):
        module._score_expr(0, "triangular")


def test_receipt_declares_its_score_distribution_source():
    source = SCRIPT.read_text(encoding="utf-8")
    # A receipt must say whether its fractions are the declared synthetic distribution
    # or a measured calibration histogram, so a capacity gate cannot mistake one for the other.
    assert '"score_distribution_source": "measured-histogram" if fractions else "declared-synthetic-bell"' in source
    assert "--fractions-json" in source


def test_receipt_binds_fractions_to_a_canonical_copy_and_digest():
    """A capacity gate must be able to prove which histogram a receipt used."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"fractions_canonical"' in source
    assert '"fractions_sha256"' in source
    assert '"sigma_all"' in source
    assert "hashlib.sha256" in source
    # The digest must cover a canonical form, not the caller's file bytes or path.
    assert 'json.dumps(normalized, sort_keys=True, separators=(",", ":"))' in source


def test_fractions_sampling_is_deterministic_and_matches_the_fractions():
    """The capacity receipt's rows must not depend on random() draws.

    The same migration and histogram have to give the same rows -- and so the same
    index bytes -- on every run, and the realized tier shares have to match the
    supplied fractions closely, not merely in expectation.
    """
    from decimal import Decimal, getcontext

    module = _load()
    floors = {"60": 0.5, "76": 0.2, "88": 0.05}
    expr = module._score_expr(3, "fractions", floors)
    assert "random()" not in expr
    assert expr == module._score_expr(3, "fractions", floors)
    # A Python mirror of the SQL band assignment with the module's own constants.
    getcontext().prec = 40
    step = Decimal(module.WEYL_STEP)
    offset = Decimal(f"{(3 * module.WEYL_KEY_OFFSET) % 1:.20f}")
    rows = 20_000
    counts = {60: 0, 76: 0, 88: 0}
    for n in range(1, rows + 1):
        u = (n * step + offset) % 1
        if u < Decimal("0.05"):
            score = 88 + (n * 7 + 3) % 13
        elif u < Decimal("0.2"):
            score = 76 + (n * 11 + 3) % 12
        elif u < Decimal("0.5"):
            score = 60 + (n * 13 + 3) % 16
        else:
            score = (n * 17 + 3) % 60
        for floor in counts:
            counts[floor] += score >= floor
    for floor, fraction in ((60, 0.5), (76, 0.2), (88, 0.05)):
        assert abs(counts[floor] / rows - fraction) < 0.001


def test_bell_sampling_is_seeded_before_every_fill():
    source = SCRIPT.read_text(encoding="utf-8")
    fill_loop = source.split("for layout, column, trailing, predicates, distribution")[1]
    assert fill_loop.index('conn.execute(f"SELECT setseed({RANDOM_SEED})")') < fill_loop.index(
        "_fill("
    )
    assert '"random_seed": RANDOM_SEED' in source


@pytest.mark.parametrize(
    ("floors", "message"),
    [
        ({"60": 0.5, "76": 0.2}, "missing floor keys: 88"),
        ({"76": 0.2, "88": 0.1}, "missing floor keys: 60"),
        ({"60": "x", "76": 0.2, "88": 0.1}, "must be numbers"),
        ([0.5, 0.2, 0.1], "must be an object"),
    ],
)
def test_malformed_fractions_stop_with_a_message_not_a_traceback(
    tmp_path, monkeypatch, floors, message
):
    import json as _json

    module = _load()
    fractions = {key: {"60": 0.5, "76": 0.2, "88": 0.1} for key in module.ARCHETYPE_KEYS}
    fractions[module.ARCHETYPE_KEYS[0]] = floors
    path = tmp_path / "fractions.json"
    path.write_text(_json.dumps(fractions), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["measure", "--fractions-json", str(path)])
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert message in str(exc.value.code)
