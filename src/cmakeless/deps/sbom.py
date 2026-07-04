# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Software bill of materials generation from cmakeless.lock.

cmakeless.lock already carries the project's complete, resolved dependency
inventory (name, version, and, for fetched packages, the source URL and
SHA256 pin); these functions turn that inventory into the two SBOM formats
tooling in regulated industries commonly requires, using nothing beyond the
standard library.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from cmakeless.deps.lockfile import LockData, LockedPackage

SBOM_FORMATS: frozenset[str] = frozenset({"cyclonedx", "spdx"})

_CYCLONEDX_SPEC_VERSION = "1.5"
_SPDX_VERSION = "SPDX-2.3"


def generate_cyclonedx(
    lock: LockData,
    *,
    project_name: str,
    project_version: str,
    serial_number: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Build a CycloneDX 1.5 bill of materials from a resolved lockfile.

    Args:
        lock: The project's resolved dependency inventory.
        project_name: The CMake project name, recorded as the root component.
        project_version: The project version string.
        serial_number: The document's URN, or None to mint a fresh one; only
            ever overridden by tests, for deterministic output.
        timestamp: The RFC 3339 generation timestamp, or None to use now();
            only ever overridden by tests.

    Returns:
        The document as a JSON-serializable mapping.
    """
    components = [
        _cyclonedx_component(package) for package in sorted(lock.packages.values(), key=_by_name)
    ]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": _CYCLONEDX_SPEC_VERSION,
        "serialNumber": serial_number if serial_number is not None else f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": timestamp if timestamp is not None else _now(),
            "component": {
                "type": "application",
                "name": project_name,
                "version": project_version,
            },
        },
        "components": components,
    }


def _cyclonedx_component(package: LockedPackage) -> dict[str, Any]:
    """Render one locked package as a CycloneDX component.

    Args:
        package: The LockedPackage to render.

    Returns:
        The component mapping.
    """
    component: dict[str, Any] = {
        "type": "library",
        "name": package.name,
        "version": package.version,
    }
    if package.url is not None:
        component["externalReferences"] = [{"type": "distribution", "url": package.url}]
    return component


def generate_spdx(
    lock: LockData,
    *,
    project_name: str,
    project_version: str,
    document_namespace: str | None = None,
    created: str | None = None,
) -> dict[str, Any]:
    """Build an SPDX 2.3 bill of materials from a resolved lockfile.

    Args:
        lock: The project's resolved dependency inventory.
        project_name: The CMake project name, recorded as the document name.
        project_version: The project version string, appended to the
            document name for readability.
        document_namespace: The document's unique namespace URI, or None to
            mint one from a fresh UUID; only ever overridden by tests.
        created: The RFC 3339 creation timestamp, or None to use now(); only
            ever overridden by tests.

    Returns:
        The document as a JSON-serializable mapping.
    """
    namespace = (
        document_namespace
        if document_namespace is not None
        else f"https://cmakeless.invalid/spdx/{project_name}-{uuid.uuid4()}"
    )
    packages = [_spdx_package(package) for package in sorted(lock.packages.values(), key=_by_name)]
    return {
        "spdxVersion": _SPDX_VERSION,
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{project_name}-{project_version}",
        "documentNamespace": namespace,
        "creationInfo": {
            "created": created if created is not None else _now(),
            "creators": ["Tool: cmakeless"],
        },
        "packages": packages,
    }


def _spdx_package(package: LockedPackage) -> dict[str, Any]:
    """Render one locked package as an SPDX package entry.

    Args:
        package: The LockedPackage to render.

    Returns:
        The package mapping.
    """
    entry: dict[str, Any] = {
        "SPDXID": f"SPDXRef-Package-{package.name}",
        "name": package.name,
        "versionInfo": package.version,
        "downloadLocation": package.url if package.url is not None else "NOASSERTION",
        "filesAnalyzed": False,
    }
    if package.sha256 is not None:
        entry["checksums"] = [{"algorithm": "SHA256", "checksumValue": package.sha256}]
    return entry


def _by_name(package: LockedPackage) -> str:
    """Sort key for a LockedPackage, by name.

    Args:
        package: The LockedPackage to key.

    Returns:
        The package name.
    """
    return package.name


def _now() -> str:
    """The current time as an RFC 3339 / ISO 8601 UTC timestamp.

    Returns:
        The timestamp, second precision, with a trailing "Z".
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
