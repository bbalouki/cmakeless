# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The vcpkg adapter: manifest generation and toolchain wiring.

cmakeless writes a vcpkg.json manifest next to the generated CMakeLists.txt
and points CMake at the vcpkg toolchain file, so vcpkg's own tooling keeps
working on the same project.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from cmakeless.deps.find_package import FindPackageAdapter
from cmakeless.deps.lockfile import LockData
from cmakeless.deps.provider import (
    DependencyProvider,
    ResolutionContext,
    collect_tree_dependencies,
)
from cmakeless.deps.registry import registry_entry
from cmakeless.errors import ToolchainError
from cmakeless.model.nodes import DependencyModel, ProjectModel

MANIFEST_NAME = "vcpkg.json"

# Environment variables that point at a vcpkg checkout, most specific first.
# VCPKG_INSTALLATION_ROOT is what GitHub-hosted runners set.
_ROOT_ENVIRONMENT_VARIABLES: tuple[str, ...] = ("VCPKG_ROOT", "VCPKG_INSTALLATION_ROOT")


class VcpkgAdapter(DependencyProvider):
    """Resolves dependencies through a vcpkg manifest and toolchain file."""

    name = "vcpkg"

    def __init__(self) -> None:
        """Create the adapter; metadata comes from the shared registry."""
        self._find_package = FindPackageAdapter()

    def resolve(self, dependency: DependencyModel, context: ResolutionContext) -> DependencyModel:
        """Fill the find_package metadata; vcpkg needs no fetch pin.

        Args:
            dependency: The frozen dependency to complete.
            context: Lockfile contents and resolution flags.

        Returns:
            The dependency with cmake_name and link_targets filled.

        Raises:
            DependencyError: For a package neither the registry nor the
                user's overrides describe.
        """
        return self._find_package.resolve(dependency, context)

    def manifest_files(self, model: ProjectModel, lock: LockData) -> dict[Path, str]:
        """Generate the vcpkg.json manifest for the whole project tree.

        Version constraints require a builtin-baseline; without one (no git
        history in the vcpkg checkout) the manifest lists plain port names
        and vcpkg resolves against its bundled versions.

        Args:
            model: The resolved project model.
            lock: The lockfile contents, carrying the recorded baseline.

        Returns:
            The manifest text keyed by its root-relative path.
        """
        dependencies = collect_tree_dependencies(model)
        baseline = lock.vcpkg_baseline
        manifest: dict[str, object] = {
            "name": _manifest_name(model.name),
            "version-string": model.version,
            "dependencies": [_manifest_dependency(dep, baseline) for dep in dependencies],
        }
        if baseline is not None:
            manifest["builtin-baseline"] = baseline
        text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        return {Path(MANIFEST_NAME): text}

    def toolchain_args(self, build_dir: Path, *, build_type: str) -> tuple[str, ...]:
        """Point cmake at the vcpkg toolchain file.

        Args:
            build_dir: The project's build directory (unused; vcpkg's
                toolchain lives in the vcpkg checkout).
            build_type: The active CMake build type (unused; the vcpkg
                toolchain file itself handles every configuration).

        Returns:
            The -DCMAKE_TOOLCHAIN_FILE argument.

        Raises:
            ToolchainError: When no vcpkg installation can be found.
        """
        del build_dir, build_type
        toolchain = vcpkg_root() / "scripts" / "buildsystems" / "vcpkg.cmake"
        return (f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",)

    def lock_baseline(self, context: ResolutionContext) -> str | None:
        """Determine the builtin-baseline commit to record in the lockfile.

        A missing vcpkg installation is tolerated here: generation must
        work on a machine without the tools, and toolchain_args() raises
        the helpful error when an actual build is attempted.

        Args:
            context: Lockfile contents and resolution flags.

        Returns:
            The already-locked baseline when not forcing a refresh,
            otherwise the HEAD commit of the vcpkg checkout; None when
            neither is available.
        """
        if not context.force and context.lock.vcpkg_baseline is not None:
            return context.lock.vcpkg_baseline
        try:
            root = vcpkg_root()
        except ToolchainError:
            return None
        return _checkout_head(root)


def vcpkg_root() -> Path:
    """Locate the vcpkg installation.

    Returns:
        The vcpkg checkout directory, from VCPKG_ROOT,
        VCPKG_INSTALLATION_ROOT, or the location of vcpkg on PATH.

    Raises:
        ToolchainError: When no installation can be found, with setup
            guidance.
    """
    for variable in _ROOT_ENVIRONMENT_VARIABLES:
        value = os.environ.get(variable)
        if value:
            return Path(value)
    executable = shutil.which("vcpkg")
    if executable is not None:
        return Path(executable).resolve().parent
    raise ToolchainError(
        'project.package_manager = "vcpkg" needs a vcpkg installation, but none '
        "was found. Install it (https://learn.microsoft.com/vcpkg) and set "
        "VCPKG_ROOT to the checkout directory, or put vcpkg on PATH."
    )


def _checkout_head(root: Path) -> str | None:
    """Read the HEAD commit of the vcpkg checkout, if it is a git clone.

    Args:
        root: The vcpkg checkout directory.

    Returns:
        The commit hash, or None when git or the history is unavailable.
    """
    git = shutil.which("git")
    if git is None:
        return None
    completed = subprocess.run(
        [git, "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _manifest_dependency(dependency: DependencyModel, baseline: str | None) -> object:
    """Render one dependency for the manifest's dependencies array.

    Args:
        dependency: The dependency to render.
        baseline: The builtin-baseline, or None when version constraints
            cannot be used.

    Returns:
        A port-name string, or an object with a version constraint when a
        baseline makes constraints valid.
    """
    entry = registry_entry(dependency.name)
    port = entry.vcpkg_name if entry is not None and entry.vcpkg_name else dependency.name
    if baseline is None:
        return port
    return {"name": port, "version>=": dependency.version}


def _manifest_name(project_name: str) -> str:
    """Derive a manifest name vcpkg accepts (lowercase, digits, hyphens).

    Args:
        project_name: The CMake project name.

    Returns:
        The sanitized manifest name.
    """
    lowered = project_name.lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in lowered).strip("-")
    return cleaned or "project"
