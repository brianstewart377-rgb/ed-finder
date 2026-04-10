#!/usr/bin/env python3
"""
ED:Finder — EDDN ZeroMQ Listener
==================================
Subscribes to the EDDN relay (tcp://eddn.edcd.io:9500) and updates
the local galaxy.db with real-time colonisation data.

Relevant schemas processed:
  - journal/FSDJump/1    → system coords, population, faction presence
  - journal/Location/1   → same as FSDJump
  - journal/Scan/1       → body data (atmospheres, rings, signals, etc.)
  - colonisation/1       → direct colonisation status (if/when schema exists)

Data written:
  - colonisation table   (population, is_colonised, controlling_faction, etc.)
  - systems table        (coords if system is new — fills gaps in dump)

Usage:
    python3 eddn_listener.py [--db /data/galaxy.db] [--verbose]

Runs forever; restart on crash using the systemd service or Docker restart policy.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import time
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

try:
    import zmq
except ImportError:
    print("ERROR: pyzmq not installed. Run: pip install pyzmq")
    raise

# ── Config ────────────────────────────────────────────────────────────────────
EDDN_RELAY      = "tcp://eddn.edcd.io:9500"
DEFAULT_DB      = "/data/galaxy.db"
RECONNECT_DELAY = 15       # seconds before reconnect on error
SUBSCRIBE_TOPIC = b""      # subscribe to all topics

# Schemas we care about
FSDJ_SCHEMA     = "https://eddn.edcd.io/schemas/journal/1"
SCAN_SCHEMA     = "https://eddn.edcd.io/schemas/fsssignalsdiscovered/1"
NAVBEACON_SCHEMA= "https://eddn.edcd.io/schemas/navbeaconscan/1"
COLONISE_SCHEMA = "https://eddn.edcd.io/schemas/colonisation/1"  # future

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger("eddn_listener")


# ── DB helpers ────────────────────────────────────────────────────────────────
def open_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-32000")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_conn(path: str):
    conn = open_db(path)
    try:
        yield conn
    finally:
        conn.close()


def ensure_colonisation_table(conn: sqlite3.Connection) -> None:
    """Ensure the colonisation table exists (may be called before galaxy import)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS systems (
            id64          INTEGER PRIMARY KEY,
            name          TEXT    NOT NULL,
            x             REAL    NOT NULL DEFAULT 0,
            y             REAL    NOT NULL DEFAULT 0,
            z             REAL    NOT NULL DEFAULT 0,
            main_star     TEXT,
            needs_permit  INTEGER NOT NULL DEFAULT 0,
            updated_at    TEXT,
            imported_at   REAL    NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_sys_name ON systems(name);

        CREATE TABLE IF NOT EXISTS colonisation (
            id64          INTEGER PRIMARY KEY,
            population    INTEGER DEFAULT 0,
            is_colonised  INTEGER DEFAULT 0,
            is_being_colonised INTEGER DEFAULT 0,
            controlling_faction TEXT,
            state         TEXT,
            government    TEXT,
            allegiance    TEXT,
            economy       TEXT,
            eddn_updated  REAL,
            spansh_updated REAL
        );
        CREATE INDEX IF NOT EXISTS idx_col_pop       ON colonisation(population);
        CREATE INDEX IF NOT EXISTS idx_col_colonised ON colonisation(is_colonised);

        CREATE TABLE IF NOT EXISTS import_meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
    """)
    conn.commit()


# ── EDDN message processing ───────────────────────────────────────────────────
class EddnProcessor:
    """Process EDDN messages and write updates to galaxy.db."""

    def __init__(self, db_path: str, verbose: bool = False):
        self.db_path = db_path
        self.verbose = verbose
        self._msg_count = 0
        self._update_count = 0
        self._new_systems = 0
        self._start_time = time.time()

        # Ensure tables exist before first message
        with db_conn(db_path) as conn:
            ensure_colonisation_table(conn)
        log.info("EDDN processor ready. DB: %s", db_path)

    def process(self, raw_bytes: bytes) -> None:
        """Decompress and dispatch one EDDN message."""
        try:
            payload = json.loads(zlib.decompress(raw_bytes))
        except Exception as exc:
            log.debug("Failed to parse EDDN message: %s", exc)
            return

        schema = payload.get("$schemaRef", "")
        message = payload.get("message", {})
        event = message.get("event", "")
        self._msg_count += 1

        # Print stats every 1000 messages
        if self._msg_count % 1000 == 0:
            uptime = time.time() - self._start_time
            log.info(
                "EDDN: %d msgs processed | %d DB updates | %d new systems | uptime %.0fs",
                self._msg_count, self._update_count, self._new_systems, uptime,
            )

        # Route by schema + event
        if FSDJ_SCHEMA in schema and event in ("FSDJump", "Location", "CarrierJump"):
            self._handle_jump(message)
        elif COLONISE_SCHEMA in schema:
            self._handle_colonisation(message)

    def _handle_jump(self, msg: dict) -> None:
        """
        FSDJump / Location events contain:
          SystemAddress (= id64), StarSystem (name), StarPos [x,y,z],
          Population, SystemAllegiance, SystemGovernment, SystemEconomy,
          ControllingPower, Factions[], SystemFaction
        """
        id64 = msg.get("SystemAddress")
        name = msg.get("StarSystem")
        if not id64 or not name:
            return

        star_pos = msg.get("StarPos", [0, 0, 0])
        x, y, z = (star_pos + [0, 0, 0])[:3]

        pop = int(msg.get("Population", 0) or 0)
        is_col = 1 if pop > 0 else 0

        # Detect "being colonised": Population=0 but Factions present with
        # a 'Colonisation' state — heuristic until dedicated schema arrives
        factions = msg.get("Factions", []) or []
        is_being_col = 0
        for f in factions:
            states = [s.get("State", "") for s in f.get("ActiveStates", [])]
            if "Colonisation" in states or "Colonised" in states:
                is_being_col = 1
                break

        sys_faction = msg.get("SystemFaction", {}) or {}
        controlling = sys_faction.get("Name") if isinstance(sys_faction, dict) else None
        state = sys_faction.get("FactionState") if isinstance(sys_faction, dict) else None
        government = msg.get("SystemGovernment", "").lstrip("$").rstrip("_i;")
        allegiance = msg.get("SystemAllegiance", "")
        economy = msg.get("SystemEconomy", "").lstrip("$").rstrip("_i;")

        now = time.time()

        with db_conn(self.db_path) as conn:
            # Upsert system coords (INSERT OR IGNORE to avoid clobbering dump data)
            existing = conn.execute(
                "SELECT id64 FROM systems WHERE id64=?", (id64,)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT OR IGNORE INTO systems
                       (id64, name, x, y, z, imported_at)
                       VALUES (?,?,?,?,?,?)""",
                    (id64, name, x, y, z, now),
                )
                self._new_systems += 1
                if self.verbose:
                    log.info("New system from EDDN: %s (id64=%s)", name, id64)

            # Upsert colonisation status
            conn.execute(
                """INSERT INTO colonisation
                   (id64, population, is_colonised, is_being_colonised,
                    controlling_faction, state, government, allegiance, economy,
                    eddn_updated, spansh_updated)
                   VALUES (?,?,?,?,?,?,?,?,?,?,NULL)
                   ON CONFLICT(id64) DO UPDATE SET
                       population          = excluded.population,
                       is_colonised        = excluded.is_colonised,
                       is_being_colonised  = excluded.is_being_colonised,
                       controlling_faction = excluded.controlling_faction,
                       state               = excluded.state,
                       government          = excluded.government,
                       allegiance          = excluded.allegiance,
                       economy             = excluded.economy,
                       eddn_updated        = excluded.eddn_updated""",
                (id64, pop, is_col, is_being_col,
                 controlling, state, government, allegiance, economy, now),
            )
            conn.commit()
            self._update_count += 1

        if self.verbose:
            log.debug(
                "Jump %s: pop=%d col=%d being_col=%d faction=%s",
                name, pop, is_col, is_being_col, controlling,
            )

    def _handle_colonisation(self, msg: dict) -> None:
        """
        Direct colonisation schema (future EDDN schema).
        Will be the most accurate source once Frontier/EDCD publish it.
        """
        id64 = msg.get("SystemAddress")
        if not id64:
            return
        pop = int(msg.get("Population", 0) or 0)
        is_col = 1 if pop > 0 else 0
        is_being_col = 1 if msg.get("ColonisationPhase") else 0
        now = time.time()

        with db_conn(self.db_path) as conn:
            conn.execute(
                """INSERT INTO colonisation
                   (id64, population, is_colonised, is_being_colonised, eddn_updated)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(id64) DO UPDATE SET
                       population         = excluded.population,
                       is_colonised       = excluded.is_colonised,
                       is_being_colonised = excluded.is_being_colonised,
                       eddn_updated       = excluded.eddn_updated""",
                (id64, pop, is_col, is_being_col, now),
            )
            conn.commit()
            self._update_count += 1


# ── ZeroMQ loop ───────────────────────────────────────────────────────────────
def run_listener(db_path: str, verbose: bool = False) -> None:
    processor = EddnProcessor(db_path, verbose=verbose)
    ctx = zmq.Context()

    while True:
        sock = ctx.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, SUBSCRIBE_TOPIC)
        sock.setsockopt(zmq.RCVTIMEO, 60_000)      # 60 s recv timeout
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RECONNECT_IVL, 5_000)  # reconnect every 5 s

        try:
            log.info("Connecting to EDDN relay: %s", EDDN_RELAY)
            sock.connect(EDDN_RELAY)
            log.info("Connected. Listening for events…")

            # Update DB last-seen timestamp every 5 min
            last_meta_update = time.time()

            while True:
                try:
                    raw = sock.recv()
                    processor.process(raw)

                    now = time.time()
                    if now - last_meta_update > 300:
                        with db_conn(db_path) as conn:
                            conn.execute(
                                "INSERT OR REPLACE INTO import_meta (key,value) VALUES (?,?)",
                                ("eddn_last_seen", datetime.now(timezone.utc).isoformat()),
                            )
                            conn.execute(
                                "INSERT OR REPLACE INTO import_meta (key,value) VALUES (?,?)",
                                ("eddn_msg_count", str(processor._msg_count)),
                            )
                            conn.commit()
                        last_meta_update = now

                except zmq.Again:
                    log.warning("EDDN: no message for 60 s — reconnecting…")
                    break

        except KeyboardInterrupt:
            log.info("Listener stopped by user")
            break
        except Exception as exc:
            log.error("EDDN listener error: %s — reconnecting in %ds", exc, RECONNECT_DELAY)
            time.sleep(RECONNECT_DELAY)
        finally:
            sock.close()

    ctx.term()
    log.info("EDDN listener shut down cleanly")


# ── CLI ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="ED:Finder EDDN ZeroMQ listener")
    parser.add_argument("--db",      default=DEFAULT_DB, help="Galaxy SQLite DB path")
    parser.add_argument("--verbose", action="store_true", help="Log every system update")
    args = parser.parse_args()
    run_listener(args.db, verbose=args.verbose)


if __name__ == "__main__":
    main()
