from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_entrypoint_no_longer_imports_redesign_runtime():
    main_source = (ROOT / 'frontend' / 'src' / 'main.tsx').read_text(encoding='utf-8')

    assert "import('./_redesign/RedesignApp.jsx')" not in main_source
    assert 'uiPreview' not in main_source
    assert 'shouldUseRedesign' not in main_source


def test_preview_only_routes_are_no_longer_live_runtime_paths():
    app_source = (ROOT / 'frontend' / 'src' / 'App.tsx').read_text(encoding='utf-8')
    hash_route_source = (ROOT / 'frontend' / 'src' / 'hooks' / 'useHashRoute.ts').read_text(encoding='utf-8')
    navbar_source = (ROOT / 'frontend' / 'src' / 'components' / 'NavBar.tsx').read_text(encoding='utf-8')

    assert 'planner-preview' not in app_source
    assert 'chip-preview' not in app_source
    assert 'planner-preview' not in hash_route_source
    assert 'chip-preview' not in hash_route_source
    assert 'Planner Preview' not in navbar_source
    assert 'Chip Preview' not in navbar_source


def test_redesign_readme_marks_folder_as_archived_reference_only():
    readme = (ROOT / 'docs' / 'archive' / 'frontend-redesign-prototype' / 'README.md').read_text(encoding='utf-8')

    assert 'archived reference' in readme
    assert 'material while the active Stage 25 shell continues' in readme
    assert 'no longer wired into `src/main.tsx`' in readme
    assert "Don't reintroduce the redesign into `main.tsx`" in readme


def test_root_residue_is_archived_out_of_repo_root():
    assert not (ROOT / 'implementation_plan_stage_4a.md').exists()
    assert not (ROOT / 'ED_FINDER_FULL_STACK_ADVERSARIAL_AUDIT_V1(1).md').exists()
    assert not (ROOT / 'robocopy.log').exists()
    assert (ROOT / 'docs' / 'archive' / 'root-residue' / 'implementation_plan_stage_4a.md').exists()
    assert (ROOT / 'docs' / 'archive' / 'root-residue' / 'full-stack-adversarial-audit-v1-duplicate-download.md').exists()


def test_stage18j_historical_wrappers_are_retired_out_of_operator_surface():
    wrapper_names = (
        'stage18j_run_compact_summary.sh',
        'stage18j_run_identity_review_packet.sh',
        'stage18j_run_identity_load_dry_run.sh',
        'stage18j_run_identity_approval_allowlist.sh',
    )
    for name in wrapper_names:
        assert not (ROOT / 'scripts' / 'operator' / name).exists()
        assert not (ROOT / 'scripts' / 'operator' / 'archive' / 'stage18j' / name).exists()

    manifest = (ROOT / 'scripts' / 'operator' / 'archive' / 'stage18j' / 'README.md').read_text(encoding='utf-8')
    assert 'Hetzner-only operator entry points' in manifest
    assert 'fully retired' in manifest
    assert 'runnable wrapper bodies are intentionally not carried into the V3 repository surface' in manifest
    for name in wrapper_names:
        assert f'`{name}`' in manifest
