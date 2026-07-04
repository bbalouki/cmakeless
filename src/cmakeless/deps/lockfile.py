# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Reading and writing cmakeless.lock: deterministic resolution on disk.

The lockfile is plain JSON, byte-deterministic (sorted keys, two-space
indent, LF newlines), and meant to be committed: CI and teammates resolve
from it alone, with zero network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cmakeless.errors import DependencyError

LOCKFILE_NAME = "cmakeless.lock"
LOCK_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class LockedPackage:
    """One resolved package as recorded in the lockfile.

    Attributes:
        name: The package name from the depends() spec.
        version: The resolved version.
        backend: The provider that resolved it ("auto", "find_package",
            "vcpkg", or "conan").
        cmake_name: The name find_package() knows the package by.
        targets: The imported targets consumers link against.
        url: Source archive URL, or None when the backend does not fetch.
        sha256: Archive pin, or None when the backend does not fetch.
    """

    name: str
    version: str
    backend: str
    cmake_name: str
    targets: tuple[str, ...]
    url: str | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class LockData:
    """The whole lockfile, parsed.

    Attributes:
        packages: Locked packages keyed by package name.
        vcpkg_baseline: The vcpkg builtin-baseline commit recorded at
            resolution time, or None when vcpkg was not involved.
    """

    packages: dict[str, LockedPackage]
    vcpkg_baseline: str | None = None


def read_lockfile(path: Path) -> LockData:
    """Load a lockfile, tolerating its absence.

    Args:
        path: The lockfile location, usually <root>/cmakeless.lock.

    Returns:
        The parsed lock data; empty when the file does not exist.

    Raises:
        DependencyError: When the file exists but is not a lockfile this
            version understands.
    """
    if not path.is_file():
        return LockData(packages={})
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DependencyError(
            f"The lockfile {path} is not valid JSON ({error}). Delete it and rerun "
            f"to regenerate, or restore it from version control."
        ) from error
    if raw.get("schema") != LOCK_SCHEMA_VERSION:
        raise DependencyError(
            f"The lockfile {path} uses schema {raw.get('schema')!r}, but this "
            f"cmakeless understands schema {LOCK_SCHEMA_VERSION}. Upgrade cmakeless, "
            f"or delete the lockfile and rerun to regenerate it."
        )
    packages = {
        name: _locked_package(name, fields) for name, fields in raw.get("packages", {}).items()
    }
    return LockData(packages=packages, vcpkg_baseline=raw.get("vcpkg", {}).get("baseline"))


def write_lockfile(
    path: Path,
    packages: dict[str, LockedPackage],
    *,
    vcpkg_baseline: str | None = None,
) -> None:
    """Write the lockfile, byte-deterministically.

    Args:
        path: The lockfile location, usually <root>/cmakeless.lock.
        packages: Locked packages keyed by package name.
        vcpkg_baseline: The vcpkg builtin-baseline commit to record, if any.
    """
    document = {
        "schema": LOCK_SCHEMA_VERSION,
        "packages": {name: _package_fields(package) for name, package in packages.items()},
        "vcpkg": {"baseline": vcpkg_baseline},
    }
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def _locked_package(name: str, fields: dict[str, Any]) -> LockedPackage:
    """Build one LockedPackage from its parsed JSON fields.

    Args:
        name: The package name (the JSON key).
        fields: The package's JSON object.

    Returns:
        The parsed package record.
    """
    return LockedPackage(
        name=name,
        version=fields["version"],
        backend=fields["backend"],
        cmake_name=fields["cmake_name"],
        targets=tuple(fields["targets"]),
        url=fields.get("url"),
        sha256=fields.get("sha256"),
    )


def _package_fields(package: LockedPackage) -> dict[str, Any]:
    """Render one LockedPackage as its JSON object (name lives in the key).

    Args:
        package: The package record to render.

    Returns:
        The JSON-serializable field mapping.
    """
    return {
        "version": package.version,
        "backend": package.backend,
        "cmake_name": package.cmake_name,
        "targets": list(package.targets),
        "url": package.url,
        "sha256": package.sha256,
    }
