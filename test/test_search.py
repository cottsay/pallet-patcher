# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from pathlib import Path
from unittest.mock import patch

from pallet_patcher.search import _get_available_crates
import pytest


@pytest.fixture
def mock_crates_dir(tmp_path):
    """
    Create a temporary directory structure mimicking a Rust workspace.

    Structure:
      /tmp_dir/
        ├── crate_a/Cargo.toml
        ├── crate_b_v1/Cargo.toml
        └── crate_b_v2/Cargo.toml
    """
    (tmp_path / 'crate_a').mkdir()
    (tmp_path / 'crate_a' / 'Cargo.toml').touch()

    (tmp_path / 'crate_b_v1').mkdir()
    (tmp_path / 'crate_b_v1' / 'Cargo.toml').touch()

    (tmp_path / 'crate_b_v2').mkdir()
    (tmp_path / 'crate_b_v2' / 'Cargo.toml').touch()

    return tmp_path


def test_get_available_crates_structure(mock_crates_dir):
    """Tests that the function correctly parses a directory of crates."""
    # We define what load_manifest should return based on the path it receives
    def manifest_side_effect(path):
        str_path = str(path)
        if 'crate_a' in str_path:
            return {'package': {'name': 'alpha-lib', 'version': '0.1.0'}}
        elif 'crate_b_v1' in str_path:
            return {'package': {'name': 'beta-lib', 'version': '1.0.0'}}
        elif 'crate_b_v2' in str_path:
            return {'package': {'name': 'beta-lib', 'version': '2.0.0'}}
        return {}

    # Patch 'load_manifest' in the scope where _get_available_crates is defined
    with patch('pallet_patcher.search.load_manifest',
               side_effect=manifest_side_effect):
        versions, metadata = _get_available_crates(mock_crates_dir)

        assert 'alpha-lib' in versions
        assert 'beta-lib' in versions

        assert versions['alpha-lib'] == {'0.1.0'}
        assert versions['beta-lib'] == {'1.0.0', '2.0.0'}

        key_alpha = 'alpha-lib+0.1.0'
        key_beta_1 = 'beta-lib+1.0.0'
        key_beta_2 = 'beta-lib+2.0.0'

        assert key_alpha in metadata
        assert key_beta_1 in metadata
        assert key_beta_2 in metadata

        # Check content (Path, Manifest)
        # Note: metadata values are (parent_path, manifest_dict)

        assert metadata[key_alpha][0].name == 'crate_a'
        assert metadata[key_alpha][1]['package']['name'] == 'alpha-lib'

        assert metadata[key_beta_1][0].name == 'crate_b_v1'
        assert metadata[key_beta_1][1]['package']['name'] == 'beta-lib'

        assert metadata[key_beta_2][0].name == 'crate_b_v2'
        assert metadata[key_beta_2][1]['package']['name'] == 'beta-lib'


def test_get_available_crates_empty(tmp_path):
    """Tests behavior when directory is empty or has no Cargo.toml files."""
    versions, metadata = _get_available_crates(tmp_path)
    assert not versions
    assert not metadata


def test_real_folder_integration():
    real_packages_path = Path(__file__).parent / 'packages' / 'upper_layer'

    if not real_packages_path.exists():
        pytest.skip('Skipping: "packages" directory not found locally.')

    versions, metadata = _get_available_crates(real_packages_path)

    assert 'pkg-d' in versions
    assert 'pkg-e' in versions

    assert versions['pkg-d'] == {'0.0.0'}
    assert versions['pkg-e'] == {'0.0.0'}

    key_d = 'pkg-d+0.0.0'
    key_e = 'pkg-e+0.0.0'

    assert key_d in metadata
    assert key_e in metadata

    assert metadata[key_d][0].name == 'pkg-d-0.0.0'
    assert metadata[key_d][1]['package']['name'] == 'pkg-d'

    assert metadata[key_e][0].name == 'pkg-e-0.0.0'
    assert metadata[key_e][1]['package']['name'] == 'pkg-e'
