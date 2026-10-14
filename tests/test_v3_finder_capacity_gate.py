from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import v3_finder_capacity_gate as gate


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]

IDENTITY = "a" * 64
SEAL = "b" * 64
KEYS = gate.ARCHETYPE_KEYS


def _histogram(*, s: int = 0, a: int = 0, b: int = 1, c: int = 2, d: int = 2):
    return {
        key: {"tier_histogram": {"S": s, "A": a, "B": b, "C": c, "D": d}}
        for key in KEYS
    }


def _complete(**changes):
    value = {
        "mode": "complete",
        "system_count": 5,
        "per_archetype": _histogram(),
        "sigma_all": 8 * Fraction(1, 5),
        "content_sha256": SEAL,
    }
    value["sigma_all"] = float(value["sigma_all"])
    value.update(changes)
    return value


def _fraction_file(complete=None):
    complete = complete or _complete()
    exact = gate.histogram_fractions(complete["per_archetype"], complete["system_count"])
    fractions = {
        key: {floor: float(exact[key][floor]) for floor in gate.FLOORS}
        for key in KEYS
    }
    return {
        **fractions,
        "fractions_sha256": gate.hashlib.sha256(
            gate.canonical_json(fractions).encode()
        ).hexdigest(),
        "source_receipt_content_sha256": complete["content_sha256"],
        "source_f2d_operator_code_sha256": IDENTITY,
        "converter_f2d_operator_code_sha256": IDENTITY,
    }


@pytest.mark.parametrize("value", range(0, 257))
def test_reserve_is_exact_ceiling_of_fifteen_percent(value):
    assert gate.reserve_bytes(value) == gate.ceil_fraction(Fraction(23 * value, 20))


def test_non_divisible_tier_projection_rounds_up():
    result = gate.full_archetype_projection(
        system_count=7,
        sigma=Fraction(1, 3),
        heap_bytes_per_row=2,
        primary_key_bytes_per_row=3,
        weighted_index_bytes_per_row=4,
        tier_index_bytes_per_row_per_unit_fraction=5,
    )

    assert result == {
        "projected_heap_bytes": 14,
        "projected_fixed_index_bytes": 49,
        "projected_tier_index_bytes": 12,
        "projected_archetype_bytes": 75,
    }


def test_capacity_boundary_passes_at_required_and_refuses_one_byte_below():
    archetype = gate.fresh_projection(101, "fresh")
    search = gate.fresh_projection(99, "fresh")
    required = gate.reserve_bytes(200)

    assert gate.capacity_result(
        archetype=archetype, search=search, available_bytes=required
    )["passes"] is True
    below = gate.capacity_result(
        archetype=archetype, search=search, available_bytes=required - 1
    )
    assert below["passes"] is False
    assert below["headroom_bytes"] == -1


def test_early_saving_charges_source_remainder_not_ten_percent():
    result = gate.resume_projection(
        full_projection=1_000,
        rows_done=900,
        system_count=1_000,
        bytes_done=700,
        fixed_bytes_per_row=2,
        variable_left=200,
    )

    assert result["remaining"] == 400
    assert result["projection_minus_bytes_done"] == 300
    assert result["term_charged"] == 400
    assert result["max_branch"] == "source_derived_remaining"


def test_wide_search_tail_can_exceed_projection_remainder():
    result = gate.resume_projection(
        full_projection=10_000,
        rows_done=900,
        system_count=1_000,
        bytes_done=5_000,
        fixed_bytes_per_row=10,
        variable_left=6_000,
    )

    assert result["projection_minus_bytes_done"] == 5_000
    assert result["remaining"] == 7_000
    assert result["term_charged"] == 7_000


def test_dense_archetype_tail_charges_exact_tier_entries():
    result = gate.resume_projection(
        full_projection=10_000,
        rows_done=900,
        system_count=1_000,
        bytes_done=9_000,
        fixed_bytes_per_row=1,
        variable_left=126 * 100,
        tier_left=30 * 47,
    )

    assert result["tier_left"] == 1_410
    assert result["term_charged"] == 14_110


def test_matching_resume_can_fit_while_manifest_mismatch_full_charge_does_not():
    resumed = gate.resume_projection(
        full_projection=10_000,
        rows_done=900,
        system_count=1_000,
        bytes_done=9_000,
        fixed_bytes_per_row=1,
        variable_left=900,
    )
    full = gate.fresh_projection(10_000, "product manifest identity differs")
    space = gate.reserve_bytes(resumed["term_charged"])

    assert gate.capacity_result(
        archetype=resumed, search=gate.fresh_projection(0, "ready"), available_bytes=space
    )["passes"] is True
    assert gate.capacity_result(
        archetype=full, search=gate.fresh_projection(0, "ready"), available_bytes=space
    )["passes"] is False


def test_histogram_must_have_every_key_and_tier():
    histogram = _histogram()
    histogram.pop(KEYS[-1])

    with pytest.raises(gate.GateRefusal) as error:
        gate.histogram_fractions(histogram, 5)

    assert error.value.exit_code == 12


def test_sigma_over_four_refuses_at_item_d():
    complete = _complete(sigma_all=24.0)
    fractions = {
        key: {floor: Fraction(1) for floor in gate.FLOORS} for key in KEYS
    }

    with pytest.raises(gate.GateRefusal) as error:
        gate.check_fractions(
            complete,
            _fraction_file(),
            fractions,
            identity=IDENTITY,
            canonical_sha256=lambda value: gate.hashlib.sha256(
                gate.canonical_json(value).encode()
            ).hexdigest(),
        )

    assert error.value.exit_code == 13
    assert error.value.field == "sigma_all"


@pytest.mark.parametrize("decision", [None, "rejected"])
def test_absent_or_nonaccepted_decision_refuses_item_a(decision):
    value = {
        "coefficient_decision": decision,
        "coefficients": {"alpha": 1},
        "complete_receipt_content_sha256": SEAL,
    }

    with pytest.raises(gate.GateRefusal) as error:
        gate.check_coefficient_decision(value, _complete(), {"alpha": 1})

    assert error.value.exit_code == 10


def test_coefficients_are_compared_by_canonical_json_not_python_numeric_equality():
    decision = {
        "coefficient_decision": "accepted",
        "coefficients": {"alpha": 1.0},
        "complete_receipt_content_sha256": SEAL,
    }

    with pytest.raises(gate.GateRefusal) as error:
        gate.check_coefficient_decision(decision, _complete(), {"alpha": 1})

    assert error.value.exit_code == 10
    assert error.value.field == "coefficients"


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("f2d_operator_code_sha256", "c" * 64),
        ("coefficients", {"alpha": 2}),
        ("archetype_model_sha256", "d" * 64),
    ],
)
def test_complete_identity_fields_refuse_independently(field, changed):
    manifest = {"product_code": "system_archetype", "value": 1}
    digest = gate.hashlib.sha256(gate.canonical_json(manifest).encode()).hexdigest()
    complete = _complete(
        f2d_operator_code_sha256=IDENTITY,
        code_identity={"builder": "e" * 64},
        coefficients={"alpha": 1},
        archetype_model_sha256="f" * 64,
        model_file_sha256="1" * 64,
        generation={
            "generation_key": "ratings",
            "derived_generation_id": "uuid",
            "publication_sequence": 1,
        },
        expected_product_manifest=manifest,
        expected_product_manifest_sha256=digest,
    )
    complete[field] = changed
    generation = SimpleNamespace(key="ratings", identifier="uuid", publication_sequence=1)

    with pytest.raises(gate.GateRefusal) as error:
        gate.check_complete_identity(
            complete,
            identity=IDENTITY,
            code_identity={"builder": "e" * 64},
            coefficients={"alpha": 1},
            model_sha256="f" * 64,
            model_file_sha256="1" * 64,
            generation=generation,
            expected_manifest=manifest,
            canonical_sha256=lambda value: gate.hashlib.sha256(
                gate.canonical_json(value).encode()
            ).hexdigest(),
        )

    assert error.value.exit_code == 11
    assert error.value.field == field


def test_fraction_converter_identity_refuses_independently():
    complete = _complete()
    derived = gate.histogram_fractions(complete["per_archetype"], 5)
    fractions = _fraction_file(complete)
    fractions["converter_f2d_operator_code_sha256"] = "9" * 64

    with pytest.raises(gate.GateRefusal) as error:
        gate.check_fractions(
            complete,
            fractions,
            derived,
            identity=IDENTITY,
            canonical_sha256=lambda value: gate.hashlib.sha256(
                gate.canonical_json(value).encode()
            ).hexdigest(),
        )

    assert error.value.exit_code == 13
    assert error.value.field == "converter_f2d_operator_code_sha256"


@pytest.mark.parametrize("which", ["archetype", "search"])
def test_footprint_identity_refuses_independently(which):
    archetype = {
        "migration_011_sha256": "1" * 64,
        "fractions_sha256": "2" * 64,
        "f2d_operator_code_sha256": IDENTITY,
        "heap_bytes_per_row": 1,
        "primary_key_bytes_per_row": 1,
        "weighted_index_bytes_per_row": 1,
        "tier_index_bytes_per_row_per_unit_fraction": 1,
        "archetype_fixed_bytes_per_row": 1,
    }
    search = {
        "migration_010_sha256": "3" * 64,
        "f2d_operator_code_sha256": IDENTITY,
        "measured_010_delta_bytes_per_row": 1,
        "search_fixed_bytes_per_row": 1,
    }
    (archetype if which == "archetype" else search)["f2d_operator_code_sha256"] = "4" * 64
    step0 = {
        "footprint": {
            "measured_footprint_attribution": {
                "system_search": {"generations": {"ratings_v4_prod_p4_opt1": {"attributed_bytes": 11}}}
            },
            "rows_by_generation": {"ratings_v4_prod_p4_opt1": {"search_systems": 2}},
        }
    }

    with pytest.raises(gate.GateRefusal) as error:
        gate.check_footprints(
            archetype,
            search,
            {"fractions_sha256": "2" * 64},
            step0,
            identity=IDENTITY,
            checkout_011_sha256="1" * 64,
            checkout_010_sha256="3" * 64,
            ledger_011_sha256="1" * 64,
            ledger_010_sha256="3" * 64,
        )

    assert error.value.exit_code == 14
    assert error.value.field == f"{which}.f2d_operator_code_sha256"


def test_archetype_footprint_from_a_different_migration_refuses_item_e():
    archetype = {
        "migration_011_sha256": "9" * 64,
        "fractions_sha256": "2" * 64,
        "f2d_operator_code_sha256": IDENTITY,
        "heap_bytes_per_row": 1,
        "primary_key_bytes_per_row": 1,
        "weighted_index_bytes_per_row": 1,
        "tier_index_bytes_per_row_per_unit_fraction": 1,
        "archetype_fixed_bytes_per_row": 1,
    }
    search = {
        "migration_010_sha256": "3" * 64,
        "f2d_operator_code_sha256": IDENTITY,
        "measured_010_delta_bytes_per_row": 1,
        "search_fixed_bytes_per_row": 1,
    }
    step0 = {
        "footprint": {
            "measured_footprint_attribution": {
                "system_search": {
                    "generations": {
                        "ratings_v4_prod_p4_opt1": {"attributed_bytes": 11}
                    }
                }
            },
            "rows_by_generation": {
                "ratings_v4_prod_p4_opt1": {"search_systems": 2}
            },
        }
    }

    with pytest.raises(gate.GateRefusal) as error:
        gate.check_footprints(
            archetype,
            search,
            {"fractions_sha256": "2" * 64},
            step0,
            identity=IDENTITY,
            checkout_011_sha256="1" * 64,
            checkout_010_sha256="3" * 64,
            ledger_011_sha256="1" * 64,
            ledger_010_sha256="3" * 64,
        )

    assert error.value.exit_code == 14
    assert error.value.field == "archetype.migration_011_sha256"


def test_real_pre010_bytes_rounds_up_to_406():
    step0 = {
        "footprint": {
            "measured_footprint_attribution": {
                "system_search": {
                    "generations": {
                        "ratings_v4_prod_p4_opt1": {"attributed_bytes": 80_522_969_088}
                    }
                }
            },
            "rows_by_generation": {
                "ratings_v4_prod_p4_opt1": {"search_systems": 198_528_286}
            },
        }
    }

    assert gate.real_pre010_bytes_per_row(step0)[0] == 406


def test_volume_exact_boundary_passes_and_one_byte_below_refuses():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    step0 = {
        "footprint": {
            "host_disk": {
                "filesystem": "/dev/md1",
                "mount_destination": "/var/lib/postgresql",
            }
        }
    }
    volume = {
        "filesystem": "/dev/md1",
        "filesystem_type": "ext4",
        "size_bytes": 1_000,
        "used_bytes": 500,
        "mount_destination": "/var/lib/postgresql/data",
        "mount_source": "/var/lib/docker/volumes/database/_data",
        "read_at": now.isoformat(),
        "avail_bytes": 100,
    }

    assert gate.check_volume(volume, step0, 100, now=now)["status"] == "passed"
    volume["avail_bytes"] = 99
    with pytest.raises(gate.GateRefusal) as error:
        gate.check_volume(volume, step0, 100, now=now)
    assert error.value.exit_code == 15


@pytest.mark.parametrize("offset", [-901, 1])
def test_volume_must_be_from_the_last_fifteen_minutes(offset):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    volume = {
        "filesystem": "/dev/md1",
        "filesystem_type": "ext4",
        "size_bytes": 1_000,
        "used_bytes": 500,
        "mount_destination": "/var/lib/postgresql/data",
        "mount_source": "/var/lib/docker/volumes/database/_data",
        "read_at": (now + timedelta(seconds=offset)).isoformat(),
        "avail_bytes": 100,
    }
    step0 = {"footprint": {"host_disk": {"filesystem": "/dev/md1", "mount_destination": "/var/lib/postgresql"}}}

    with pytest.raises(gate.GateRefusal) as error:
        gate.check_volume(volume, step0, 1, now=now)
    assert error.value.exit_code == 15


def test_sealed_failure_receipt_names_mismatched_field():
    receipt = gate._failure_receipt(
        identity=IDENTITY,
        code=14,
        item="e",
        reason="migration mismatch",
        field="migration_011_sha256",
        expected="1" * 64,
        actual="2" * 64,
        context={
            "item_results": [{"item": "a", "status": "passed"}],
            "inputs": {"volume_reading": {"avail_bytes": 99}},
            "intermediates": {"system_search": {"term_charged": 20}},
            "projected_archetype_bytes": 80,
            "projected_search_bytes": 20,
            "projected_new_bytes": 100,
            "required_bytes": 115,
            "available_bytes": 99,
            "generation": {"derived_generation_id": "generation"},
        },
    )
    body = dict(receipt)
    seal = body.pop("content_sha256")

    assert receipt["exit_code"] == 14
    assert receipt["failures"][0]["field"] == "migration_011_sha256"
    assert receipt["item_results"][0] == {"item": "a", "status": "passed"}
    assert receipt["inputs"]["volume_reading"]["avail_bytes"] == 99
    assert receipt["projected_new_bytes"] == 100
    assert receipt["headroom_bytes"] == -16
    assert seal == gate.hashlib.sha256(gate.canonical_json(body).encode()).hexdigest()


def test_valid_zero_byte_build_start_is_not_treated_as_absent(tmp_path):
    from scripts.operator.lib import f2d_evidence

    payload = f2d_evidence.seal(
        {
            "schema_version": gate.BUILD_START_SCHEMA,
            "product_code": "system_search",
            "derived_generation_id": "generation",
            "manifest_sha256": "1" * 64,
            "relation_total_bytes_at_start": 0,
            "started_at": "2026-10-13T12:00:00+00:00",
            "f2d_operator_code_sha256": IDENTITY,
        }
    )
    (tmp_path / "build-start-receipt.json").write_text(
        gate.canonical_json(payload), encoding="utf-8"
    )

    start, reason = gate._start_bytes(
        tmp_path, "system_search", "generation", "1" * 64, IDENTITY
    )

    assert start == 0
    assert reason == "matched sealed build-start receipt"


def test_malformed_build_start_timestamp_refuses_live_state(tmp_path):
    from scripts.operator.lib import f2d_evidence

    payload = f2d_evidence.seal(
        {
            "schema_version": gate.BUILD_START_SCHEMA,
            "product_code": "system_search",
            "derived_generation_id": "generation",
            "manifest_sha256": "1" * 64,
            "relation_total_bytes_at_start": 123,
            "started_at": "not-a-timestamp",
            "f2d_operator_code_sha256": IDENTITY,
        }
    )
    (tmp_path / "build-start-receipt.json").write_text(
        gate.canonical_json(payload), encoding="utf-8"
    )

    with pytest.raises(gate.GateRefusal) as error:
        gate._start_bytes(
            tmp_path, "system_search", "generation", "1" * 64, IDENTITY
        )

    assert error.value.exit_code == 16
    assert error.value.field == "system_search.build_start_receipt.started_at"


def test_sealed_chunk_systems_must_match_canonical_plan():
    class Result:
        @staticmethod
        def fetchall():
            return [(7, 9)]

    class Connection:
        @staticmethod
        def execute(statement, parameters):
            assert parameters == ("generation",)
            return Result()

    with pytest.raises(gate.GateRefusal) as error:
        gate._sealed_chunks(
            Connection(), "generation", "system_search", {7: 10}
        )

    assert error.value.exit_code == 16
    assert error.value.field == "system_search.chunk[7].systems"


@pytest.mark.parametrize("attested", [None, "NOT-A-SHA"])
def test_missing_or_malformed_attested_identity_refuses_before_argument_parsing(
    tmp_path, monkeypatch, attested
):
    output = tmp_path / "identity-refusal.json"
    if attested is None:
        monkeypatch.delenv(gate.DEFAULT_IDENTITY_ENV, raising=False)
    else:
        monkeypatch.setenv(gate.DEFAULT_IDENTITY_ENV, attested)

    code = gate.main(["--not-a-real-option", "value", "--output", str(output)])

    assert code == 2
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["exit_code"] == 2
    assert receipt["item_results"][0]["item"] == "identity"


def test_committed_synthetic_archetype_footprint_is_gate_ineligible():
    path = ROOT / "docs/operations/evidence/2026-10-10-wide-archetype-footprint-200k.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    from scripts.dev.measure_wide_archetype_footprint import (
        validate_archetype_footprint_receipt,
    )

    with pytest.raises(gate.GateRefusal) as error:
        gate.validate_footprint_receipts(
            payload,
            {},
            archetype_validator=validate_archetype_footprint_receipt,
            search_validator=lambda value: value,
        )

    assert error.value.exit_code == 14
    assert error.value.field == "archetype.content_sha256"


def test_failure_receipt_preserves_capacity_inputs_and_intermediates():
    context = {
        "item_results": [{"item": "a", "status": "passed"}],
        "inputs": {"volume_reading": {"avail_bytes": 99}, "system_count": 5},
        "intermediates": {"projected_heap_bytes": 10},
        "projected_archetype_bytes": 70,
        "projected_search_bytes": 30,
        "projected_new_bytes": 100,
        "required_bytes": 115,
        "available_bytes": 99,
        "generation": {"derived_generation_id": "generation"},
    }

    receipt = gate._failure_receipt(
        identity=IDENTITY,
        code=15,
        item="f",
        reason="insufficient space",
        field="available_bytes",
        expected=115,
        actual=99,
        context=context,
    )

    assert receipt["inputs"] == context["inputs"]
    assert receipt["intermediates"] == context["intermediates"]
    assert receipt["projected_new_bytes"] == 100
    assert receipt["required_bytes"] == 115
    assert receipt["available_bytes"] == 99
    assert receipt["headroom_bytes"] == -16
    assert [result["item"] for result in receipt["item_results"]] == ["a", "f"]


def test_run_gate_pass_receipt_reports_all_inputs_and_intermediates(
    tmp_path, monkeypatch
):
    from scripts import v3_archetype_calibration_complete as calibration
    from scripts.operator.lib import f2d_evidence

    generation_id = "11111111-1111-1111-1111-111111111111"
    canonical_id = "22222222-2222-2222-2222-222222222222"
    generation_key = "ratings_v4_prod_p4_parallel_v1"
    coefficients = {"alpha": 1}
    code_identity = {"builder": "1" * 64}
    model_digest = "2" * 64
    model_path = tmp_path / "shared_contracts/v3_system_archetype_model.py"
    model_path.parent.mkdir(parents=True)
    model_path.write_text("# model fixture\n", encoding="utf-8")
    model_file_sha = gate.hashlib.sha256(model_path.read_bytes()).hexdigest()
    migration_010 = tmp_path / "sql/v3/migrations/010_v3_system_search_body_type_counts.sql"
    migration_011 = tmp_path / "sql/v3/migrations/011_v3_system_archetype.sql"
    migration_010.parent.mkdir(parents=True)
    migration_010.write_text("-- 010 fixture\n", encoding="utf-8")
    migration_011.write_text("-- 011 fixture\n", encoding="utf-8")
    migration_010_sha = gate.hashlib.sha256(migration_010.read_bytes()).hexdigest()
    migration_011_sha = gate.hashlib.sha256(migration_011.read_bytes()).hexdigest()

    class Generation(SimpleNamespace):
        def __init__(self, **values):
            super().__init__(**values)

    def archetype_manifest(generation):
        return {
            "product_code": "system_archetype",
            "derived_generation_id": generation.identifier,
            "coefficients": coefficients,
        }

    def search_manifest(generation):
        return {
            "product_code": "system_search",
            "derived_generation_id": generation.identifier,
        }

    expected_manifest = archetype_manifest(
        Generation(identifier=generation_id)
    )
    expected_manifest_sha = f2d_evidence.canonical_sha256(expected_manifest)
    complete = f2d_evidence.seal(
        {
            "mode": "complete",
            "generation": {
                "generation_key": generation_key,
                "derived_generation_id": generation_id,
                "publication_sequence": 1,
            },
            "system_count": 5,
            "chunk_plan": {
                "sha256": f2d_evidence.canonical_sha256([[0, 5]])
            },
            "per_archetype": _histogram(),
            "coefficients": coefficients,
            "code_identity": code_identity,
            "archetype_model_sha256": model_digest,
            "model_file_sha256": model_file_sha,
            "expected_product_manifest": expected_manifest,
            "expected_product_manifest_sha256": expected_manifest_sha,
            "sigma_all": 1.6,
            "f2d_operator_code_sha256": IDENTITY,
        }
    )
    decision = f2d_evidence.seal(
        {
            "coefficient_decision": "accepted",
            "coefficients": coefficients,
            "complete_receipt_content_sha256": complete["content_sha256"],
        }
    )
    fractions = _fraction_file(complete)
    archetype_footprint = f2d_evidence.seal(
        {
            "capacity_gate_eligible": True,
            "score_distribution_source": "measured-histogram",
            "migration_011_sha256": migration_011_sha,
            "fractions_sha256": fractions["fractions_sha256"],
            "f2d_operator_code_sha256": IDENTITY,
            "heap_bytes_per_row": 1,
            "primary_key_bytes_per_row": 1,
            "weighted_index_bytes_per_row": 1,
            "tier_index_bytes_per_row_per_unit_fraction": 1,
            "archetype_fixed_bytes_per_row": 1,
        }
    )
    search_footprint = f2d_evidence.seal(
        {
            "capacity_gate_eligible": True,
            "migration_010_sha256": migration_010_sha,
            "f2d_operator_code_sha256": IDENTITY,
            "measured_010_delta_bytes_per_row": 1,
            "search_fixed_bytes_per_row": 1,
        }
    )
    step0 = {
        "footprint": {
            "host_disk": {
                "filesystem": "/dev/test",
                "mount_destination": "/var/lib/postgresql",
            },
            "measured_footprint_attribution": {
                "system_search": {
                    "generations": {
                        "ratings_v4_prod_p4_opt1": {"attributed_bytes": 11}
                    }
                }
            },
            "rows_by_generation": {
                "ratings_v4_prod_p4_opt1": {"search_systems": 2}
            },
        }
    }
    now = datetime.now(timezone.utc).replace(microsecond=0)
    volume = {
        "filesystem": "/dev/test",
        "filesystem_type": "ext4",
        "size_bytes": 1_000,
        "used_bytes": 100,
        "avail_bytes": 100,
        "read_at": now.isoformat(),
        "mount_source": "/volume/test",
        "mount_destination": "/var/lib/postgresql/data",
    }

    evidence_values = {
        f2d_evidence.COMPLETE_RECEIPT: complete,
        f2d_evidence.COEFFICIENT_DECISION: decision,
        f2d_evidence.FRACTIONS: fractions,
        f2d_evidence.ARCHETYPE_FOOTPRINT: archetype_footprint,
        f2d_evidence.SEARCH_FOOTPRINT: search_footprint,
        f2d_evidence.STEP0_RECEIPT: step0,
    }
    for relative, value in evidence_values.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(gate.canonical_json(value), encoding="utf-8")
    volume_path = tmp_path / "volume.json"
    volume_path.write_text(gate.canonical_json(volume), encoding="utf-8")

    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(
        gate,
        "_live_generation",
        lambda *_: {
            "identifier": generation_id,
            "key": generation_key,
            "state": "PUBLISHED",
            "expected_systems": 5,
            "canonical_generation_id": canonical_id,
            "canonical_publication_sequence": 1,
            "manifest": {"canonical_schema": "v3_gen_fixture"},
            "publication_sequence": 1,
        },
    )
    monkeypatch.setattr(
        gate,
        "_chunk_plan",
        lambda *_: ([[0, 5]], 5, f2d_evidence.canonical_sha256([[0, 5]])),
    )
    monkeypatch.setattr(gate, "_live_system_count", lambda *_: 5)
    monkeypatch.setattr(
        gate,
        "_ledger_hash",
        lambda _connection, name: (
            migration_011_sha if name.startswith("011") else migration_010_sha
        ),
    )
    monkeypatch.setattr(gate, "_product_rows", lambda *_: {})
    monkeypatch.setattr(gate, "_sealed_chunks", lambda *_: ([], 0))

    modules = {
        "evidence": f2d_evidence,
        "calibration": SimpleNamespace(
            validate_complete_receipt=calibration.validate_complete_receipt,
            validate_per_chunk_log=lambda *_: [],
        ),
        "archetype_builder": SimpleNamespace(
            Generation=Generation,
            _coefficients=lambda: coefficients,
            code_identity=lambda: code_identity,
            product_manifest=archetype_manifest,
        ),
        "search_builder": SimpleNamespace(
            Generation=Generation,
            product_manifest=search_manifest,
        ),
        "model": SimpleNamespace(
            ARCHETYPE_KEYS=KEYS,
            archetype_model_sha256=lambda: model_digest,
        ),
        "archetype_footprint": SimpleNamespace(
            validate_archetype_footprint_receipt=lambda value: value
        ),
        "search_footprint": SimpleNamespace(
            validate_search_footprint_receipt=lambda value: value
        ),
    }
    args = SimpleNamespace(
        generation_key=generation_key,
        generation_id=generation_id,
        publication_sequence=1,
        volume_reading=volume_path,
        complete_state=tmp_path / "complete-state",
        search_state=tmp_path / "search-state",
        archetype_state=tmp_path / "archetype-state",
        image_model_file=model_path,
    )

    exit_code, receipt = gate.run_gate(
        object(), args, identity=IDENTITY, modules=modules, now=now
    )

    assert exit_code == 0
    assert receipt["status"] == "passed"
    assert [result["item"] for result in receipt["item_results"]] == list("abcdef")
    assert receipt["inputs"]["complete_receipt_content_sha256"] == complete["content_sha256"]
    assert receipt["inputs"]["coefficient_decision_content_sha256"] == decision["content_sha256"]
    assert receipt["inputs"]["fractions_content_sha256"] == f2d_evidence.canonical_sha256(fractions)
    assert receipt["inputs"]["costs"]["real_pre010_bytes_per_row"] == 6
    assert receipt["inputs"]["system_count_sources"] == {
        "complete_receipt": 5,
        "derived_generation": 5,
        "build_chunk": 5,
    }
    assert receipt["intermediates"]["projected_heap_bytes"] == 5
    assert receipt["intermediates"]["projected_fixed_index_bytes"] == 10
    assert receipt["intermediates"]["projected_tier_index_bytes"] == 8
    assert receipt["projected_archetype_bytes"] == 23
    assert receipt["projected_search_bytes"] == 35
    assert receipt["projected_new_bytes"] == 58
    assert receipt["required_bytes"] == 67
    assert receipt["available_bytes"] == 100
    assert receipt["headroom_bytes"] == 33
    body = dict(receipt)
    seal = body.pop("content_sha256")
    assert seal == f2d_evidence.canonical_sha256(body)


def _search_product(state: str, status: str, manifest: str) -> dict:
    return {
        "lifecycle_state": state,
        "validation_receipt": {"status": status},
        "manifest_sha256": manifest,
    }


def test_ready_verified_search_product_counts_only_for_the_current_manifest():
    current = "a" * 64
    assert gate._ready_verified_search_product(
        _search_product("READY", "VERIFIED", current), current
    ) is True
    # Not READY/VERIFIED: fall through to the normal projection.
    assert gate._ready_verified_search_product(None, current) is False
    assert gate._ready_verified_search_product(
        _search_product("BUILDING", "VERIFIED", current), current
    ) is False
    assert gate._ready_verified_search_product(
        _search_product("READY", "FAILED", current), current
    ) is False

    # A READY product for another manifest is refused, never charged zero.
    with pytest.raises(gate.GateRefusal) as error:
        gate._ready_verified_search_product(
            _search_product("READY", "VERIFIED", "b" * 64), current
        )
    assert error.value.exit_code == 16
    assert error.value.field == "system_search.manifest_sha256"

