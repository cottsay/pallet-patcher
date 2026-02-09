# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from packaging.specifiers import InvalidSpecifier
from pallet_patcher.solver import _parse_rust_specifier, solve_dependency
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
    spec_set = _parse_rust_specifier(r_input)

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
])
def test_standard_python_fallback(input_str, expected_str_repr):
    """Tests that std Python specifiers or other strings are passed through."""
    spec = _parse_rust_specifier(input_str)
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
        _parse_rust_specifier('invalid_string_with_char')


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


def test_solve_dependency_invalid_input_handling():
    """Test how the function handles non-integer version strings."""
    # NOTE: The provided function uses `int(part)` which will crash on "beta".
    # This test documents that behavior. If you want to support prereleases,
    # the sort key in the function needs to change.
    spec = '^1.0.0'
    available = ['1.0.0', '1.1.0-beta']

    with pytest.raises(ValueError) as excinfo:
        solve_dependency(spec, available)

    # Confirm it failed where we expected (in the sort lambda)
    assert 'invalid literal for int()' in str(excinfo.value)
