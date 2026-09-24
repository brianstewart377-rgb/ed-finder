"""Static contract for the governed spatial-pyramid operator script.

No SSH, no DB, no prod: reads the script text and asserts it pins the canonical
generation, gates on migration 012, and exposes build + publish sub-commands.
"""
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'operator' / 'actions' / 'v3-spatial-pyramid.sh'


def test_script_exists():
    assert _SCRIPT.is_file()


def test_pins_canonical_generation_not_ratings_key():
    text = _SCRIPT.read_text(encoding='utf-8')
    assert 'TARGET_CANONICAL_GENERATION=' in text
    assert 'TARGET_CANONICAL_SEQUENCE=' in text
    # The decoupled build must NOT pin a ratings derived generation_key.
    assert 'ratings_v4_prod_p4_opt1' not in text
    assert 'TARGET_GENERATION_KEY' not in text


def test_gates_on_migration_012():
    text = _SCRIPT.read_text(encoding='utf-8')
    assert '012_v3_spatial_pyramid_decouple.sql' in text


def test_exposes_build_and_publish_commands():
    text = _SCRIPT.read_text(encoding='utf-8')
    assert 'publish_spatial_pyramid' in text
    assert ' build)' in text or 'build)' in text
    assert ' publish)' in text or 'publish)' in text


def test_publish_psql_variables_are_delivered_on_stdin_not_command():
    """psql interpolates client-side :'variables' only when it reads the SQL
    from stdin (or -f), never from --command/-c -- there the string reaches the
    server verbatim and a bare `:` is a syntax error.

    The publish path binds actor/reason (the only operator free text that
    crosses into the DB) as :'quoted' psql variables; that quoting IS the
    trust boundary. So the publish SELECT must arrive on psql's stdin
    (`docker exec -i` + a pipe), and no --command/-c string may carry a
    :'variable'. Regression guard for the publish syntax-error bug.
    """
    text = _SCRIPT.read_text(encoding='utf-8')
    assert ":'target'" in text and ":'actor'" in text and ":'reason'" in text
    assert 'docker exec -i "$POSTGRES_CONTAINER" psql' in text
    for line in text.splitlines():
        if '--command' in line or ' -c ' in line:
            assert ":'" not in line, (
                'psql --command/-c line carries a client-side :variable that '
                f'psql will not interpolate: {line.strip()}'
            )
