# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os
from pathlib import Path

from pallet_patcher.manifest import get_dependencies
from pallet_patcher.manifest import load_manifest


def _get_reference(specification):
    if not isinstance(specification, dict):
        return None
    path = specification.get('path')
    if path is not None:
        return Path(path).as_uri()
    git = specification.get('git')
    if git is not None:
        return git
    return specification.get('registry')


def compose(dependencies, search_paths):
    """
    Compose a collection of crates which may satisfy given dependencies.

    :param dependencies: List of dependency tuples
      (import name, specifications)
    :type dependencies: tuple
    :param search_paths: List of local registry sources to search for packages
    :type search_paths: list

    :returns: Collection of packages which may satisfy the required
      dependencies.
    :rtype: dict
    """
    search_paths = list(search_paths)
    composition = {}
    candidates = {}

    queue = list(dependencies)
    while queue:
        name, specifications = queue.pop(0)
        if isinstance(specifications, dict):
            name = specifications.get('package', name)

        if name in composition:
            reference = _get_reference(specifications)
            composition[name][0].add(reference)
            continue

        candidate = candidates.get(name)
        while candidate is None and search_paths:
            search_path = search_paths.pop(0)
            layer = {}
            for manifest_path in search_path.glob('*/Cargo.toml'):
                manifest = load_manifest(manifest_path)
                pkgname = manifest.get('package', {}).get('name')
                if pkgname in candidates:
                    continue
                layer.setdefault(pkgname, []).append(
                    (manifest_path.parent, manifest))
            candidate = layer.get(name)
            candidates.update(layer)

        if candidate is None:
            continue

        reference = _get_reference(specifications)
        locations = set()
        for location, manifest in candidate:
            locations.add(location)
            plain_deps, build_deps, _ = get_dependencies(manifest, location)
            queue.extend(plain_deps.items())
            queue.extend(build_deps.items())

        composition[name] = ({reference}, locations)

    return composition


def get_cargo_arguments(composition, default_registry=None):
    """
    Get arguments to pass to 'cargo' which patch package references.

    :param composition: The curated package composition
    :type composition: dict
    :param default_registry: The default package registry if none was specified
    :type default_registry: str, optional

    :returns: List of command line arguments
    :rtype: list
    """
    if default_registry is None:
        default_registry = os.environ.get('CARGO_REGISTRY_DEFAULT')
        if not default_registry:
            default_registry = 'crates-io'
    arguments = set()
    for name, (references, candidates) in composition.items():
        for reference in references:
            if reference is None:
                reference = default_registry
            elif any(
                candidate.as_uri() == reference
                for candidate in candidates
            ):
                # Cargo does not allow a patch to point to the same location as
                # the original dependency specification. If we encounter this,
                # just skip the reference entirely since it already points to
                # at least one of our candidates.
                continue
            for idx, candidate in enumerate(candidates):
                # Specifically use ~, which is valid in TOML but not in a
                # Cargo package name to reduce the likelihood of a collision
                section = f"patch.'{reference}'.'{name}~{idx}'"
                arguments.add(f"--config={section}.package='{name}'")
                arguments.add(f"--config={section}.path='{candidate}'")
    return sorted(arguments)


def get_cargo_config(composition, default_registry=None):
    """
    Get Cargo configuration to patch package references.

    :param composition: The curated package composition
    :type composition: dict
    :param default_registry: The default package registry if none was specified
    :type default_registry: str, optional

    :returns: Raw TOML configuration
    :rtype: str
    """
    if default_registry is None:
        default_registry = os.environ.get('CARGO_REGISTRY_DEFAULT')
        if not default_registry:
            default_registry = 'crates-io'
    sections = set()
    for name, (references, candidates) in composition.items():
        for reference in references:
            if reference is None:
                reference = default_registry
            elif any(
                candidate.as_uri() == reference
                for candidate in candidates
            ):
                # Cargo does not allow a patch to point to the same location as
                # the original dependency specification. If we encounter this,
                # just skip the reference entirely since it already points to
                # at least one of our candidates.
                continue
            for idx, candidate in enumerate(candidates):
                # Specifically use ~, which is valid in TOML but not in a
                # Cargo package name to reduce the likelihood of a collision
                sections.add('\n'.join((
                    f"[patch.'{reference}'.'{name}~{idx}']",
                    f"package = '{name}'",
                    f"path = '{candidate}'",
                )))
    return '\n\n'.join(sorted(sections))
