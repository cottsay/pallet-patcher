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


# The dependency categories, in the order returned by ``get_dependencies``.
DEPENDENCY_CATEGORIES = (
    'dependencies',
    'build-dependencies',
    'dev-dependencies',
)


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


def dump_manifest(manifest_data):
    """
    Serialize manifest data back to TOML text.

    The writer is imported lazily because there is no TOML serializer in the
    standard library, so only workflows which actually rewrite a manifest
    (e.g. the in-place output) require one to be installed.

    :param manifest_data: The manifest data to serialize
    :type manifest_data: dict

    :returns: The TOML representation of the manifest data
    :rtype: str
    """
    try:
        from tomli_w import dumps as toml_dumps
    except ImportError:
        try:
            from toml import dumps as toml_dumps
        except ImportError:
            raise ImportError(
                'writing a manifest requires the "tomli-w" (Python 3.7+) or '
                '"toml" package to be installed')
    return toml_dumps(manifest_data)


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
