"""Resolution orchestration: parallelism, determinism, and the lockfile."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

import pytest

from cmakeless.deps.conan import ConanAdapter
from cmakeless.deps.fetchcontent import AutoAdapter
from cmakeless.deps.find_package import FindPackageAdapter
from cmakeless.deps.lockfile import read_lockfile
from cmakeless.deps.provider import DependencyProvider, ResolutionContext
from cmakeless.deps.resolver import provider_for, resolve_dependencies
from cmakeless.deps.vcpkg import VcpkgAdapter
from cmakeless.errors import DependencyError
from cmakeless.model.nodes import DependencyModel, ProjectModel, SubprojectModel


class FakeProvider(DependencyProvider):
    """A provider that completes dependencies without any real backend."""

    name = "auto"

    def resolve(self, dependency: DependencyModel, context: ResolutionContext) -> DependencyModel:
        """Fill deterministic fake metadata and pins."""
        del context
        return replace(
            dependency,
            cmake_name=dependency.name,
            link_targets=(f"{dependency.name}::{dependency.name}",),
            url=f"https://example.com/{dependency.name}.tar.gz",
            sha256="ab" * 32,
        )


class BarrierProvider(FakeProvider):
    """A provider that only succeeds when resolutions overlap in time."""

    def __init__(self, expected: int) -> None:
        """Arm a barrier for the expected number of concurrent workers."""
        self._barrier = threading.Barrier(expected, timeout=10)

    def resolve(self, dependency: DependencyModel, context: ResolutionContext) -> DependencyModel:
        """Wait for every sibling resolution before completing."""
        self._barrier.wait()
        return super().resolve(dependency, context)


class FailingProvider(DependencyProvider):
    """A provider whose resolutions always fail."""

    name = "auto"

    def resolve(self, dependency: DependencyModel, context: ResolutionContext) -> DependencyModel:
        """Fail as a real backend would."""
        del context
        raise DependencyError(f"cannot resolve {dependency.name!r}")


def make_model(
    dependencies: tuple[DependencyModel, ...],
    subprojects: tuple[SubprojectModel, ...] = (),
) -> ProjectModel:
    """A frozen project around the given dependencies."""
    return ProjectModel(
        name="demo",
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/does/not/matter"),
        source_script="build.py",
        dependencies=dependencies,
        subprojects=subprojects,
    )


def test_provider_for_maps_every_package_manager() -> None:
    """Provider for maps every package manager."""
    assert isinstance(provider_for("auto"), AutoAdapter)
    assert isinstance(provider_for("find_package"), FindPackageAdapter)
    assert isinstance(provider_for("vcpkg"), VcpkgAdapter)
    assert isinstance(provider_for("conan"), ConanAdapter)


def test_dependency_free_tree_writes_no_lockfile(tmp_path: Path) -> None:
    """Dependency free tree writes no lockfile."""
    model = make_model(())
    lock_path = tmp_path / "cmakeless.lock"
    assert resolve_dependencies(model, lock_path=lock_path) is model
    assert not lock_path.exists()


def test_resolution_completes_the_model_and_writes_the_lock(tmp_path: Path) -> None:
    """Resolution completes the model and writes the lock."""
    model = make_model((DependencyModel(name="fmt", version="10.2.1"),))
    lock_path = tmp_path / "cmakeless.lock"
    resolved = resolve_dependencies(model, lock_path=lock_path, provider=FakeProvider())
    dependency = resolved.dependencies[0]
    assert dependency.url == "https://example.com/fmt.tar.gz"
    lock = read_lockfile(lock_path)
    assert lock.packages["fmt"].backend == "auto"
    assert lock.packages["fmt"].sha256 == "ab" * 32


def test_dependencies_resolve_in_parallel_threads(tmp_path: Path) -> None:
    """Dependencies resolve in parallel threads."""
    dependencies = (
        DependencyModel(name="fmt", version="10.2.1"),
        DependencyModel(name="spdlog", version="1.14.1"),
        DependencyModel(name="doctest", version="2.4.11"),
    )
    model = make_model(dependencies)
    # The barrier only opens when all three resolutions run concurrently;
    # sequential resolution would deadlock and trip the barrier timeout.
    resolved = resolve_dependencies(
        model,
        lock_path=tmp_path / "cmakeless.lock",
        provider=BarrierProvider(expected=len(dependencies)),
    )
    assert [dep.name for dep in resolved.dependencies] == ["fmt", "spdlog", "doctest"]


def test_lockfile_is_deterministic_regardless_of_declaration_order(tmp_path: Path) -> None:
    """Lockfile is deterministic regardless of declaration order."""
    forward = make_model(
        (
            DependencyModel(name="fmt", version="10.2.1"),
            DependencyModel(name="spdlog", version="1.14.1"),
        )
    )
    backward = make_model(tuple(reversed(forward.dependencies)))
    first = tmp_path / "first.lock"
    second = tmp_path / "second.lock"
    resolve_dependencies(forward, lock_path=first, provider=FakeProvider())
    resolve_dependencies(backward, lock_path=second, provider=FakeProvider())
    assert first.read_bytes() == second.read_bytes()


def test_subproject_dependencies_are_collected_and_replaced(tmp_path: Path) -> None:
    """Subproject dependencies are collected and replaced."""
    child = make_model((DependencyModel(name="fmt", version="10.2.1"),))
    parent = make_model(
        (),
        subprojects=(SubprojectModel(directory=Path("tools/child"), project=child),),
    )
    resolved = resolve_dependencies(
        parent, lock_path=tmp_path / "cmakeless.lock", provider=FakeProvider()
    )
    child_dependency = resolved.subprojects[0].project.dependencies[0]
    assert child_dependency.sha256 == "ab" * 32
    assert "fmt" in read_lockfile(tmp_path / "cmakeless.lock").packages


def test_resolution_failure_propagates(tmp_path: Path) -> None:
    """Resolution failure propagates."""
    model = make_model((DependencyModel(name="fmt", version="10.2.1"),))
    with pytest.raises(DependencyError, match="fmt"):
        resolve_dependencies(
            model, lock_path=tmp_path / "cmakeless.lock", provider=FailingProvider()
        )
