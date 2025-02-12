# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
import shutil
import subprocess

from pallet_patcher.command import load_and_compose
from pallet_patcher.search import compose
from pallet_patcher.search import get_cargo_arguments
from pallet_patcher.search import get_cargo_config
import pytest

_PACKAGES_PATH = Path(__file__).parent / 'packages'

_CARGO = shutil.which('cargo')


def test_dry():
    dependencies = [
        ('pkg-e', '*'),
    ]
    search_paths = (
        _PACKAGES_PATH / 'upper_layer',
        _PACKAGES_PATH / 'lower_layer',
    )

    composition = compose(dependencies, search_paths)
    assert len(composition) == 5, f'{composition}'

    arguments = get_cargo_arguments(composition)
    assert len(arguments) == 10, f'{arguments}'

    config = get_cargo_config(composition)
    assert config


@pytest.mark.skipif(not _CARGO, reason='The cargo executable is not available')
def test_cargo_arguments(tmpdir):
    layer_src = _PACKAGES_PATH / 'upper_layer'
    layer_dst = Path(tmpdir) / 'upper_layer'
    shutil.copytree(str(layer_src), layer_dst)

    search_paths = (
        layer_dst,
        _PACKAGES_PATH / 'lower_layer',
    )

    pkg_e = layer_dst / 'pkg-e-0.0.0'
    composition = load_and_compose(pkg_e / 'Cargo.toml', search_paths)
    arguments = get_cargo_arguments(composition)

    subprocess.run(
        [_CARGO, 'metadata', '--format-version=1', '--offline', *arguments],
        cwd=str(pkg_e),
        check=True)


@pytest.mark.skipif(not _CARGO, reason='The cargo executable is not available')
def test_cargo_config(tmpdir):
    layer_src = _PACKAGES_PATH / 'upper_layer'
    layer_dst = Path(tmpdir) / 'upper_layer'
    shutil.copytree(str(layer_src), layer_dst)

    search_paths = (
        layer_dst,
        _PACKAGES_PATH / 'lower_layer',
    )

    pkg_e = layer_dst / 'pkg-e-0.0.0'
    composition = load_and_compose(pkg_e / 'Cargo.toml', search_paths)
    config = get_cargo_config(composition)

    config_file = pkg_e / '.cargo' / 'config.toml'
    config_file.parent.mkdir()
    config_file.write_text(config)

    subprocess.run(
        [_CARGO, 'metadata', '--format-version=1', '--offline'],
        cwd=str(pkg_e),
        check=True)
