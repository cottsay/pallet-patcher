# Copyright 2025 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from packaging.version import Version
from packaging.specifiers import SpecifierSet


# I heavily relied on AI to help with this one.
# I added each case by iterating on the ones that throw me errors while
# debugging. We can add tests to make sure it handles most common Rust
# cases (or at least the ones used right now
def _parse_rust_specifier(spec_str: str) -> SpecifierSet:
    clean_spec = spec_str.strip()

    # 1. Handle "Explicit Equals" (=1.2.3 -> ==1.2.3)
    if clean_spec.startswith("=") and not clean_spec.startswith("=="):
        return SpecifierSet(f"=={clean_spec[1:]}")

    # 2. Handle Tilde (~1.2.3) - Minimal update
    if clean_spec.startswith("~"):
        version_part = clean_spec.lstrip("~")
        parts = version_part.split('.')
        try:
            if len(parts) >= 2:
                major, minor = int(parts[0]), int(parts[1])
                return SpecifierSet(f">={version_part},<{major}.{minor + 1}.0")
            elif len(parts) == 1:
                major = int(parts[0])
                return SpecifierSet(f">={version_part},<{major + 1}.0.0")
        except ValueError:
            pass

    # 3. Handle Caret (^1.2.3) - Maximal update (Compatible)
    # Rust: ^1.2.3 is the same as 1.2.3 (it's the default)
    # We strip the caret and let it fall through to the "Bare" logic below.
    if clean_spec.startswith("^"):
        clean_spec = clean_spec[1:]

    # 4. Handle "Bare" / Caret versions
    if clean_spec and clean_spec[0].isdigit():
        parts = clean_spec.split('.')
        try:
            major = int(parts[0])

            # Case A: Major > 0 (e.g. ^1.2.3) -> Lock Major
            if major > 0:
                return SpecifierSet(f">={clean_spec},<{major + 1}.0.0")

            # Case B: Major is 0
            if major == 0:
                # Case B.1: Single digit (^0) -> Allow 0.x.x
                if len(parts) == 1:
                    return SpecifierSet(f">={clean_spec},<1.0.0")

                minor = int(parts[1])

                # Case B.2: Major 0, Minor > 0 (e.g. ^0.2.3) -> Lock Minor
                if minor > 0:
                    return SpecifierSet(f">={clean_spec},<0.{minor + 1}.0")

                # Case B.3: Major 0, Minor 0 (e.g. ^0.0.3) -> Lock Patch
                # In Rust, 0.0.x changes are always breaking.
                elif minor == 0 and len(parts) > 2:
                    patch = int(parts[2])
                    return SpecifierSet(f">={clean_spec},<0.0.{patch + 1}")

                # Case B.4: ^0.0 (Implies 0.0.x)
                elif minor == 0:
                    return SpecifierSet(f">={clean_spec},<0.1.0")

        except ValueError:
            pass  # Fallback to standard handling if parsing fails

    # Fallback for standard Python specifiers (>=1.2, etc.)
    return SpecifierSet(clean_spec)


def solve_dependency(version_specifier, available_versions):
    """
    Find if one version available in our versions_dict matches the expected
    version_specifier provided.

    :param version_spec: Specifier for the version we want to match.
    :type version_spec: str

    :param available_versions: List of versions available.
    :type available_versions: str

    :returns: matched version string, or None if available ver don't match
    :rtype: dict
    """
    spec = _parse_rust_specifier(version_specifier)

    # We sort them first to prioritize higher versions for the packages
    sorted_versions = sorted(
        available_versions,
        key=lambda x: [int(part) for part in x.split('.')],
        reverse=True
    )

    # Iterate over the sorted list
    for version in sorted_versions:
        v = Version(version)
        # print(v, spec)
        if v in spec:
            return str(v)

    return None
