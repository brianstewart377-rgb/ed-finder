"""Deterministic synthetic large-journal generator for the V3 journal perf lane.

Produces a repeatable ~100k-line Elite Dangerous journal (JSONL) covering the
allowlisted event surface used by the import hot path: Fileheader/LoadGame
headers, then repeating cycles of FSDJump, Location, FSSDiscoveryScan,
FSSAllBodiesFound, Scan (star + planet), FSSBodySignals, SAASignalsFound,
CodexEntry, and the three ScanOrganic stages.

Determinism contract: the same (--lines, --seed) always yields byte-identical
output, so perf runs are comparable across machines and reruns. Everything is
stdlib-only and importable (``generate_lines`` / ``write_large_journal``) so
the perf tests can reuse it without spawning a process.

Output goes to the caller-provided --out path; the repository ignores
``tests/fixtures/journal_v3/generated/`` so generated files are never checked in.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_LINES = 100_000
DEFAULT_SEED = 20260828

_CYCLE_LINES = 12  # one visit cycle per system; see _visit_cycle

_GAME_VERSION = "5.0.0.2100"
_GAME_BUILD = "r310428/r0"
_SECTOR_POOL = [
    "Praea Euq",
    "Col 285 Sector",
    "Synuefe",
    "Swoilz",
    "Hypiae Flyuae",
    "Pru Aescs",
    "Eorl Auwsy",
    "Ceeckia",
]
_STAR_TYPES = ["G", "M", "K", "F"]
_PLANET_CLASSES = ["Rocky body", "Icy body", "High metal content body"]
_GENUSES = [
    ("$Codex_Ent_Genus_Stratum;", "Stratum", "$Codex_Ent_Stratum_07_Name;", "Stratum araneae", "$Codex_Ent_Stratum_07_F;"),
    ("$Codex_Ent_Genus_Tussock;", "Tussock", "$Codex_Ent_Tussocks_01_Name;", "Tussock pennata", "$Codex_Ent_Tussocks_01_A;"),
    ("$Codex_Ent_Genus_Bacterium;", "Bacterium", "$Codex_Ent_Bacterium_08_Name;", "Bacterium informem", "$Codex_Ent_Bacterium_08_A;"),
    ("$Codex_Ent_Genus_Fungus;", "Fungus", "$Codex_Ent_Fungus_01_Name;", "Fungus seta", "$Codex_Ent_Fungus_01_B;"),
    ("$Codex_Ent_Genus_Cactoid;", "Cactoid", "$Codex_Ent_Cactoida_02_Name;", "Cactoida cortexum", "$Codex_Ent_Cactoida_02_F;"),
    ("$Codex_Ent_Genus_Aleoida;", "Aleoida", "$Codex_Ent_Aleoida_04_Name;", "Aleoida arcus", "$Codex_Ent_Aleoida_04_E;"),
]


def _system_name(rng: random.Random, index: int) -> str:
    sector = _SECTOR_POOL[index % len(_SECTOR_POOL)]
    letter = chr(ord("A") + (index // len(_SECTOR_POOL)) % 26)
    return f"{sector} {letter}{letter}-{chr(ord('a') + index % 26)} {index % 100}"


def _system_address(index: int) -> int:
    # Distinct, deterministic uint64-scale addresses (safe integers: < 2**53).
    return 2**52 + index * 7919


def _header_lines(ts: datetime) -> list[str]:
    return [
        json.dumps(
            {
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "event": "Fileheader",
                "part": 1,
                "language": "English/UK",
                "Odyssey": True,
                "gameversion": _GAME_VERSION,
                "build": _GAME_BUILD,
            },
            separators=(",", ":"),
        ),
        json.dumps(
            {
                "timestamp": (ts + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "event": "LoadGame",
                "Commander": "PerfCMDR",
                "FID": "F20260828",
                "Horizons": True,
                "Odyssey": True,
                "Ship": "Anaconda",
                "ShipID": 1,
                "ShipName": "Bench Runner",
                "ShipIdent": "BNCH-01",
                "FuelLevel": 32.0,
                "FuelCapacity": 32.0,
                "GameMode": "Open",
                "Group": "",
                "Credits": 1000000000,
                "Loan": 0,
            },
            separators=(",", ":"),
        ),
    ]


def _line(ts: datetime, record: dict) -> str:
    record = {"timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), **record}
    return json.dumps(record, separators=(",", ":"))


def _visit_cycle(rng: random.Random, ts: datetime, system_index: int, cycle: int) -> list[str]:
    """One 12-line visit: jump in, honk, scan star + one planet, codex, organics."""
    system = _system_name(rng, system_index)
    address = _system_address(system_index)
    star_class = rng.choice(_STAR_TYPES)
    planet_class = rng.choice(_PLANET_CLASSES)
    body_id = 2 + (cycle % 2)
    genus, genus_loc, species, species_loc, variant = rng.choice(_GENUSES)
    entry_id = str(1850000 + rng.randrange(0, 500))
    star_pos = [round(rng.uniform(-200, 200), 4), round(rng.uniform(-200, 200), 4), round(rng.uniform(-200, 200), 4)]
    lat = round(rng.uniform(-89.99, 89.99), 4)
    lon = round(rng.uniform(-179.99, 179.99), 4)
    body_name = f"{system} {body_id}"

    events: list[dict] = [
        {"event": "FSDJump", "StarSystem": system, "SystemAddress": address, "StarPos": star_pos,
         "StarClass": star_class, "JumpDist": round(rng.uniform(3.0, 40.0), 2),
         "FuelUsed": round(rng.uniform(0.5, 2.0), 2), "FuelLevel": round(rng.uniform(20.0, 31.0), 2)},
        {"event": "Location", "StarSystem": system, "SystemAddress": address, "StarPos": star_pos,
         "Body": system, "BodyID": 0, "BodyType": "Star", "Docked": False},
        {"event": "FSSDiscoveryScan", "StarSystem": system, "SystemAddress": address,
         "Progress": 1.0, "BodyCount": 5, "NonBodyCount": 0},
        {"event": "FSSAllBodiesFound", "StarSystem": system, "SystemAddress": address, "Count": 5},
        {"event": "Scan", "ScanType": "Basic", "StarSystem": system, "SystemAddress": address,
         "BodyName": system, "BodyID": 0, "DistanceFromArrivalLS": 0.0, "StarType": star_class,
         "Subclass": rng.randrange(0, 9), "StellarMass": round(rng.uniform(0.1, 2.5), 2),
         "Radius": round(rng.uniform(100000000.0, 1000000000.0), 1),
         "AbsoluteMagnitude": round(rng.uniform(3.0, 10.0), 1),
         "Age_MY": rng.randrange(500, 12000), "SurfaceTemperature": rng.randrange(2500, 10000),
         "Luminosity": rng.choice(["V", "IV", "Va"]), "ScanID": rng.randrange(1000000, 9000000)},
        {"event": "FSSBodySignals", "StarSystem": system, "SystemAddress": address,
         "BodyName": body_name, "BodyID": body_id,
         "Signals": [{"Type": "Biological", "Count": rng.randrange(1, 5)}]},
        {"event": "Scan", "ScanType": "Detailed", "StarSystem": system, "SystemAddress": address,
         "BodyName": body_name, "BodyID": body_id,
         "DistanceFromArrivalLS": round(rng.uniform(500.0, 5000.0), 1),
         "PlanetClass": planet_class, "Atmosphere": "thin carbon dioxide",
         "AtmosphereType": "CarbonDioxide", "Volcanism": "", "MassEM": round(rng.uniform(0.01, 2.0), 2),
         "SurfaceGravity": round(rng.uniform(1.0, 20.0), 1), "SurfacePressure": round(rng.uniform(0.0, 9000.0), 1),
         "Landable": True, "TerraformState": "Not terraformable", "ScanID": rng.randrange(1000000, 9000000)},
        {"event": "SAASignalsFound", "StarSystem": system, "SystemAddress": address,
         "BodyName": body_name, "BodyID": body_id,
         "Signals": [{"Type": "Biological", "Count": rng.randrange(1, 5)}],
         "Genuses": [{"Genus": genus, "Genus_Localised": genus_loc}]},
        {"event": "CodexEntry", "EntryID": entry_id, "Name": species, "Name_Localised": species_loc,
         "SubCategory": "$Codex_SubCategory_Organic_Structures;", "SubCategory_Localised": "Organic Structures",
         "Category": "$Codex_Category_Biology;", "Category_Localised": "Biology",
         "Region": "Synuefe", "System": system, "SystemAddress": address, "BodyID": body_id,
         "Latitude": lat, "Longitude": lon},
        {"event": "ScanOrganic", "ScanType": "Log", "Genus": genus, "Genus_Localised": genus_loc,
         "Species": species, "Species_Localised": species_loc, "Variant": variant,
         "Variant_Localised": species_loc, "SystemAddress": address, "Body": body_id, "BodyName": body_name},
        {"event": "ScanOrganic", "ScanType": "Sample", "Genus": genus, "Genus_Localised": genus_loc,
         "Species": species, "Species_Localised": species_loc, "Variant": variant,
         "Variant_Localised": species_loc, "SystemAddress": address, "Body": body_id, "BodyName": body_name},
        {"event": "ScanOrganic", "ScanType": "Analyse", "Genus": genus, "Genus_Localised": genus_loc,
         "Species": species, "Species_Localised": species_loc, "Variant": variant,
         "Variant_Localised": species_loc, "SystemAddress": address, "Body": body_id, "BodyName": body_name},
    ]

    lines: list[str] = []
    for offset, record in enumerate(events):
        lines.append(_line(ts + timedelta(seconds=offset * 30), record))
    return lines


def generate_lines(count: int = DEFAULT_LINES, seed: int = DEFAULT_SEED) -> list[str]:
    """Return ``count`` deterministic synthetic journal lines (JSONL strings)."""
    if count < 2:
        raise ValueError(f"count must be >= 2, got {count}")
    rng = random.Random(seed)
    start = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
    lines: list[str] = []
    lines.extend(_header_lines(start))
    ts = start + timedelta(seconds=2)
    cycle = 0
    system_index = 0
    while len(lines) < count:
        cycle_lines = _visit_cycle(rng, ts, system_index, cycle)
        remaining = count - len(lines)
        if len(cycle_lines) > remaining:
            lines.extend(cycle_lines[:remaining])
        else:
            lines.extend(cycle_lines)
        ts = ts + timedelta(seconds=len(cycle_lines) * 30)
        cycle += 1
        system_index = (system_index + 1) % 200
    return lines


def write_large_journal(
    path: str | Path,
    count: int = DEFAULT_LINES,
    seed: int = DEFAULT_SEED,
) -> int:
    """Write ``count`` deterministic lines to ``path``; returns the line count."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = generate_lines(count, seed)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lines", type=int, default=DEFAULT_LINES)
    parser.add_argument("--out", type=str, default="generated/large_journal_100k.jsonl")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    written = write_large_journal(args.out, args.lines, args.seed)
    print(f"wrote {written} lines to {args.out} (seed={args.seed})")


if __name__ == "__main__":
    main()
