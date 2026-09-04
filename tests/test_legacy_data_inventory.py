import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.migration import legacy_data_inventory as inventory


ROOT = Path(__file__).resolve().parents[1]


LISTING = """; Archive created at 2026-09-04 00:00:00 UTC
;     Dumped from database version: 16.4
;     Dumped by pg_dump version: 16.4
;
5; 2615 2200 SCHEMA - public ignored_owner
100; 1259 10000 TABLE public systems ignored_owner
101; 0 10000 TABLE DATA public systems ignored_owner
102; 1259 10001 TABLE public unexpected_private_table ignored_owner
"""


def _fake_pg_restore(tmp_path: Path, listing: str = LISTING) -> Path:
    listing_path = tmp_path / "listing.txt"
    listing_path.write_text(listing, encoding="utf-8")
    executable = tmp_path / "pg_restore"
    executable.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = --version ]; then echo 'pg_restore (PostgreSQL) 16.4'; exit 0; fi\n"
        f"if [ \"$1\" = --list ]; then cat '{listing_path}'; exit 0; fi\n"
        "exit 91\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def test_parse_toc_discards_owner_and_database_header() -> None:
    parsed = inventory.parse_toc(LISTING)
    assert parsed[0]["schema"] is None
    assert parsed[0]["name"] == "public"
    assert parsed[1]["name"] == "systems"
    assert "ignored_owner" not in json.dumps(parsed)
    assert "Archive created" not in json.dumps(parsed)


@pytest.mark.parametrize(
    ("tool", "archive"),
    [(15, 16), (19, 16), (18, 19), (18, 9)],
)
def test_version_relationship_rejects_unsupported_pairs(
    tool: int, archive: int
) -> None:
    with pytest.raises(inventory.InventoryError):
        inventory.verify_version_relationship(tool, archive)


def test_inventory_writes_sanitized_receipts_and_fails_for_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    dump = input_dir / "synthetic.dump"
    dump.write_bytes(b"not-real; fake pg_restore supplies the listing")
    fake = _fake_pg_restore(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    output = tmp_path / "receipts"

    result = inventory.main(
        [
            "inventory",
            "--dump",
            os.fspath(dump),
            "--output-dir",
            os.fspath(output),
            "--synthetic-or-test-dump",
            "--proposal-template",
        ]
    )

    assert fake.exists()
    assert result == 2
    receipt = json.loads((output / "legacy-inventory.json").read_text())
    assert receipt["dump"]["evidence_kind"] == "synthetic-or-test-acknowledged"
    assert receipt["unclassified_blockers"] == [
        {
            "name": "unexpected_private_table",
            "object_type": "TABLE",
            "schema": "public",
            "toc_id": 102,
        }
    ]
    rendered = json.dumps(receipt)
    assert "ignored_owner" not in rendered
    assert "Archive created" not in rendered
    hashes = json.loads((output / "receipt-hashes.json").read_text())
    assert set(hashes) == {"legacy-inventory.json", "legacy-inventory.md"}
    proposal = json.loads((output / "extraction-manifest.proposal.json").read_text())
    assert proposal["tables"] == []
    assert proposal["owner_approval"]["decision"] == "not_approved"


def test_rejects_symlink_dump_before_pg_restore(tmp_path: Path) -> None:
    real = tmp_path / "real.dump"
    real.write_bytes(b"x")
    link = tmp_path / "linked.dump"
    link.symlink_to(real)
    assert (
        inventory.main(
            [
                "inventory",
                "--dump",
                os.fspath(link),
                "--output-dir",
                os.fspath(tmp_path / "out"),
                "--synthetic-or-test-dump",
            ]
        )
        == 2
    )


def test_retained_mode_rejects_wrong_identity_but_synthetic_mode_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    dump = source / inventory.RETAINED_NAME
    dump.write_bytes(b"tiny synthetic, not retained evidence")
    _fake_pg_restore(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    assert (
        inventory.main(
            [
                "inventory",
                "--dump",
                os.fspath(dump),
                "--output-dir",
                os.fspath(tmp_path / "retained-output"),
                "--retained-vault",
            ]
        )
        == 2
    )
    assert (
        inventory.main(
            [
                "inventory",
                "--dump",
                os.fspath(dump),
                "--output-dir",
                os.fspath(tmp_path / "synthetic-output"),
                "--synthetic-or-test-dump",
            ]
        )
        == 2  # The deliberately unknown TOC entry is a classification blocker.
    )
    receipt = json.loads(
        (tmp_path / "synthetic-output" / "legacy-inventory.json").read_text()
    )
    assert receipt["dump"]["evidence_kind"] == "synthetic-or-test-acknowledged"


@pytest.mark.parametrize(
    "path", ["https://example.invalid/a.dump", "postgresql://db/x"]
)
def test_rejects_network_or_database_dump_paths(path: str, tmp_path: Path) -> None:
    assert (
        inventory.main(
            [
                "inventory",
                "--dump",
                path,
                "--output-dir",
                os.fspath(tmp_path / "output"),
                "--synthetic-or-test-dump",
            ]
        )
        == 2
    )


def test_inspection_plan_only_prints_schema_first_exact_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dump_dir = tmp_path / "input"
    dump_dir.mkdir()
    dump = dump_dir / "synthetic.dump"
    dump.write_bytes(b"synthetic")
    _fake_pg_restore(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    manifest = {
        "schema_version": "legacy-selective-extraction-manifest/v1",
        "manifest_id": "reviewed_system_notes",
        "dump_sha256": "a" * 64,
        "tables": [
            {
                "source_table": "public.system_notes",
                "columns": ["system_id64", "note"],
                "key_filters": [
                    {"column": "system_id64", "operator": "in", "value": [42]}
                ],
                "maximum_rows": 1,
                "destination_mapping": {
                    "table": "public.system_notes",
                    "columns": {"system_id64": "system_id64", "note": "note"},
                },
                "idempotency_key_columns": ["system_id64"],
                "conflict_policy": "abort",
                "relationship_validations": [
                    {
                        "source_columns": ["system_id64"],
                        "referenced_table": "public.systems",
                        "referenced_columns": ["id64"],
                        "required": True,
                    }
                ],
                "expected_source_count": {"exact": 1},
                "expected_target_count": {"minimum": 0, "maximum": 1},
            }
        ],
        "owner_approval": {
            "owner": "repository-owner",
            "decision": "approved",
            "approved_at": "2026-09-04T12:00:00Z",
            "scope": "one invented test record",
        },
        "abort_conditions": ["count differs"],
        "rollback_conditions": ["relationship invalid"],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert (
        inventory.main(
            [
                "inspection-plan",
                "--dump",
                os.fspath(dump),
                "--manifest",
                os.fspath(manifest_path),
                "--host",
                "127.0.0.1",
                "--port",
                "55439",
                "--synthetic-or-test-dump",
            ]
        )
        == 0
    )
    plan = capsys.readouterr().out
    assert plan.index("--schema-only") < plan.index("--data-only")
    assert plan.count("--table public.system_notes") == 2
    assert "--clean" not in plan
    assert "pg_restore --create" not in plan
    assert "PRINTED PLAN ONLY" in plan


def test_custom_format_round_trip_when_local_postgres_tools_exist(
    tmp_path: Path,
) -> None:
    required = ["initdb", "pg_ctl", "createdb", "psql", "pg_dump", "pg_restore"]
    tools = {name: shutil.which(name) for name in required}
    missing = [name for name, path in tools.items() if path is None]
    if missing:
        pytest.skip(
            "PostgreSQL client/server binaries unavailable: " + ", ".join(missing)
        )

    data = tmp_path / "cluster"
    socket = tmp_path / "socket"
    socket.mkdir()
    port = "55439"
    subprocess.run(
        [tools["initdb"], "--no-locale", "--encoding=UTF8", "--auth=trust", "-D", data],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            tools["pg_ctl"],
            "-D",
            data,
            "-o",
            f"-h '' -k {socket} -p {port}",
            "-w",
            "start",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        common = ["--host", os.fspath(socket), "--port", port]
        subprocess.run([tools["createdb"], *common, "legacy_synthetic"], check=True)
        subprocess.run(
            [
                tools["psql"],
                *common,
                "--dbname",
                "legacy_synthetic",
                "--command",
                "CREATE TABLE watchlist (id bigint primary key, system_id64 bigint); INSERT INTO watchlist VALUES (1, 42)",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        dump = tmp_path / "input" / "tiny.dump"
        dump.parent.mkdir()
        subprocess.run(
            [
                tools["pg_dump"],
                *common,
                "--format=custom",
                "--file",
                dump,
                "legacy_synthetic",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        listed = subprocess.run(
            [tools["pg_restore"], "--list", dump],
            check=True,
            capture_output=True,
            text=True,
        )
        assert any(
            item["name"] == "watchlist" for item in inventory.parse_toc(listed.stdout)
        )
    finally:
        subprocess.run(
            [tools["pg_ctl"], "-D", data, "-m", "fast", "-w", "stop"], check=True
        )
