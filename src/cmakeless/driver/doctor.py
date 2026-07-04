# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Environment diagnostics: what 'cmakeless doctor' checks on a new machine.

Every probe here is read-only: no project, no cmakelessfile.py, and no
CMakeLists.txt is required, so this can run on a brand-new checkout before
anything else has been set up.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from cmakeless._constants import CMAKE_MINIMUM_VERSION
from cmakeless.driver.generators import select_generator

_NETWORK_PROBE_URL = "https://github.com"
_NETWORK_TIMEOUT_SECONDS = 3.0
_TOOL_TIMEOUT_SECONDS = 10.0

# Tools whose absence is informational, not fatal, and why each one matters.
_OPTIONAL_TOOLS: tuple[tuple[str, str], ...] = (
    ("ccache", "speeds up rebuilds"),
    ("sccache", "speeds up rebuilds"),
    ("vcpkg", 'only needed for project.package_manager = "vcpkg"'),
    ("conan", 'only needed for project.package_manager = "conan"'),
)

_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """One diagnostic result.

    Attributes:
        name: The tool or capability checked.
        ok: True when the check passed (for an optional tool, when it was
            found on PATH).
        required: True when a failing check should fail the whole verb's
            exit code.
        detail: A one-line human-readable result.
    """

    name: str
    ok: bool
    required: bool
    detail: str


def run_diagnostics() -> tuple[DoctorCheck, ...]:
    """Probe the current machine for everything a cmakeless build needs.

    Returns:
        One DoctorCheck per probe: cmake, the auto-selected generator, the
        optional compiler caches and package managers, and network access.
    """
    checks = [_check_cmake(), _check_generator()]
    checks.extend(_check_optional_tool(tool, note) for tool, note in _OPTIONAL_TOOLS)
    checks.append(_check_network())
    return tuple(checks)


def _check_cmake() -> DoctorCheck:
    """Check that cmake is on PATH and meets the minimum version.

    Returns:
        The DoctorCheck for cmake.
    """
    path = shutil.which("cmake")
    if path is None:
        return DoctorCheck(
            name="cmake",
            ok=False,
            required=True,
            detail="not found on PATH; install CMake from https://cmake.org/download/",
        )
    version = _tool_version(path)
    if version is None:
        return DoctorCheck(
            name="cmake",
            ok=False,
            required=True,
            detail=f"found at {path}, but --version output could not be parsed",
        )
    ok = _parse_version(version) >= _parse_version(CMAKE_MINIMUM_VERSION)
    detail = (
        f"{version} (>= {CMAKE_MINIMUM_VERSION} required)"
        if ok
        else f"{version} is older than the required {CMAKE_MINIMUM_VERSION}"
    )
    return DoctorCheck(name="cmake", ok=ok, required=True, detail=detail)


def _check_generator() -> DoctorCheck:
    """Check which CMake generator cmakeless would auto-select.

    Returns:
        The DoctorCheck for the generator (always ok: auto-selection with
        no explicit name never raises).
    """
    generator = select_generator(None)
    return DoctorCheck(name="generator", ok=True, required=True, detail=generator.name)


def _check_optional_tool(tool: str, note: str) -> DoctorCheck:
    """Check whether an optional tool is on PATH.

    Args:
        tool: The executable name to look for.
        note: Why the tool matters, shown when it is missing.

    Returns:
        The DoctorCheck for this tool; never required.
    """
    path = shutil.which(tool)
    if path is None:
        detail = f"not found on PATH ({note})"
        return DoctorCheck(name=tool, ok=False, required=False, detail=detail)
    return DoctorCheck(name=tool, ok=True, required=False, detail=f"found at {path}")


def _check_network() -> DoctorCheck:
    """Check whether a short-timeout HTTPS request succeeds.

    Returns:
        The DoctorCheck for network access; never required, since builds
        with a complete lockfile and vendored dependencies need none.
    """
    try:
        # nosec B310 - _NETWORK_PROBE_URL is a fixed https:// constant, never
        # user input, so the scheme is already known-safe here.
        with urllib.request.urlopen(  # nosec B310
            _NETWORK_PROBE_URL, timeout=_NETWORK_TIMEOUT_SECONDS
        ):
            pass
    except (urllib.error.URLError, OSError) as error:
        detail = f"could not reach {_NETWORK_PROBE_URL} ({error})"
        return DoctorCheck(name="network", ok=False, required=False, detail=detail)
    detail = f"reached {_NETWORK_PROBE_URL}"
    return DoctorCheck(name="network", ok=True, required=False, detail=detail)


def _tool_version(path: str) -> str | None:
    """Run '<path> --version' and extract a dotted version number.

    Args:
        path: The executable's absolute path.

    Returns:
        The first "X.Y.Z"-shaped token found in the output, or None.
    """
    completed = subprocess.run(
        [path, "--version"],
        capture_output=True,
        text=True,
        timeout=_TOOL_TIMEOUT_SECONDS,
        check=False,
    )
    match = _VERSION_PATTERN.search(completed.stdout or completed.stderr or "")
    return match.group(0) if match else None


def _parse_version(text: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable tuple.

    Args:
        text: A "X.Y.Z"-shaped version string.

    Returns:
        The version as an (X, Y, Z) integer tuple.
    """
    return tuple(int(part) for part in text.split("."))
