from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_station_type_enum_contains_dodec_in_base_schema() -> None:
    schema = (REPO_ROOT / "sql" / "001_schema.sql").read_text(encoding="utf-8")

    assert "'Dodec'" in schema
    assert "'Coriolis'" in schema
    assert "'Ocellus'" in schema
    assert "'Orbis'" in schema


def test_dodec_forward_migration_is_additive_only() -> None:
    migration = (REPO_ROOT / "sql" / "028_add_dodec_station_type.sql").read_text(
        encoding="utf-8"
    )

    assert "ALTER TYPE station_type ADD VALUE IF NOT EXISTS 'Dodec';" in migration
    assert "UPDATE stations" not in migration
    assert "station_type_dry_run" not in migration
    assert "canonical apply" not in migration.lower()
