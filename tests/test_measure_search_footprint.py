"""Contracts for the disposable Search-footprint measurement."""

from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import sys

import pytest

from scripts.operator.lib import f2d_evidence

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dev" / "measure_search_footprint.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_search_footprint", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _no_ambient_libpq_routing(monkeypatch):
    for name in ("PGHOST", "PGHOSTADDR", "PGPORT", "PGSERVICE", "PGSERVICEFILE", "PGDATABASE"):
        monkeypatch.delenv(name, raising=False)


class _FakeConn:
    def __init__(self, row):
        self.row = row

    def execute(self, _statement):
        row = self.row

        class _Cursor:
            def fetchone(self):
                return row

        return _Cursor()


def _sizes(total: int) -> dict[str, object]:
    return {
        "heap_bytes": total - 20,
        "index_bytes": 16,
        "toast_bytes": 4,
        "total_bytes": total,
        "per_index_bytes": {"system_search_pkey": 16},
    }


def _receipt(module, *, pre_total=1001, post_total=1302, fixed_total=902, rows=100):
    # The validator recomputes the applied migration sets from the current
    # manifest, so the fixture records exactly those.
    pre_entries, post_entries = module.migration_sets()
    return module.build_receipt(
        rows=rows,
        versions=(180004, 180004, 180004),
        migrations_pre010=module._receipt_migrations(pre_entries),
        migrations_post010=module._receipt_migrations(post_entries),
        pre010=_sizes(pre_total),
        post010=_sizes(post_total),
        fixed=_sizes(fixed_total),
        text_bytes_seeded=1200,
        f2d_operator_code_sha256="a" * 64,
    )


def test_registered_states_are_distinct_and_record_every_applied_hash():
    module = _load()
    pre010, post010 = module.migration_sets()
    assert [entry[0] for entry in post010] == [entry[0] for entry in pre010] + [module.MIGRATION_010]
    assert module.MIGRATION_004 in [entry[0] for entry in pre010]
    assert module.MIGRATION_010 not in [entry[0] for entry in pre010]
    assert module.MIGRATION_010 in [entry[0] for entry in post010]
    for entry in (*pre010, *post010):
        assert entry[2] == module.hashlib.sha256(entry[1].read_bytes()).hexdigest()
    assert len(module._receipt_migrations(pre010)) == len(pre010)
    assert len(module._receipt_migrations(post010)) == len(post010)


def test_fixed_distribution_uses_exactly_one_byte_in_each_text_column():
    module = _load()
    rows = list(module.synthetic_text_rows(100, fixed=True))
    assert rows == [("n", "r", "s")] * 100
    assert all(sum(len(value.encode()) for value in row if value is not None) == 3 for row in rows)


def test_seeded_distribution_is_reproducible_and_respects_declared_bounds():
    module = _load()
    first = list(module.synthetic_text_rows(500, fixed=False))
    assert first == list(module.synthetic_text_rows(500, fixed=False))
    assert all(6 <= len(name.encode()) <= 64 for name, _region, _star in first)
    assert all(region is None or 6 <= len(region.encode()) <= 64 for _name, region, _star in first)
    assert all(star is None or 1 <= len(star.encode()) <= 12 for _name, _region, star in first)
    assert any(region is None for _name, region, _star in first)
    assert any(star is None for _name, _region, star in first)


def test_delta_is_ceiling_of_the_unrounded_total_difference():
    module = _load()
    receipt = _receipt(module, pre_total=1001, post_total=1302, rows=100)
    assert receipt["pre010_bytes_per_row"] == 11
    assert receipt["post010_bytes_per_row"] == 14
    # ceil((1302 - 1001) / 100), not ceil(1302/100)-ceil(1001/100).
    assert receipt["measured_010_delta_bytes_per_row"] == 4
    assert receipt["search_fixed_bytes_per_row"] == 10


def test_negative_measured_delta_is_refused():
    module = _load()
    with pytest.raises(ValueError, match="negative delta"):
        _receipt(module, pre_total=1303, post_total=1302)


def test_receipt_is_sealed_and_shared_loader_accepts_it(tmp_path):
    module = _load()
    receipt = _receipt(module)
    path = tmp_path / "search-footprint.json"
    module._atomic_write_json(path, receipt)
    assert f2d_evidence.load_sealed(path) == receipt
    assert receipt["content_sha256"] == f2d_evidence.canonical_sha256(
        {key: value for key, value in receipt.items() if key != "content_sha256"}
    )
    assert module.validate_search_footprint_receipt(receipt) is receipt


@pytest.mark.parametrize(
    "field",
    [
        "pre010_bytes_per_row",
        "post010_bytes_per_row",
        "measured_010_delta_bytes_per_row",
        "search_fixed_bytes_per_row",
    ],
)
def test_validator_refuses_each_missing_gate_field(field):
    module = _load()
    body = _receipt(module)
    del body["content_sha256"]
    del body[field]
    with pytest.raises(ValueError, match=field):
        module.validate_search_footprint_receipt(f2d_evidence.seal(body))


def test_non_loopback_dsn_is_refused_before_connect_or_write():
    module = _load()
    with pytest.raises(ValueError, match="non-loopback"):
        module.disposable_conninfo(
            "postgresql://u:secret@db.example.com/ratings_v4_validation"
        )


def test_server_must_be_loopback_postgresql_18_before_any_database_create(monkeypatch):
    module = _load()
    assert module.assert_disposable_server(
        _FakeConn(("127.0.0.1", "127.0.0.1", 180004, "ratings_v4_validation")),
        expected_database="ratings_v4_validation",
    ) == 180004
    with pytest.raises(ValueError, match="not loopback or the attested disposable container"):
        module.assert_disposable_server(
            _FakeConn(("203.0.113.9", "203.0.113.1", 180004, "ratings_v4_validation"))
        )
    # A disposable service container behind a published loopback port reports
    # its bridge address and sees the bridge gateway as the client; accepted only
    # when the orchestrator attested that exact address.
    monkeypatch.delenv(module.ATTESTED_SERVER_ADDRESS_ENV, raising=False)
    with pytest.raises(ValueError, match="not loopback or the attested disposable container"):
        module.assert_disposable_server(
            _FakeConn(("172.18.0.2", "172.18.0.1", 180004, "ratings_v4_validation"))
        )
    monkeypatch.setenv(module.ATTESTED_SERVER_ADDRESS_ENV, "172.18.0.2")
    assert module.assert_disposable_server(
        _FakeConn(("172.18.0.2", "172.18.0.1", 180004, "ratings_v4_validation"))
    ) == 180004
    with pytest.raises(ValueError, match="not loopback or the attested disposable container"):
        module.assert_disposable_server(
            _FakeConn(("172.18.0.9", "172.18.0.1", 180004, "ratings_v4_validation"))
        )
    # A tunnel to another private-address server shows a loopback client there.
    monkeypatch.setenv(module.ATTESTED_SERVER_ADDRESS_ENV, "10.1.2.3")
    with pytest.raises(ValueError, match="not loopback or the attested disposable container"):
        module.assert_disposable_server(
            _FakeConn(("10.1.2.3", "127.0.0.1", 180004, "ratings_v4_validation"))
        )
    monkeypatch.delenv(module.ATTESTED_SERVER_ADDRESS_ENV, raising=False)
    assert module.server_address_is_disposable("10.1.2.3", "10.1.0.1", "10.1.2.3") is True
    assert module.server_address_is_disposable("10.1.2.3", "10.1.0.1", None) is False
    assert module.server_address_is_disposable("10.1.2.3", "10.2.0.1", "10.1.2.3") is False
    assert module.server_address_is_disposable("8.8.8.8", "8.8.8.1", "8.8.8.8") is False
    assert module.server_address_is_disposable(None) is False
    with pytest.raises(ValueError, match="PostgreSQL 17, not 18"):
        module.assert_disposable_server(
            _FakeConn(("127.0.0.1", "127.0.0.1", 170006, "ratings_v4_validation"))
        )
    source = SCRIPT.read_text(encoding="utf-8")
    measure_source = source.split("def measure_search_footprint", 1)[1]
    assert measure_source.index("assert_disposable_server(") < measure_source.index(
        "_measure_database("
    )


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:p@localhost/db?hostaddr=203.0.113.9",
        "postgresql://u:p@localhost/db?service=prod",
        "postgresql://u:p@localhost/db#fragment",
        "postgresql://u:p@/ratings_v4_validation",
        "postgresql://u:p@127.0.0.1/postgres",
        "mysql://u:p@localhost/ratings_v4_validation",
    ],
)
def test_dsn_overrides_and_non_allowlisted_databases_are_refused(dsn):
    module = _load()
    with pytest.raises(ValueError):
        module.disposable_conninfo(dsn)


def test_measurement_uses_three_fresh_databases_and_one_aggregate_for_text():
    source = SCRIPT.read_text(encoding="utf-8")
    runner = source.split("def measure_search_footprint", 1)[1].split("def _atomic_write_json", 1)[0]
    assert runner.count("_measure_database(\n") == 3
    assert "sum(octet_length(name)" in source
    assert "COALESCE(octet_length(region_name),0)" in source
    assert "COALESCE(octet_length(main_star_class),0)" in source
    assert "cursor.executemany(statement, values)" in source
    assert "range(0, rows, 1000)" in source


def test_smoke_on_disposable_postgresql_18(monkeypatch, tmp_path):
    """Exercise all three registered-DDL states when the isolated PG18 is available."""
    dsn = os.environ.get("RATINGS_V4_VALIDATION_DATABASE_URL")
    if not dsn:
        pytest.skip("isolated PostgreSQL 18 validation URL not set")
    module = _load()
    monkeypatch.setenv("EDFINDER_DISPOSABLE_DSN", dsn)
    output = tmp_path / "search-footprint.json"
    assert module.main(["--rows", "1000", "--output", str(output)]) == 0
    receipt = f2d_evidence.load_sealed(output)
    module.validate_search_footprint_receipt(receipt)
    assert receipt["rows"] == 1000
    assert receipt["capacity_gate_eligible"] is True
    assert receipt["text_bytes_seeded"] > 0
    assert receipt["fixed"]["total_bytes"] > 0


def test_validator_refuses_migration_sets_other_than_the_current_manifest():
    module = _load()
    body = _receipt(module)
    del body["content_sha256"]
    stale = json.loads(json.dumps(body))
    stale["migrations_applied"]["pre010"][0][1] = "0" * 64
    with pytest.raises(ValueError, match="migrations_applied differs"):
        module.validate_search_footprint_receipt(f2d_evidence.seal(stale))
    short = json.loads(json.dumps(body))
    short["migrations_applied"]["post010"].pop(0)
    with pytest.raises(ValueError, match="migrations_applied differs"):
        module.validate_search_footprint_receipt(f2d_evidence.seal(short))
    for field in ("migration_004_sha256", "migration_010_sha256"):
        resealed = json.loads(json.dumps(body))
        resealed[field] = "0" * 64
        with pytest.raises(ValueError, match=f"{field} differs"):
            module.validate_search_footprint_receipt(f2d_evidence.seal(resealed))

