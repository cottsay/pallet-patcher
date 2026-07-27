# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path

from pallet_patcher.command import load_and_compose
from pallet_patcher.inplace import apply_in_place
from pallet_patcher.manifest import load_manifest

_PACKAGES_PATH = Path(__file__).parent / 'packages'

_SEARCH_PATHS = (
    _PACKAGES_PATH / 'upper_layer',
    _PACKAGES_PATH / 'lower_layer',
)


def _write_manifest(tmp_path, body):
    manifest_path = tmp_path / 'Cargo.toml'
    manifest_path.write_text(body)
    return manifest_path


def _apply(manifest_path):
    _composition, direct = load_and_compose(manifest_path, _SEARCH_PATHS)
    apply_in_place(manifest_path, direct)


def test_inplace_patches_inline_dependencies(tmp_path):
    manifest_path = _write_manifest(tmp_path, '\n'.join((
        '[package]',
        'name = "consumer"',
        'version = "0.1.0"',
        '',
        '[dependencies]',
        'pkg-a = "=1.0.0"',
        'pkg-c = { version = "*", features = ["x"], optional = true }',
        'core = { package = "pkg-a", version = "1.1.0" }',
        '',
    )))

    _apply(manifest_path)

    manifest = load_manifest(manifest_path)
    dependencies = manifest['dependencies']

    # The bare-string dependency became a local path.
    pkg_a = dependencies['pkg-a']
    assert set(pkg_a) == {'path'}
    assert pkg_a['path'].endswith('pkg-a-1.0.0')

    # Extra keys are preserved and the version specifier is dropped.
    pkg_c = dependencies['pkg-c']
    assert 'version' not in pkg_c
    assert pkg_c['features'] == ['x']
    assert pkg_c['optional'] is True
    assert pkg_c['path'].endswith('pkg-c-0.0.0')

    # A renamed dependency resolves via its 'package' and keeps that key.
    core = dependencies['core']
    assert core['package'] == 'pkg-a'
    assert 'version' not in core
    assert core['path'].endswith('pkg-a-1.1.0')


def test_inplace_creates_backup_and_preserves_original(tmp_path):
    body = '\n'.join((
        '[package]',
        'name = "consumer"',
        'version = "0.1.0"',
        '',
        '[dependencies]',
        'pkg-a = "=1.0.0"',
        '',
    ))
    manifest_path = _write_manifest(tmp_path, body)

    _apply(manifest_path)

    backup_path = tmp_path / 'Cargo.toml.orig'
    assert backup_path.exists()
    assert backup_path.read_text() == body

    # Re-running must not clobber the pristine backup.
    _apply(manifest_path)
    assert backup_path.read_text() == body


def test_inplace_leaves_unresolved_and_local_dependencies(tmp_path):
    body = '\n'.join((
        '[package]',
        'name = "consumer"',
        'version = "0.1.0"',
        '',
        '[dependencies]',
        'not-found = "9.9.9"',
        'already-local = { path = "../elsewhere" }',
        '',
    ))
    manifest_path = _write_manifest(tmp_path, body)

    _apply(manifest_path)

    # Nothing resolved locally, so the manifest and its backup are untouched.
    assert manifest_path.read_text() == body
    assert not (tmp_path / 'Cargo.toml.orig').exists()


def test_inplace_patches_table_section_dependencies(tmp_path):
    manifest_path = _write_manifest(tmp_path, '\n'.join((
        '[package]',
        'name = "consumer"',
        'version = "0.1.0"',
        '',
        '[dependencies.table-form]',
        'package = "pkg-a"',
        'version = "1.1.0"',
        'features = ["y"]',
        '',
    )))

    _apply(manifest_path)

    dependency = load_manifest(manifest_path)['dependencies']['table-form']
    # The source specifier is dropped, path injected, extras preserved.
    assert 'version' not in dependency
    assert dependency['package'] == 'pkg-a'
    assert dependency['features'] == ['y']
    assert dependency['path'].endswith('pkg-a-1.1.0')


def test_inplace_repoints_mismatched_path_dependency(tmp_path):
    manifest_path = _write_manifest(tmp_path, '\n'.join((
        '[package]',
        'name = "consumer"',
        'version = "0.1.0"',
        '',
        '[dependencies]',
        'pkg-a = { path = "../nowhere", version = "=1.0.0" }',
        '',
    )))

    _apply(manifest_path)

    # A path dependency resolving to a different local crate is re-pointed,
    # matching what the args/toml formats emit for the same manifest.
    pkg_a = load_manifest(manifest_path)['dependencies']['pkg-a']
    assert set(pkg_a) == {'path'}
    assert pkg_a['path'].endswith('pkg-a-1.0.0')


def test_inplace_patches_whole_table_dependencies(tmp_path):
    # Dependencies declared as a single root-level inline table have no
    # [dependencies] section, but editing the parsed structure handles every
    # syntactic form uniformly.
    manifest_path = _write_manifest(tmp_path, '\n'.join((
        'dependencies = { pkg-a = "=1.0.0" }',
        '',
        '[package]',
        'name = "consumer"',
        'version = "0.1.0"',
        '',
    )))

    _apply(manifest_path)

    pkg_a = load_manifest(manifest_path)['dependencies']['pkg-a']
    assert set(pkg_a) == {'path'}
    assert pkg_a['path'].endswith('pkg-a-1.0.0')


def test_inplace_leaves_matching_path_dependency(tmp_path):
    # A path already pointing at the resolved crate is left untouched, since
    # Cargo cannot patch a dependency to the location it already references.
    # Use a forward-slash path: backslashes are escape characters in TOML
    # basic strings, so a raw Windows path (e.g. ``D:\a\...``) is invalid TOML.
    target = (_PACKAGES_PATH / 'lower_layer' / 'pkg-a-1.0.0').as_posix()
    body = '\n'.join((
        '[package]',
        'name = "consumer"',
        'version = "0.1.0"',
        '',
        '[dependencies]',
        f'pkg-a = {{ path = "{target}", version = "=1.0.0" }}',
        '',
    ))
    manifest_path = _write_manifest(tmp_path, body)

    _apply(manifest_path)

    assert manifest_path.read_text() == body
    assert not (tmp_path / 'Cargo.toml.orig').exists()
