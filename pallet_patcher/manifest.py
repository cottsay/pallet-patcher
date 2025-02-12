# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os.path

try:
    # Python 3.11+
    from tomllib import loads as toml_loads
except ImportError:
    try:
        from tomli import loads as toml_loads
    except ImportError:
        from toml import loads as toml_loads


def load_manifest(manifest_path):
    """
    Load data from a Cargo.toml file.

    :param manifest_path: Path to the Cargo.toml file on disk
    :type manifest_path: Path

    :returns: Manifest data
    :rtype: dict
    """
    with manifest_path.open('rb') as f:
        return toml_loads(f.read().decode())


def _extract_dependencies(manifest_section, package_name):
    plain_dependencies = {}
    for k, v in manifest_section.get('dependencies', {}).items():
        if k == package_name:
            continue
        plain_dependencies[k] = v

    build_dependencies = {}
    for k, v in manifest_section.get('build-dependencies', {}).items():
        if k == package_name:
            continue
        build_dependencies[k] = v

    dev_dependencies = {}
    for k, v in manifest_section.get('dev-dependencies', {}).items():
        if k == package_name:
            continue
        dev_dependencies[k] = v

    return plain_dependencies, build_dependencies, dev_dependencies


def _resolve_dependencies(dependencies, location):
    for specifications in dependencies.values():
        if not isinstance(specifications, dict):
            continue
        specifications_path = specifications.get('path')
        if specifications_path is None:
            continue
        if not specifications_path.startswith('file://'):
            specifications['path'] = os.path.normpath(
                str((location / specifications_path).absolute()))


def get_dependencies(manifest_data, location):
    """
    Get the dependencies from a Cargo.toml manifest.

    :param manifest_data: The deserialized data from the Cargo.toml
    :type manifest_data: dict
    :param location: The path to the directory where the Cargo.toml file
      resides on disk to resolve relative dependency paths from
    :type location: Path

    :returns: Tuple of dependencies: plain, build, dev
    :rtype: tuple
    """
    package_name = manifest_data.get('name')
    all_dependencies = _extract_dependencies(manifest_data, package_name)
    for category, spec in manifest_data.get('target', {}).items():
        dependencies = _extract_dependencies(spec, package_name)
        for existing, new in zip(all_dependencies, dependencies):
            existing.update(new)

    for dependencies in all_dependencies:
        _resolve_dependencies(dependencies, location)

    return all_dependencies
