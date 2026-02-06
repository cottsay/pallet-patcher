# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from argparse import ArgumentParser
from pathlib import Path

from pallet_patcher.manifest import get_dependencies
from pallet_patcher.manifest import load_manifest
from pallet_patcher.search import compose
from pallet_patcher.search import get_cargo_arguments
from pallet_patcher.search import get_cargo_config


def load_and_compose(manifest_path, ws_search_paths, system_search_paths):
    """
    Load a Cargo manifest and compose a package collection for building it.

    :param manifest_path: Path to the Cargo.toml file on disk
    :type manifest_path: Path
    :param ws_search_paths: List of local registry sources to search for patcheable packages
    :type search_paths: list
    :param ws_search_paths: List of system registry sources to search for immutable packages
    :type search_paths: list

    :returns: Collection of packages which may satisfy the requirements to
      build the package.
    :rtype: dict
    """
    manifest = load_manifest(manifest_path)
    location = manifest_path.parent.resolve()
    plain, build, dev = get_dependencies(None, manifest, location)
    root_pkg = manifest.get('package').get('name')
    dependencies = [*plain.items(), *build.items(), *dev.items()]

    return compose(root_pkg, dependencies, ws_search_paths, system_search_paths)


def main(argv=None):
    """
    Command line interface for composing Cargo package collections.

    :param argv: Command line arguments to parse
    :type argv: dict, optional
    """
    parser = ArgumentParser()
    parser.add_argument('manifest_path', type=Path)
    parser.add_argument(
        'path_ws_deps',
        type=Path,
        nargs='*',
        default=[Path.cwd() / "deps"],
        help="List of paths to search for workspace crates. Defaults to ./deps/ if none provided."
    )
    parser.add_argument(
        'path_system_crates',
        type=Path,
        nargs='*',
        default=[Path("/usr/share/cargo/registry/")],
        help="List of paths to search for system crates. Defaults to '/usr/share/cargo/registry/' if none provided."
    )

    parser.add_argument(
        '--output-format', choices=('args', 'toml'), default='args')
    args = parser.parse_args(argv)

    workspace_search_paths = [path.resolve() for path in args.path_ws_deps]
    system_search_paths = [path.resolve() for path in args.path_system_crates]
    composition = load_and_compose(args.manifest_path, workspace_search_paths, system_search_paths)

    if args.output_format == 'toml':
        print(get_cargo_config(composition))
    else:
        for argument in get_cargo_arguments(composition):
            print(argument)
