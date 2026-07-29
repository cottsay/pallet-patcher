# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from argparse import ArgumentParser
from pathlib import Path

from pallet_patcher.manifest import get_dependencies
from pallet_patcher.manifest import load_manifest
from pallet_patcher.search import compose
from pallet_patcher.search import get_cargo_arguments
from pallet_patcher.search import get_cargo_config


def load_and_compose(manifest_path, search_paths):
    """
    Load a Cargo manifest and compose a package collection for building it.

    :param manifest_path: Path to the Cargo.toml file on disk
    :type manifest_path: Path
    :param search_paths: List of local registry sources to search for packages
    :type search_paths: list

    :returns: Collection of packages which may satisfy the requirements to
      build the package.
    :rtype: dict
    """
    manifest = load_manifest(manifest_path)
    location = manifest_path.parent.resolve()
    plain, build, dev = get_dependencies(manifest, location)
    dependencies = [*plain.items(), *build.items(), *dev.items()]

    return compose(dependencies, search_paths, seeds=[location])


def main(argv=None):
    """
    Command line interface for composing Cargo package collections.

    :param argv: Command line arguments to parse
    :type argv: dict, optional
    """
    parser = ArgumentParser()
    parser.add_argument('manifest_path', type=Path)
    parser.add_argument('search_path', type=Path, nargs='+')
    parser.add_argument(
        '--output-format', choices=('args', 'toml'), default='args')
    parser.add_argument(
        '--relative-paths', action='store_true',
        help='Generate relative paths from the working directory instead '
             'of absolute paths')
    args = parser.parse_args(argv)

    search_paths = [path.resolve() for path in args.search_path]
    composition = load_and_compose(args.manifest_path, search_paths)

    if args.output_format == 'toml':
        print(get_cargo_config(
            composition, relative_paths=args.relative_paths))
    else:
        for argument in get_cargo_arguments(
            composition,
            relative_paths=args.relative_paths,
        ):
            print(argument)
