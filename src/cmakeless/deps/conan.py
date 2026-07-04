# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The Conan 2 adapter: conanfile.txt generation and toolchain wiring.

cmakeless writes a conanfile.txt next to the generated CMakeLists.txt, runs
'conan install' before the configure step, and points CMake at the toolchain
file Conan generates, so Conan's own tooling keeps working on the project.
"""

from __future__ import annotations

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
from cmakeless.errors import DependencyError, ToolchainError
from cmakeless.model.nodes import DependencyModel, ProjectModel

MANIFEST_NAME = "conanfile.txt"


class ConanAdapter(DependencyProvider):
    """Resolves dependencies through Conan 2 and its CMake integration."""

    name = "conan"

    def __init__(self) -> None:
        """Create the adapter; metadata comes from the shared registry."""
        self._find_package = FindPackageAdapter()

    def resolve(self, dependency: DependencyModel, context: ResolutionContext) -> DependencyModel:
        """Fill the find_package metadata; Conan needs no fetch pin.

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
        """Generate the conanfile.txt for the whole project tree.

        Args:
            model: The resolved project model.
            lock: The lockfile contents (unused; Conan pins via requires).

        Returns:
            The manifest text keyed by its root-relative path.
        """
        del lock
        requires = [_conan_reference(dep) for dep in collect_tree_dependencies(model)]
        lines = ["[requires]", *requires, "", "[generators]", "CMakeDeps", "CMakeToolchain", ""]
        return {Path(MANIFEST_NAME): "\n".join(lines)}

    def toolchain_args(self, build_dir: Path, *, build_type: str) -> tuple[str, ...]:
        """Point cmake at the toolchain file 'conan install' generated.

        Args:
            build_dir: The build directory the install step populated.
            build_type: The active CMake build type; must match the one
                passed to pre_configure() so Conan's installed dependency
                configuration (Debug/Release/...) agrees with CMake's.

        Returns:
            The toolchain-file and build-type arguments.
        """
        toolchain = build_dir / "conan_toolchain.cmake"
        return (f"-DCMAKE_TOOLCHAIN_FILE={toolchain}", f"-DCMAKE_BUILD_TYPE={build_type}")

    def pre_configure(self, *, root_dir: Path, build_dir: Path, build_type: str) -> None:
        """Run 'conan install' so the toolchain and config files exist.

        Args:
            root_dir: The project root containing conanfile.txt.
            build_dir: The build directory to install into.
            build_type: The active CMake build type, passed straight to
                Conan's own -s build_type= setting, so a Debug preset
                installs Debug dependencies instead of always Release.

        Raises:
            ToolchainError: When conan is not on PATH.
            DependencyError: When the install step fails.
        """
        command = [
            _conan_executable(),
            "install",
            str(root_dir),
            "--output-folder",
            str(build_dir),
            "--build=missing",
            "-s",
            f"build_type={build_type}",
        ]
        print(f"[cmakeless] Running conan: {subprocess.list2cmdline(command)}")
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            tail = (completed.stderr or completed.stdout or "").strip().splitlines()[-5:]
            raise DependencyError(
                f"'conan install' failed with exit code {completed.returncode} for "
                f"{root_dir}. Last output: {' | '.join(tail)}. Fix the Conan error, "
                f"or rerun the exact command by hand: "
                f"{subprocess.list2cmdline(command)}"
            )


def _conan_executable() -> str:
    """Locate the conan executable on PATH.

    Returns:
        The absolute path to conan.

    Raises:
        ToolchainError: When conan is not on PATH, with install guidance.
    """
    conan = shutil.which("conan")
    if conan is None:
        raise ToolchainError(
            'project.package_manager = "conan" needs Conan 2 on PATH, but it was '
            "not found. Install it with 'pip install conan' (or your package "
            "manager) and make sure 'conan --version' works in this shell."
        )
    return conan


def _conan_reference(dependency: DependencyModel) -> str:
    """Render one dependency as a Conan requires reference.

    Args:
        dependency: The dependency to render.

    Returns:
        The "name/version" reference, using the registry's Conan name.
    """
    entry = registry_entry(dependency.name)
    name = entry.conan_name if entry is not None and entry.conan_name else dependency.name
    return f"{name}/{dependency.version}"
