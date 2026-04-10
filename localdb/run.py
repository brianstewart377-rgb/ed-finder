#!/usr/bin/env python3
"""
ED:Finder Local DB — Standalone runner
======================================
Convenience wrapper for running import_systems.py or eddn_listener.py
from within the Docker container.

Usage (via docker exec or docker-compose run):

  # Import systems (Phase 1 — ~25-45 min):
  docker exec ed-finder-api python3 /app/localdb/run.py import-systems

  # Download and import systems:
  docker exec ed-finder-api python3 /app/localdb/run.py import-systems --download

  # Import full galaxy with bodies (Phase 2 — many hours):
  docker exec ed-finder-api python3 /app/localdb/run.py import-galaxy --download

  # Apply nightly delta:
  docker exec ed-finder-api python3 /app/localdb/run.py delta

  # Show local DB status:
  docker exec ed-finder-api python3 /app/localdb/run.py status

Note: The EDDN listener runs as its own container (ed-finder-eddn) via docker-compose.
      You don't need to start it manually.
"""
import sys, os

# Add this directory to path
sys.path.insert(0, os.path.dirname(__file__))

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    db = os.getenv("GALAXY_DB_PATH", "/data/galaxy.db")

    if cmd == "import-systems":
        from import_systems import main as _main
        sys.argv = [sys.argv[0], "--db", db] + args
        _main()

    elif cmd == "import-galaxy":
        from import_systems import main as _main
        sys.argv = [sys.argv[0], "--db", db, "--galaxy"] + args
        _main()

    elif cmd == "delta":
        from nightly_delta import main as _main
        sys.argv = [sys.argv[0], "--db", db] + args
        _main()

    elif cmd == "status":
        from local_search import local_db_status
        import json
        s = local_db_status()
        print(json.dumps(s, indent=2))

    elif cmd == "rebuild-indexes":
        from import_systems import open_db, create_indexes
        conn = open_db(db)
        create_indexes(conn)
        conn.close()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
