import os
import sys
from pathlib import Path


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

from import_spansh import DUMP_FILES, norm_station_type  # noqa: E402


def test_station_type_normaliser_accepts_edsm_labels():
    assert norm_station_type('Coriolis Starport') == 'Coriolis'
    assert norm_station_type('Orbis Starport') == 'Orbis'
    assert norm_station_type('Ocellus Starport') == 'Ocellus'
    assert norm_station_type('Planetary settlement') == 'PlanetaryOutpost'
    assert norm_station_type('Fleet Carrier') == 'FleetCarrier'


def test_edsm_dumps_are_not_added_to_active_heavy_imports():
    assert all('edsm' not in dump_name.lower() for dump_name in DUMP_FILES)
