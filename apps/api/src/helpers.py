"""Pure-Python helpers that are called by multiple routers.

Nothing in here touches module-level state directly — takes things as
arguments, returns values. Easy to unit test.
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger('ed_finder')

SOL_ID64 = 10477373803


def safe_coords_from_row(row: Any) -> dict[str, float | None]:
    """Return a trusted coordinate triple from a DB/API row.

    The systems table historically used NOT NULL DEFAULT 0 for x/y/z, so
    import paths without coordinates produced fake origin records. Sol is the
    only real system at (0,0,0); every other all-zero triple is unknown.
    """
    if row is None:
        return {'x': None, 'y': None, 'z': None}
    get = row.get if hasattr(row, 'get') else row.__getitem__
    try:
        x = get('x')
        y = get('y')
        z = get('z')
        id64 = get('id64')
    except Exception:
        return {'x': None, 'y': None, 'z': None}

    if x is None or y is None or z is None:
        return {'x': None, 'y': None, 'z': None}

    try:
        fx, fy, fz = float(x), float(y), float(z)
    except (TypeError, ValueError):
        return {'x': None, 'y': None, 'z': None}

    try:
        numeric_id64 = int(id64) if id64 is not None else None
    except (TypeError, ValueError):
        numeric_id64 = None

    if fx == 0.0 and fy == 0.0 and fz == 0.0 and numeric_id64 != SOL_ID64:
        return {'x': None, 'y': None, 'z': None}

    return {'x': fx, 'y': fy, 'z': fz}


# ---------------------------------------------------------------------------
# DB-row flattening
# ---------------------------------------------------------------------------
def sys_row_to_dict(r: Any) -> dict:
    """Convert an asyncpg Record to the wire shape the frontend understands.

    Mirrors the column layout produced by the main search query — if the
    search SQL changes, this translator must change alongside it.
    """
    if r is None:
        return {}
    d = dict(r)
    coords = safe_coords_from_row(d)
    d['id64']        = d.get('id64')
    d['name']        = d.get('name', 'Unknown')
    d['x']           = coords['x']
    d['y']           = coords['y']
    d['z']           = coords['z']
    d['coords']      = coords
    d['distance']    = d.get('distance')
    d['population']  = d.get('population')
    d['archetype_score'] = d.get('archetype_score')
    d['archetype_tier'] = d.get('archetype_tier')
    d['primary_archetype'] = d.get('primary_archetype')
    d['secondary_archetype'] = d.get('secondary_archetype')
    d['archetype_confidence'] = d.get('archetype_confidence')
    d['overall_development_potential'] = d.get('overall_development_potential')
    d['buildability_score'] = d.get('buildability_score')
    d['build_complexity'] = d.get('build_complexity')
    d['purity_score'] = d.get('purity_score')
    d['contamination_risk'] = d.get('contamination_risk')
    d['est_total_slots'] = d.get('est_total_slots')
    d['tags'] = list(d.get('tags') or d.get('display_tags') or [])
    d['primaryEconomy']   = d.get('primary_economy',   'Unknown')
    d['secondaryEconomy'] = d.get('secondary_economy', 'None')
    d['security']         = d.get('security',   'Unknown')
    d['allegiance']       = d.get('allegiance', 'Unknown')
    d['government']       = d.get('government', 'Unknown')
    d['is_colonised']        = d.get('is_colonised', False)
    d['is_being_colonised']  = d.get('is_being_colonised', False)
    d['bodies'] = d.get('bodies', [])
    return d


# ---------------------------------------------------------------------------
# Cluster rebuild subprocess runner (triggered by admin endpoint).
#
# The caller MUST have already claimed the active_jobs slot inside the
# active_jobs_lock; this function only updates the terminal state.
# ---------------------------------------------------------------------------
def run_cluster_rebuild(active_jobs: dict[str, Any]) -> None:
    """Run build_clusters.py as a subprocess and record status."""
    job_id = 'cluster_rebuild'
    try:
        compose_dir = os.environ.get('COMPOSE_PROJECT_DIR', '/opt/ed-finder')
        cmd = [
            'docker', 'compose',
            '--project-directory', compose_dir,
            '--profile', 'import',
            'run', '--rm', 'importer',
            'python3', 'build_clusters.py', '--dirty-only', '--workers', '6',
        ]
        log.info('Triggering background cluster rebuild: %s', ' '.join(cmd))
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        active_jobs[job_id].update({
            'status':   'completed',
            'end_time': datetime.now(timezone.utc).isoformat(),
            'exit_code': 0,
        })
        log.info('Background cluster rebuild completed successfully.')
    except subprocess.CalledProcessError as e:
        active_jobs[job_id].update({
            'status':   'failed',
            'end_time': datetime.now(timezone.utc).isoformat(),
            'exit_code': e.returncode,
            'error':    e.stderr or str(e),
        })
        log.error('Background cluster rebuild failed (exit %d): %s', e.returncode, e.stderr)
    except Exception as e:
        active_jobs[job_id].update({
            'status':   'failed',
            'end_time': datetime.now(timezone.utc).isoformat(),
            'error':    str(e),
        })
        log.exception('Unexpected error during background cluster rebuild')
