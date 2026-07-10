from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_population_storage_contract_is_nullable():
    schema = (ROOT / "sql" / "001_schema.sql").read_text(encoding="utf-8")
    migration = (ROOT / "sql" / "035_nullable_population.sql").read_text(encoding="utf-8")
    manifest = (ROOT / "sql" / "migration-manifest.txt").read_text(encoding="utf-8")

    assert "population          BIGINT          DEFAULT NULL" in schema
    assert "population          BIGINT          NOT NULL DEFAULT 0" not in schema
    assert "ALTER COLUMN population DROP NOT NULL" in migration
    assert "ALTER COLUMN population DROP DEFAULT" in migration
    assert "035_nullable_population.sql" in manifest


def test_population_writers_preserve_unknown_as_null():
    eddn_source = (ROOT / "apps" / "eddn" / "src" / "eddn_listener.py").read_text(encoding="utf-8")
    spansh_source = (ROOT / "apps" / "importer" / "src" / "import_spansh.py").read_text(encoding="utf-8")

    assert "$6::economy_type,$7::bigint" in eddn_source
    assert "COALESCE($7::bigint, 0)" not in eddn_source
    assert "population      = COALESCE($7::bigint, systems.population)" in eddn_source
    assert "def _parse_system_population(sys_obj: dict) -> int | None:" in spansh_source
    assert "_parse_system_population(sys_obj)" in spansh_source
    assert "int(sys_obj.get('population') or 0)" not in spansh_source
