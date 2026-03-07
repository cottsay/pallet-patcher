# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from packaging.specifiers import InvalidSpecifier
from pallet_patcher.solver import _parse_cargo_specifier, solve_dependency
import pytest


# Test code generated with LLM help
@pytest.mark.parametrize('r_input, expected_matches, expected_non_matches', [
    # 1. Explicit Equals (=)
    ('=1.2.3', ['1.2.3'], ['1.2.4', '1.2.2']),

    # 2. Tilde Requirements (~)
    # ~1.2.3 := >=1.2.3, <1.3.0
    ('~1.2.3', ['1.2.3', '1.2.9'], ['1.3.0', '1.1.0']),
    # ~1.2 := >=1.2, <1.3.0
    ('~1.2', ['1.2.0', '1.2.5'], ['1.3.0', '1.1.0']),
    # ~1 := >=1, <2.0.0
    ('~1', ['1.0.0', '1.5.0', '1.9.9'], ['2.0.0', '0.9.0']),

    # 3. Caret Requirements (^) - Major > 0
    # ^1.2.3 := >=1.2.3, <2.0.0
    ('^1.2.3', ['1.2.3', '1.9.9'], ['2.0.0', '1.2.2']),
    # Bare 1.2.3 (same as ^)
    ('1.2.3', ['1.2.3', '1.5.0', '1.9.9'], ['2.0.0', '1.2.2']),

    # 4. Caret Requirements (^) - Major == 0 (The tricky ones)

    # Case B.1: ^0 := >=0.0.0, <1.0.0
    ('^0', ['0.0.0', '0.1.0', '0.9.9'], ['1.0.0']),
    ('0', ['0.1.5'], ['1.0.0']),

    # Case B.2: ^0.2.3 (Minor > 0) := >=0.2.3, <0.3.0
    ('^0.2.3', ['0.2.3', '0.2.9'], ['0.3.0', '0.2.2']),
    ('0.2.3', ['0.2.3', '0.2.9'], ['0.3.0']),

    # Case B.3: ^0.0.3 (Minor == 0, Patch specified) := >=0.0.3, <0.0.4
    ('^0.0.3', ['0.0.3'], ['0.0.4', '0.0.2', '0.1.0']),
    ('0.0.3', ['0.0.3'], ['0.0.4']),

    # Case B.4: ^0.0 (Minor == 0, Patch missing) := >=0.0, <0.1.0
    ('^0.0', ['0.0.0', '0.0.5'], ['0.1.0']),
    ('0.0', ['0.0.1'], ['0.1.0']),
])
def test_rust_specifier_logic(r_input, expected_matches, expected_non_matches):
    """
    Tests that the converted Python SpecifierSet correctly matches.

    It should also exclude the versions dictated by Rust SemVer logic.
    """
    spec_set = _parse_cargo_specifier(r_input)

    for version in expected_matches:
        assert version in spec_set, \
            f"""Rust spec '{r_input}' should MATCH {version},
                but Python spec {spec_set} did not."""

    for version in expected_non_matches:
        assert version not in spec_set, \
            f"""Rust spec '{r_input}' should NOT match {version},
                but Python spec {spec_set} did."""


@pytest.mark.parametrize('input_str, expected_str_repr', [
    ('>=1.5', '>=1.5'),      # Passthrough standard python
    ('<2.0', '<2.0'),        # Passthrough standard python
    ('==1.2.3', '==1.2.3'),  # Passthrough explicit equality
    ('', ''),                # Empty string handling
    ('*', '>=0.0.0'),        # Expect finding any version = *
    ('<=0.61.*', '<0.62'),   # inequalities with patch wildcard
    ('<0.61.*', '<0.61'),    # inequalities with patch wildcard
    ('>=0.73.*', '>=0.73'),  # inequalities with patch wildcard
    ('>0.73.*', '>=0.74'),   # inequalities with patch wildcard
])
def test_standard_python_fallback(input_str, expected_str_repr):
    """Tests that std Python specifiers or other strings are passed through."""
    spec = _parse_cargo_specifier(input_str)
    # Note: SpecifierSet normalization might change string spacing,
    # but the logic checks if it parses without crashing.
    assert str(spec) == expected_str_repr or not input_str


def test_invalid_version_strings():
    """Ensure the function handles malformed strings gracefully."""
    # This falls through to "Bare" logic, fails try/except, hits fallback
    # SpecifierSet("invalid") is technically valid in packaging but matches
    # nothing or raises InvalidSpecifier depending on version.
    # Here we just want to ensure your code doesn't crash internally.
    # This acts as both the try/except and the assertion
    with pytest.raises((ValueError, InvalidSpecifier)):
        _parse_cargo_specifier('invalid_string_with_char')


@pytest.mark.parametrize('spec, available, expected', [
    # 1. Basic Caret Priority
    # ^1.2.0 allows >=1.2.0, <2.0.0.
    # It should pick 1.9.9 (highest), ignore 2.0.0 (high) and 1.1.0 (low).
    ('^1.2.0', ['1.1.0', '1.2.0', '1.2.5', '1.9.9', '2.0.0'], '1.9.9'),

    # 2. Basic Tilde Priority
    # ~1.2.0 allows >=1.2.0, <1.3.0.
    # Should pick 1.2.9, ignore 1.3.0.
    ('~1.2.0', ['1.2.0', '1.2.5', '1.2.9', '1.3.0', '1.4.0'], '1.2.9'),

    # 3. Rust '0.x.y' Semantics (Major 0 breaking changes)
    # ^0.2.0 allows >=0.2.0, <0.3.0.
    # Should ignore 0.3.0 even though it's higher.
    ('^0.2.0', ['0.1.9', '0.2.0', '0.2.5', '0.3.0'], '0.2.5'),

    # 4. Rust '0.0.x' Semantics (Patch 0 breaking changes)
    # ^0.0.3 allows >=0.0.3, <0.0.4.
    # Should strictly match 0.0.3.
    ('^0.0.3', ['0.0.2', '0.0.3', '0.0.4', '0.1.0'], '0.0.3'),

    # 5. Exact Match
    ('=1.5.0', ['1.4.0', '1.5.0', '1.6.0'], '1.5.0'),

    # 6. No Match Found
    # Range is >=1.0.0, <2.0.0. Only have 0.9 and 2.1.
    ('^1.0.0', ['0.9.0', '2.1.0', '3.0.0'], None),

    # 7. Empty List
    ('^1.0.0', [], None),

    # 8. Handling 'Bare' versions (Implies ^)
    ('1.2.0', ['1.2.0', '1.5.0', '2.0.0'], '1.5.0'),

    # 9. wildcards in patch versions
    ('>=1.34.*', ['1.33.3', '1.34.4', '1.34.0', '1.35.2'], '1.35.2'),
    ('>1.34.*', ['1.33.3', '1.34.4', '1.34.0', '1.35.2'], '1.35.2'),
    ('<=1.34.*', ['1.33.3', '1.34.4', '1.34.0', '1.35.2'], '1.34.4'),
    ('<1.34.*', ['1.33.3', '1.34.4', '1.34.0', '1.35.2'], '1.33.3'),
])
def test_solve_dependency_logic(spec, available, expected):
    """Verify that solver picks the highest ver that satisfies the spec."""
    result = solve_dependency(spec, available)
    assert result == expected, \
        f"""For spec '{spec}' and versions {available}, expected '{expected}'
          but got '{result}'"""


def test_solve_dependency_sorting_correctness():
    """
    Specifically tests that 1.10.0 is considered greater than 1.2.0.

    String sorting would say "1.2" > "1.10", but numeric sorting says 10 > 2.
    """
    spec = '^1.0.0'
    # If sorting was string-based, it might encounter 1.2.0 first (descending).
    # Correct numeric sort: 1.10.0 is highest.
    available = ['1.1.0', '1.2.0', '1.9.0', '1.10.0']

    result = solve_dependency(spec, available)
    assert result == '1.10.0'


def test_solve_dependency_prerelease_input_handling():
    """Test that pre-release version strings are handled by the sort key."""
    # packaging.version.Version handles pre-release tags like '-beta',
    # normalizing them (e.g. '1.1.0-beta' -> '1.1.0b0').
    spec = '^1.0.0'
    available = ['1.0.0', '1.1.0-beta']

    # Should not crash; Version-based sort key handles pre-release
    result = solve_dependency(spec, available)
    # '1.1.0-beta' normalizes to '1.1.0b0' which is <1.1.0,
    # so '1.0.0' is the highest non-pre-release match
    assert result is not None


@pytest.mark.parametrize('spec, available, expected', [
    # Build metadata should not crash sorting
    ('*', ['1.0.0+build42'], '1.0.0+build42'),

    # Multiple versions with build metadata sort correctly
    ('*', ['1.0.0+aaa', '2.0.0+bbb'], '2.0.0+bbb'),

    # Build metadata mixed with plain versions
    ('*', ['1.0.0', '1.5.0+meta', '2.0.0'], '2.0.0'),

    # Caret spec with build metadata
    ('^1.0.0',
        ['1.0.0+build1', '1.9.0+build2', '2.0.0+build3'],
        '1.9.0+build2'),

    # Exact match with build metadata
    ('=1.0.0', ['1.0.0+build42', '2.0.0'], '1.0.0+build42'),
])
def test_solve_dependency_build_metadata(spec, available, expected):
    """Regression: versions with + build metadata must not crash solver."""
    result = solve_dependency(spec, available)
    assert result == expected, \
        f"For spec '{spec}' and versions {available}, expected '{expected}'" \
        f" but got '{result}'"
