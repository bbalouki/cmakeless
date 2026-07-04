# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The DependencyProvider Strategy interface every backend adapts to.

Each adapter in this package (find_package, FetchContent fallback, vcpkg,
Conan) presents one small, uniform surface, so target.depends("fmt/10.2.1")
never changes when the backend does.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cmakeless.deps.lockfile import LockData
from cmakeless.model.nodes import DependencyModel, ProjectModel


@dataclass(frozen=True, slots=True)
class ResolutionContext:
    """Everything an adapter may consult while resolving one dependency.

    Attributes:
        root_dir: The root project directory (where the lockfile lives).
        lock: The lockfile contents loaded before resolution started.
        force: True when the user asked to refresh pins (dependencies.lock()),
            so locked entries must be re-resolved instead of reused.
    """

    root_dir: Path
    lock: LockData
    force: bool = False


class DependencyProvider:
    """Strategy base: one backend for acquiring external packages.

    Subclasses override resolve(); the manifest, toolchain, and
    pre-configure hooks default to doing nothing because only the package
    manager backends need them.

    Attributes:
        name: The backend name recorded in the lockfile.
    """

    name = "abstract"

    def resolve(self, dependency: DependencyModel, context: ResolutionContext) -> DependencyModel:
        """Complete one dependency's metadata and pins for this backend.

        Args:
            dependency: The frozen dependency to complete.
            context: Lockfile contents and resolution flags.

        Returns:
            A completed copy of the dependency (dataclasses.replace).

        Raises:
            NotImplementedError: Always; subclasses must override.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement resolve()")

    def manifest_files(self, model: ProjectModel, lock: LockData) -> dict[Path, str]:
        """Generate this backend's manifest files, if it has any.

        Args:
            model: The resolved project model.
            lock: The lockfile contents written by resolution.

        Returns:
            File contents keyed by root-relative path; empty by default.
        """
        del model, lock
        return {}

    def toolchain_args(self, build_dir: Path, *, build_type: str) -> tuple[str, ...]:
        """Extra cmake configure arguments this backend needs, if any.

        Args:
            build_dir: The project's out-of-source build directory.
            build_type: The active CMake build type ("Debug", "Release",
                "RelWithDebInfo", or "MinSizeRel"), so a backend that installs
                configuration-specific artifacts (Conan) matches the build
                it is about to configure.

        Returns:
            Argument strings appended to the configure command; empty by
            default.
        """
        del build_dir, build_type
        return ()

    def pre_configure(self, *, root_dir: Path, build_dir: Path, build_type: str) -> None:
        """Run backend tooling that must happen before cmake configure.

        Args:
            root_dir: The project root (where manifests were written).
            build_dir: The project's out-of-source build directory.
            build_type: The active CMake build type; see toolchain_args().
        """
        del root_dir, build_dir, build_type

    def lock_baseline(self, context: ResolutionContext) -> str | None:
        """Report the vcpkg builtin-baseline to record in the lockfile.

        Args:
            context: Lockfile contents and resolution flags.

        Returns:
            A commit hash, or None for every backend except vcpkg.
        """
        del context
        return None


def collect_tree_dependencies(model: ProjectModel) -> list[DependencyModel]:
    """Gather the whole tree's dependencies, deduplicated and sorted.

    Validation guarantees one version per package name across the tree, so
    keeping the first occurrence of each name loses nothing.

    Args:
        model: The root project model.

    Returns:
        One dependency per package name, sorted by name.
    """
    by_name: dict[str, DependencyModel] = {}
    stack = [model]
    while stack:
        node = stack.pop()
        for dependency in node.dependencies:
            by_name.setdefault(dependency.name, dependency)
        stack.extend(subproject.project for subproject in node.subprojects)
    return [by_name[name] for name in sorted(by_name)]
