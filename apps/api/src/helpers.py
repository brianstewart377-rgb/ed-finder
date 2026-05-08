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
    d['id64']        = d.get('id64')
    d['name']        = d.get('name', 'Unknown')
    d['coords']      = {'x': d.get('x', 0), 'y': d.get('y', 0), 'z': d.get('z', 0)}
    d['distance']    = d.get('distance')
    d['population']  = d.get('population', 0)
    d['primaryEconomy']   = d.get('primary_economy',   'Unknown')
    d['secondaryEconomy'] = d.get('secondary_economy', 'None')
    d['security']         = d.get('security',   'Unknown')
    d['allegiance']       = d.get('allegiance', 'Unknown')
    d['government']       = d.get('government', 'Unknown')
    d['is_colonised']        = d.get('is_colonised', False)
    d['is_being_colonised']  = d.get('is_being_colonised', False)
    d['_rating'] = {
        'score':             d.get('score'),
        'scoreAgriculture':  d.get('score_agriculture'),
        'scoreRefinery':     d.get('score_refinery'),
        'scoreIndustrial':   d.get('score_industrial'),
        'scoreHightech':     d.get('score_hightech'),
        'scoreMilitary':     d.get('score_military'),
        'scoreTourism':      d.get('score_tourism'),
        'scoreExtraction':   d.get('score_extraction'),
        'economySuggestion': d.get('economy_suggestion'),
        'breakdown':         d.get('score_breakdown'),
        # v3.1 fields — mirrored in camelCase for frontend parity.
        'terraformingPotential': d.get('terraforming_potential'),
        'bodyDiversity':         d.get('body_diversity'),
        'confidence':            d.get('confidence'),
        'rationale':             d.get('rationale'),
    }
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
