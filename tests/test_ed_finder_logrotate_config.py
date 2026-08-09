"""Regression test for the production log-rotation config (2026-08-09).

/data/logs/*.log had no rotation at all: import.log reached 4.7G and
nightly.log reached 673M on an already-89%-full disk. This locks in the
config's presence and its two safety-critical properties: it targets
the right path, and it uses copytruncate (required because several of
these logs are held open continuously by long-running containers or
written by cron-invoked scripts with no signal-based reopen support - a
plain rename-based rotation would silently orphan those writers).
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOGROTATE_CONFIG_PATH = ROOT / 'config' / 'ed-finder.logrotate'


def test_logrotate_config_exists():
    assert LOGROTATE_CONFIG_PATH.is_file(), (
        f'{LOGROTATE_CONFIG_PATH} is missing - production log rotation depends on it.'
    )


def test_logrotate_config_targets_the_right_path():
    source = LOGROTATE_CONFIG_PATH.read_text(encoding='utf-8')
    assert '/data/logs/*.log {' in source


def test_logrotate_config_uses_copytruncate():
    source = LOGROTATE_CONFIG_PATH.read_text(encoding='utf-8')
    # Required, not optional - see module docstring. A plain rotation
    # (rename + recreate) would leave continuously-open writers (e.g. the
    # EDDN listener container) appending to a file no longer visible
    # under its original name.
    assert 'copytruncate' in source


def test_logrotate_config_keeps_only_a_few_days():
    source = LOGROTATE_CONFIG_PATH.read_text(encoding='utf-8')
    assert 'daily' in source
    assert 'rotate 3' in source
