"""Archive inventory gates for the local real-data map acceptance lane."""

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "dev"))

import map_snapshot_check as check


class MapSnapshotCheckTest(unittest.TestCase):
    def manifest(self, archive: bytes) -> dict:
        return {
            "format": check.FORMAT,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(archive).hexdigest(),
            "generation_id": "00000000-0000-0000-0000-000000000001",
            "relation_schema": "v3_gen_abc",
            "spatial_generation_id": "00000000-0000-0000-0000-000000000002",
            "spatial_pyramid_version": "pyramid_v1",
            "source_system_count": 1000000,
            "level": 3,
            "level_cell_count": 1234,
            "coverage_level": "camera-path",
            "camera_paths": ["Achenar zoom and pan"],
            "data_relations": sorted(check.REQUIRED_RELATIONS | {
                "v3_gen_abc.systems", "v3_gen_abc.bodies",
            }),
        }

    def test_rejects_unreviewed_private_archive_data(self) -> None:
        archive = b"archive"
        manifest = self.manifest(archive)
        listing = "\n".join(
            f"{n}; 0 0 TABLE DATA {relation.split('.')[0]} {relation.split('.')[1]} owner"
            for n, relation in enumerate(manifest["data_relations"], 1)
        ) + "\n20; 0 0 TABLE DATA v3_private private_fact owner"
        with tempfile.TemporaryDirectory() as temporary:
            dump = Path(temporary) / "map.dump"
            dump.write_bytes(archive)
            with patch.object(check, "command", side_effect=[manifest["sha256"] + "  /tmp/map-snapshot.dump", listing]):
                with self.assertRaisesRegex(ValueError, "unapproved TABLE DATA schema"):
                    check.check_archive(manifest, dump, Path("docker-compose.map-test.yml"))

    def test_manifest_rejects_invalid_schema_and_duplicate_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            manifest = self.manifest(b"archive")
            manifest["relation_schema"] = "v3_private"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "canonical relation_schema"):
                check.load_manifest(path)
            manifest["relation_schema"] = "v3_gen_abc"
            manifest["data_relations"].append(manifest["data_relations"][0])
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate data_relations"):
                check.load_manifest(path)


if __name__ == "__main__":
    unittest.main()

