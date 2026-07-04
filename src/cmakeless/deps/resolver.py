# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Resolution orchestration: one thread per dependency, one lockfile out.

Resolution sits between validate and emit in the pipeline. Workers only read
the frozen model and a lockfile snapshot; the lock write and the model
reassembly happen after the pool joins, single-threaded, so the resolver is
correct on GIL builds and fast on free-threaded ones. Results are keyed and
sorted by name, so thread completion order never leaks into the output.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from cmakeless.deps.conan import ConanAdapter
from cmakeless.deps.fetchcontent import AutoAdapter
from cmakeless.deps.find_package import FindPackageAdapter
from cmakeless.deps.lockfile import LockedPackage, read_lockfile, write_lockfile
from cmakeless.deps.provider import (
    DependencyProvider,
    ResolutionContext,
    collect_tree_dependencies,
)
from cmakeless.deps.vcpkg import VcpkgAdapter
from cmakeless.model.nodes import DependencyModel, ProjectModel, SubprojectModel


def provider_for(package_manager: str) -> DependencyProvider:
    """Select the dependency provider Strategy for a package manager name.

    Args:
        package_manager: A validated PACKAGE_MANAGERS member.

    Returns:
        The adapter implementing that backend.
    """
    adapter_by_name: dict[str, type[DependencyProvider]] = {
        "auto": AutoAdapter,
        "find_package": FindPackageAdapter,
        "vcpkg": VcpkgAdapter,
        "conan": ConanAdapter,
    }
    return adapter_by_name[package_manager]()


def resolve_dependencies(
    model: ProjectModel,
    *,
    lock_path: Path,
    force: bool = False,
    provider: DependencyProvider | None = None,
) -> ProjectModel:
    """Resolve every dependency in the tree and write the lockfile.

    Args:
        model: The validated root project model.
        lock_path: The lockfile location, usually <root>/cmakeless.lock.
        force: True to refresh pins instead of reusing locked entries.
        provider: A replacement provider, used by tests; None selects one
            from the model's package_manager.

    Returns:
        The model with every dependency completed; the same model when the
        tree has no dependencies (and then no lockfile is written).

    Raises:
        DependencyError: When any dependency cannot be resolved.
        ToolchainError: When the backend's tooling is missing.
    """
    dependencies = collect_tree_dependencies(model)
    if not dependencies:
        return model
    if provider is None:
        provider = provider_for(model.package_manager)
    context = ResolutionContext(
        root_dir=lock_path.parent, lock=read_lockfile(lock_path), force=force
    )
    resolved = _resolve_parallel(provider, dependencies, context)
    packages = {
        name: _locked_package(dependency, provider.name)
        for name, dependency in sorted(resolved.items())
    }
    write_lockfile(lock_path, packages, vcpkg_baseline=provider.lock_baseline(context))
    return _replace_dependencies(model, resolved)


def _resolve_parallel(
    provider: DependencyProvider,
    dependencies: list[DependencyModel],
    context: ResolutionContext,
) -> dict[str, DependencyModel]:
    """Resolve all dependencies concurrently, one thread each.

    Args:
        provider: The backend adapter to resolve with.
        dependencies: The deduplicated dependencies to resolve.
        context: Lockfile contents and resolution flags, shared read-only.

    Returns:
        Completed dependencies keyed by name.

    Raises:
        DependencyError: The first resolution failure, re-raised.
    """
    with ThreadPoolExecutor(max_workers=len(dependencies)) as pool:
        completed = pool.map(lambda dep: provider.resolve(dep, context), dependencies)
        return {dependency.name: dependency for dependency in completed}


def _locked_package(dependency: DependencyModel, backend: str) -> LockedPackage:
    """Turn one resolved dependency into its lockfile record.

    Args:
        dependency: The completed dependency.
        backend: The provider name that resolved it.

    Returns:
        The lockfile record.
    """
    assert dependency.cmake_name is not None, "resolution must fill cmake_name"
    return LockedPackage(
        name=dependency.name,
        version=dependency.version,
        backend=backend,
        cmake_name=dependency.cmake_name,
        targets=dependency.link_targets,
        url=dependency.url,
        sha256=dependency.sha256,
    )


def _replace_dependencies(
    model: ProjectModel, resolved: dict[str, DependencyModel]
) -> ProjectModel:
    """Rebuild the frozen tree with every dependency completed.

    Args:
        model: The project node to rebuild.
        resolved: Completed dependencies keyed by name.

    Returns:
        A copy of the node with its own and its subprojects' dependencies
        replaced.
    """
    return replace(
        model,
        dependencies=tuple(resolved[dependency.name] for dependency in model.dependencies),
        subprojects=tuple(
            SubprojectModel(
                directory=subproject.directory,
                project=_replace_dependencies(subproject.project, resolved),
            )
            for subproject in model.subprojects
        ),
    )
