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
    # search_path = search_paths.pop(0)
    # print(search_paths)

    # Iterate over all the paths provided
    for search_path in search_paths:
        for manifest_path in search_path.glob('*/Cargo.toml'):
            # print("HERE")
            manifest = load_manifest(manifest_path)
            pkgname = manifest.get('package', {}).get('name')
            version = manifest.get('package', {}).get('version')

            versions[pkgname].add(version)

            # We are assuming here there won't be duplicated crates+version within the same search_path
            # Should we throw a warning?
            pkgs_metadata[f"{pkgname}+{version}"] = (manifest_path.parent, manifest)

            # Testing, erase this before merging
            # for pkgname, versions_pkg in versions.items():
            #     if(len(versions_pkg) >= 2):
            #         print(pkgname, versions_pkg)
            #         for version in versions_pkg:
            #             print(pkgs_metadata[f"{pkgname}+{version}"])
            # print(versions, pkgs_metadata)
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

        # Not sure if this still needed, since we specify a dependency that matches
        # the specifier set in the requirements
        # if name+"+"+version_spec in composition:
        #     reference = _get_reference(specifications)
        #     # No need to add this if the reference is not different from the one already added
        #     # This is a no-op now, but should we track here different versions?
        #     if reference is not None:
        #         composition[name][0].add(reference)
        #     continue

        # If we already parsed a version_spec, do not repeat that
        # TO-DO: this won't filter libc==0.2.62, libc==0.2.95, libc==0.2.50, etc
        # Not sure what we want to do in that scenario
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
            # Do nothing, let cargo handle this scenario
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
        plain_deps, build_deps, _ = get_dependencies(manifest, location)
        queue.extend(plain_deps.items())
        queue.extend(build_deps.items())

        composition[name+"+"+solved_version] = (reference, location, local_crate)

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
    for name, (reference, candidate, crate_local) in composition.items():
        # I'm not sure how this will work with user custom references here
        if not reference:
            reference = default_registry
        elif candidate.as_uri() == reference:
            # Cargo does not allow a patch to point to the same location as
            # the original dependency specification. If we encounter this,
            # just skip the reference entirely since it already points to
            # at least one of our candidates.
            continue

        # If the package is local, treat it as a patch
        # For patches we have to add:
        if crate_local:
            # Specifically use ~, which is valid in TOML but not in a
            # Cargo package name to reduce the likelihood of a collision
            section = f"patch.'{reference}'.'{name}~{1}'"
            arguments.add(f"--config={section}.package='{name}'")
            arguments.add(f"--config={section}.path='{candidate}'")
        else:
            pass

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
    for name, (reference, candidate, crate_local) in composition.items():
        if reference is None:
            reference = default_registry
        elif candidate.as_uri() == reference:
            # Cargo does not allow a patch to point to the same location as
            # the original dependency specification. If we encounter this,
            # just skip the reference entirely since it already points to
            # at least one of our candidates.
            continue

        # Specifically use ~, which is valid in TOML but not in a
        # Cargo package name to reduce the likelihood of a collision
        # sections.add('\n'.join((
        #     f"[patch.'{reference}'.'{name}~{1}']",
        #     f"package = '{name}'",
        #     f"path = '{candidate}'",
        # )))

        # If the package is local, treat it as a patch
        # For patches we have to add:
        if crate_local:
            # If the package is system level, treat it as immutable
            # Specifically use ~, which is valid in TOML but not in a
            # Cargo package name to reduce the likelihood of a collision
            sections.add('\n'.join((
                f"[patch.'{reference}'.'{name}~{1}']",
                f"package = '{name}'",
                f"path = '{candidate}'",
            )))
        else:
            # Otherwise, attempt to solve it with paths override
            pass

    return '\n\n'.join(sorted(sections))
