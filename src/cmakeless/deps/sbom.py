"""Software bill of materials generation from cmakeless.lock.

cmakeless.lock already carries the project's complete, resolved dependency
inventory (name, version, and, for fetched packages, the source URL and
SHA256 pin); these functions turn that inventory into the two SBOM formats
tooling in regulated industries commonly requires, using nothing beyond the
standard library. Output is reproducible: the same lockfile at the same
commit produces the same bytes, so a bill of materials diffs cleanly in
review and can be verified by rebuilding it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cmakeless.deps.lockfile import LockData, LockedPackage

SBOM_FORMATS: frozenset[str] = frozenset({"cyclonedx", "spdx"})

# The namespace document identifiers are derived from, so one lockfile always
# names its bill of materials the same way.
_SBOM_NAMESPACE = uuid.UUID("2b8f5c1e-3d4a-5f6b-8c9d-0e1f2a3b4c5d")

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
        serial_number: The document's URN, or None to derive one from the
            lockfile's content.
        timestamp: The RFC 3339 generation timestamp, or None to use now();
            callers pass reproducible_timestamp() for deterministic output.

    Returns:
        The document as a JSON-serializable mapping.
    """
    components = [
        _cyclonedx_component(package) for package in sorted(lock.packages.values(), key=_by_name)
    ]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": _CYCLONEDX_SPEC_VERSION,
        "serialNumber": (
            serial_number if serial_number is not None else f"urn:uuid:{_lock_uuid(lock)}"
        ),
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
            derive one from the lockfile's content.
        created: The RFC 3339 creation timestamp, or None to use now();
            callers pass reproducible_timestamp() for deterministic output.

    Returns:
        The document as a JSON-serializable mapping.
    """
    namespace = (
        document_namespace
        if document_namespace is not None
        else f"https://cmakeless.invalid/spdx/{project_name}-{_lock_uuid(lock)}"
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


def _lock_uuid(lock: LockData) -> uuid.UUID:
    """Derive a stable document identifier from the locked inventory.

    Args:
        lock: The project's resolved dependency inventory.

    Returns:
        A UUIDv5 that changes exactly when the inventory does.
    """
    inventory = [
        [package.name, package.version, package.url, package.sha256]
        for package in sorted(lock.packages.values(), key=_by_name)
    ]
    return uuid.uuid5(_SBOM_NAMESPACE, json.dumps(inventory))


def reproducible_timestamp(root_dir: Path) -> str:
    """Pick a generation time that is the same on every machine for one commit.

    Honors SOURCE_DATE_EPOCH (the reproducible-builds convention) first,
    then the commit time of the project's git HEAD; only outside version
    control does it fall back to the current time.

    Args:
        root_dir: The project root, used to ask git for the commit time.

    Returns:
        An RFC 3339 UTC timestamp with second precision.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH") or _git_commit_epoch(root_dir)
    if epoch is None or not epoch.isdigit():
        return _now()
    moment = datetime.fromtimestamp(int(epoch), UTC)
    return moment.isoformat().replace("+00:00", "Z")


def _git_commit_epoch(root_dir: Path) -> str | None:
    """Read the committer time of git HEAD, if the project is in a repository.

    Args:
        root_dir: The project root.

    Returns:
        The epoch seconds as a string, or None outside a repository.
    """
    git = shutil.which("git")
    if git is None:
        return None
    completed = subprocess.run(
        [git, "log", "-1", "--format=%ct"],
        capture_output=True,
        text=True,
        check=False,
        cwd=root_dir,
    )
    output = completed.stdout.strip()
    return output if completed.returncode == 0 and output else None
