# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""CycloneDX and SPDX bill-of-materials generation from a resolved lockfile."""

from __future__ import annotations

from cmakeless.deps.lockfile import LockData, LockedPackage
from cmakeless.deps.sbom import generate_cyclonedx, generate_spdx

_FMT = LockedPackage(
    name="fmt",
    version="10.2.1",
    backend="auto",
    cmake_name="fmt",
    targets=("fmt::fmt",),
    url="https://github.com/fmtlib/fmt/archive/refs/tags/10.2.1.tar.gz",
    sha256="ab" * 32,
)
_GTEST = LockedPackage(
    name="googletest",
    version="1.14.0",
    backend="find_package",
    cmake_name="GTest",
    targets=("GTest::gtest",),
)


def test_cyclonedx_lists_every_package_sorted_by_name() -> None:
    """Cyclonedx lists every package sorted by name."""
    lock = LockData(packages={"fmt": _FMT, "googletest": _GTEST})
    document = generate_cyclonedx(
        lock,
        project_name="demo",
        project_version="1.0.0",
        serial_number="urn:uuid:fixed",
        timestamp="2026-01-01T00:00:00Z",
    )
    assert document["bomFormat"] == "CycloneDX"
    assert document["serialNumber"] == "urn:uuid:fixed"
    assert document["metadata"]["component"] == {
        "type": "application",
        "name": "demo",
        "version": "1.0.0",
    }
    names = [component["name"] for component in document["components"]]
    assert names == ["fmt", "googletest"]


def test_cyclonedx_component_gets_external_reference_only_when_fetched() -> None:
    """Cyclonedx component gets external reference only when fetched."""
    lock = LockData(packages={"fmt": _FMT, "googletest": _GTEST})
    document = generate_cyclonedx(lock, project_name="demo", project_version="1.0.0")
    by_name = {component["name"]: component for component in document["components"]}
    assert by_name["fmt"]["externalReferences"] == [{"type": "distribution", "url": _FMT.url}]
    assert "externalReferences" not in by_name["googletest"]


def test_spdx_document_shape() -> None:
    """Spdx document shape."""
    lock = LockData(packages={"fmt": _FMT})
    document = generate_spdx(
        lock,
        project_name="demo",
        project_version="1.0.0",
        document_namespace="https://example.invalid/demo",
        created="2026-01-01T00:00:00Z",
    )
    assert document["spdxVersion"] == "SPDX-2.3"
    assert document["documentNamespace"] == "https://example.invalid/demo"
    (package,) = document["packages"]
    assert package["name"] == "fmt"
    assert package["versionInfo"] == "10.2.1"
    assert package["downloadLocation"] == _FMT.url
    assert package["checksums"] == [{"algorithm": "SHA256", "checksumValue": _FMT.sha256}]


def test_spdx_package_without_url_is_noassertion() -> None:
    """Spdx package without url is noassertion."""
    lock = LockData(packages={"googletest": _GTEST})
    document = generate_spdx(lock, project_name="demo", project_version="1.0.0")
    (package,) = document["packages"]
    assert package["downloadLocation"] == "NOASSERTION"
    assert "checksums" not in package


def test_empty_lock_produces_empty_component_lists() -> None:
    """Empty lock produces empty component lists."""
    lock = LockData(packages={})
    cyclonedx = generate_cyclonedx(lock, project_name="demo", project_version="1.0.0")
    spdx = generate_spdx(lock, project_name="demo", project_version="1.0.0")
    assert cyclonedx["components"] == []
    assert spdx["packages"] == []
