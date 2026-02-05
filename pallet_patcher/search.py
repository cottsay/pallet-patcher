# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from collections import defaultdict
import os
from pathlib import Path

from pallet_patcher.manifest import get_dependencies
from pallet_patcher.manifest import load_manifest
from pallet_patcher.solver import solve_dependency


def _get_available_crates(search_path):
    """
    Create a list of crates available from a directory.

    :param search_path: Local registry source to search for packages
    :type search_path: Path

    :returns: Collection of pkgs available in a directory and their versions
    :rtype: dict

    :returns: Collection of the directory and metadata information for a
              specific pkgname+version
    :rtype: dict
    """
    versions = defaultdict(set)  # Skip duplicates in versions dict
    pkgs_metadata = {}

    # Iterate over all the paths provided
    for manifest_path in search_path.glob('*/Cargo.toml'):
        manifest = load_manifest(manifest_path)
        pkgname = manifest.get('package', {}).get('name')
        # TO-DO: In some cases, we want to crash if we can't find the package
        if not pkgname:
            continue
        version = manifest.get('package', {}).get('version') or '0.0.0'

        versions[pkgname].add(version)

        # We are assuming here there won't be duplicated crates+version within
        # the same search_path.
        pkgs_metadata[f'{pkgname}+{version}'] = (
            manifest_path.parent, manifest)

    return versions, pkgs_metadata


def _get_reference(specification):
    # Specification in the form of dict like "{'version': '2.6.1', 'default-features': False}"
    # Get cases where the dependency might be stated as a path or a custom registry
    if not isinstance(specification, dict):
        return None
    path = specification.get('path')
    if path is not None:
        return Path(path).as_uri()
    git = specification.get('git')
    if git is not None:
        return git
    return specification.get('registry')


# def compose(dependencies, search_paths): #uncomment this and search_paths.pop(0) to
def _get_available_crates(search_paths):
    """
    Create a list of crates available from a directory

    :param search_paths: List of local registry sources to search for packages
    :type search_paths: List[Path]

    :returns: Collection of packages available within a directory and their versions
    :rtype: dict

    :returns: Collection of the directory and metadata information for a
              specific pkgname+version
    :rtype: dict
    """
    versions = defaultdict(set) # Skip duplicates in versions dict
    pkgs_metadata = {}

    # Iterate over all the paths provided
    for search_path in search_paths:
        for manifest_path in search_path.glob('*/Cargo.toml'):
            manifest = load_manifest(manifest_path)
            pkgname = manifest.get('package', {}).get('name')
            version = manifest.get('package', {}).get('version')

            versions[pkgname].add(version)

            # We are assuming here there won't be duplicated crates+version within the same search_path
            # Should we throw a warning?
            pkgs_metadata[f"{pkgname}+{version}"] = (manifest_path.parent, manifest)

    return versions, pkgs_metadata


# Untested: what if we provide multiple crates_path for a single category?
# How do we prioritize between these?
def compose(dependencies, ws_crates_path, system_crates_path):
    """
    Compose a collection of crates which may satisfy given dependencies.

    :param dependencies: List of dependency tuples
      (import name, specifications)
    :type dependencies: tuple

    :param ws_crates_path: Directory where the crate dependencies local to our project are stored
    :type ws_crates_path: path

    :param system_crates_path: Directory where our platform saves IMMUTABLE crates
    :type system_crates_path: path

    :returns: Collection of packages which may satisfy the required
      dependencies.
    :rtype: dict
    """
    ws_crates, workspace_crates_metadata = _get_available_crates(ws_crates_path)
    platform_crates, platform_crates_metadata = _get_available_crates(system_crates_path)
    composition = {}
    solved_specifiers = {}

    queue = list(dependencies)
    while queue:

        name, specifications = queue.pop(0)
        if isinstance(specifications, dict):
            # This case covers packages like: rustc-std-workspace-core
            # where it's listed name differs from the installation name
            # print(name, specification)
            # core {'version': '1.0.0', 'optional': True, 'package': 'rustc-std-workspace-core'}
            name = specifications.get('package', name)
            version_spec = specifications.get('version', name)
        else:
            version_spec = specifications

        # If we already parsed a version_spec, do not repeat that
        # TO-DO: this won't filter libc==0.2.62, libc==0.2.95, libc==0.2.50, etc
        if name+str(version_spec) in solved_specifiers:
            continue

        candidate = None
        # Priority mechanism, attempt to get first a candidate that solves the expected dependency
        # specification from the local workspace. If not available, try to solve with machine
        # installed packages. Otherwise, just default to crates.io
        # TO-DO: if we do nothing about the latter ones, cargo will default to crates.io
        if ws_crates[name] and (solved_version := solve_dependency(version_spec, ws_crates[name])):
            candidate = workspace_crates_metadata[f"{name}+{solved_version}"]
            local_crate = True
        elif platform_crates[name] and (solved_version := solve_dependency(version_spec, platform_crates[name])):
            candidate = platform_crates_metadata[f"{name}+{solved_version}"]
            local_crate = False
        else:
            # Do nothing, cargo will handle this scenario
            pass

        # Do not search again for versions specifiers that we already looked up
        solved_specifiers[name+str(version_spec)] = True

        if candidate is None:
            # This would only be an actual error if the user set "use_internet = False"
            # Otherwise cargo should just pull from crates.io
            print(f"ERROR: {name} does not have any candidates available to meet requirements {specifications}")
            if not ws_crates[name] and not platform_crates[name]:
                print("Not any local packages available")
            elif not ws_crates[name]:
                print(f"Available system: {platform_crates[name]}")
            elif not platform_crates[name]:
                print(f"Available local: {ws_crates[name]}")
            else:
                print(f"Available local: {ws_crates[name]}", f"Available system: {platform_crates[name]}")
            continue

        reference = _get_reference(specifications)
        # Add the dependencies of the pkg to the list of packages that we need to find afterwards
        location, manifest = candidate
        plain_deps, build_deps, _ = get_dependencies(name, manifest, location)
        queue.extend(plain_deps.items())
        queue.extend(build_deps.items())

        # We also add the raw pkgname to the composition, because patches don't support
        # Adding pkgname+version as part of the patch name
        composition[name+"~"+solved_version] = (reference, location, local_crate, name)

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
    for versioned_name, (reference, candidate, crate_local, pkgname) in composition.items():
        # I'm not sure how this will work with user custom references here
        if not reference:
            reference = default_registry
        elif candidate.as_uri() == reference:
            # Cargo does not allow a patch to point to the same location as
            # the original dependency specification. If we encounter this,
            # just skip the reference entirely since it already points to
            # at least one of our candidates.
            continue

        section = f"patch.'{reference}'.'{versioned_name}'"
        arguments.add(f"--config={section}.package='{pkgname}'")
        arguments.add(f"--config={section}.path='{candidate}'")

        # I added the crate_local variable so we can treat
        # dependencies in the system folder differently than dependencies
        # in our local path. HOWEVER, it seems we can not treat those
        # differently, unless we modify the original Cargo.toml, specifying
        # That we get those from a different registry
        # if crate_local:
        #    pass
        # else:
        #     pass

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
    for versioned_name, (reference, candidate, crate_local, pkgname) in composition.items():
        if reference is None:
            reference = default_registry
        elif candidate.as_uri() == reference:
            # Cargo does not allow a patch to point to the same location as
            # the original dependency specification. If we encounter this,
            # just skip the reference entirely since it already points to
            # at least one of our candidates.
            continue

        sections.add('\n'.join((
            f"[patch.'{reference}'.'{versioned_name}']",
            f"package = '{pkgname}'",
            f"path = '{candidate}'",
        )))

    return '\n\n'.join(sorted(sections))
