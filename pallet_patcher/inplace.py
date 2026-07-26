# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import shutil
import sys

from pallet_patcher.manifest import DEPENDENCY_CATEGORIES
from pallet_patcher.manifest import dump_manifest
from pallet_patcher.manifest import load_manifest


# Keys which describe *where* a dependency comes from. When we redirect a
# dependency to a local path we drop these and inject our own 'path', while
# preserving every other key (features, optional, default-features, ...).
_SOURCE_KEYS = frozenset((
    'version', 'path', 'git', 'registry', 'branch', 'tag', 'rev',
))

_BACKUP_SUFFIX = '.orig'


def apply_in_place(manifest_path, direct):
    """
    Rewrite a Cargo manifest in place, patching dependencies to local paths.

    The manifest is parsed, the resolved dependencies are edited directly in
    the parsed structure (dropping their source specifier and injecting a local
    ``path`` while preserving every other key), and the result is serialized
    back over the file. A backup of the original manifest is written with a
    ``.orig`` suffix before the file is changed. The set of dependencies
    handled matches what the ``args`` and ``toml`` output formats resolve;
    transitive dependencies live in other crates' manifests and are untouched.

    :param manifest_path: Path to the Cargo.toml file on disk
    :type manifest_path: Path
    :param direct: Direct-dependency map keyed by ``(category, import name)``,
      with ``(reference, candidate directory, package, specification)`` values.
    :type direct: dict
    """
    # (category, import name) -> candidate path string
    resolved = {}
    for (category, key), entry in direct.items():
        reference, candidate, _package, _specification = entry
        if reference is not None and candidate.as_uri() == reference:
            # Cargo cannot patch a dependency to the location it already
            # references; the parse-based formats skip this case too.
            continue
        resolved[(category, key)] = str(candidate)

    if not resolved:
        # No dependencies resolved to a local path; nothing to patch.
        return

    manifest = load_manifest(manifest_path)

    applied = set()
    for category, table in _iter_dependency_tables(manifest):
        for key in list(table):
            path = resolved.get((category, key))
            if path is not None:
                _patch_dependency(table, key, path)
                applied.add((category, key))

    # Every resolved dependency was parsed from this very manifest, so a
    # resolved entry missing from the parsed structure is an internal
    # inconsistency. Bail out before touching the file.
    _report_skipped(sorted(set(resolved) - applied))

    backup_path = manifest_path.parent / (manifest_path.name + _BACKUP_SUFFIX)
    if backup_path.exists():
        print(
            f'{backup_path}: backup already exists; leaving it untouched.',
            file=sys.stdout)
    else:
        shutil.copy2(str(manifest_path), str(backup_path))
        print(f'Backed up original manifest to {backup_path}', file=sys.stdout)

    manifest_path.write_text(dump_manifest(manifest))

    for category, key in sorted(applied):
        print(
            f'Patched {key} in [{category}] -> {resolved[(category, key)]}',
            file=sys.stdout)


def _iter_dependency_tables(manifest):
    """Yield (category, table) for every dependency table in the manifest.

    Covers the top-level ``[dependencies]`` / ``[build-dependencies]`` /
    ``[dev-dependencies]`` tables and their ``[target.'...'.<category>]``
    counterparts.
    """
    for category in DEPENDENCY_CATEGORIES:
        table = manifest.get(category)
        if isinstance(table, dict):
            yield category, table
    for target in manifest.get('target', {}).values():
        if not isinstance(target, dict):
            continue
        for category in DEPENDENCY_CATEGORIES:
            table = target.get(category)
            if isinstance(table, dict):
                yield category, table


def _patch_dependency(table, key, path):
    """Redirect a single dependency entry to a local path, in place."""
    value = table[key]
    if isinstance(value, dict):
        preserved = {
            name: item
            for name, item in value.items()
            if name not in _SOURCE_KEYS}
        table[key] = {'path': path, **preserved}
    else:
        table[key] = {'path': path}


def _report_skipped(skipped):
    if not skipped:
        return
    for category, key in skipped:
        print(
            f'Skipped {key} in [{category}]: resolved locally but no matching '
            'entry was found in the parsed manifest.', file=sys.stderr)
    raise RuntimeError(
        'in-place patching resolved dependencies that were absent from the '
        'parsed manifest; the manifest was left unchanged')
