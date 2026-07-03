"""The Conan 2 adapter: manifest generation and the install step."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cmakeless.deps.conan import ConanAdapter
from cmakeless.deps.lockfile import LockData
from cmakeless.deps.provider import ResolutionContext
from cmakeless.errors import DependencyError, ToolchainError
from cmakeless.model.nodes import DependencyModel, ProjectModel


class FakeRun:
    """Records subprocess invocations and returns a scripted result."""

    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        """Script the result every recorded invocation returns."""
        self.returncode = returncode
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        """Record the command and return the scripted result."""
        self.commands.append(command)
        return subprocess.CompletedProcess(
            args=command, returncode=self.returncode, stdout="", stderr=self.stderr
        )


def make_model(*dependencies: DependencyModel) -> ProjectModel:
    """A frozen project around the given dependencies."""
    return ProjectModel(
        name="demo",
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/does/not/matter"),
        source_script="build.py",
        package_manager="conan",
        dependencies=dependencies,
    )


def patch_conan(monkeypatch: pytest.MonkeyPatch, *, present: bool = True) -> None:
    """Make conan discoverable (or not) on a fake PATH."""
    location = "/usr/bin/conan" if present else None
    monkeypatch.setattr("cmakeless.deps.conan.shutil.which", lambda _: location)


def test_manifest_lists_requires_and_generators() -> None:
    """Manifest lists requires and generators."""
    model = make_model(
        DependencyModel(name="googletest", version="1.14.0"),
        DependencyModel(name="fmt", version="10.2.1"),
    )
    files = ConanAdapter().manifest_files(model, LockData(packages={}))
    assert files[Path("conanfile.txt")] == (
        "[requires]\nfmt/10.2.1\ngtest/1.14.0\n\n[generators]\nCMakeDeps\nCMakeToolchain\n"
    )


def test_pre_configure_runs_conan_install(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Pre configure runs conan install."""
    patch_conan(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.deps.conan.subprocess.run", fake_run)
    ConanAdapter().pre_configure(root_dir=tmp_path, build_dir=tmp_path / "build")
    assert fake_run.commands[0] == [
        "/usr/bin/conan",
        "install",
        str(tmp_path),
        "--output-folder",
        str(tmp_path / "build"),
        "--build=missing",
        "-s",
        "build_type=Release",
    ]


def test_missing_conan_raises_toolchain_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing conan raises toolchain error."""
    patch_conan(monkeypatch, present=False)
    with pytest.raises(ToolchainError, match="pip install conan"):
        ConanAdapter().pre_configure(root_dir=tmp_path, build_dir=tmp_path / "build")


def test_install_failure_raises_dependency_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Install failure raises dependency error."""
    patch_conan(monkeypatch)
    fake_run = FakeRun(returncode=1, stderr="ERROR: package not found\n")
    monkeypatch.setattr("cmakeless.deps.conan.subprocess.run", fake_run)
    with pytest.raises(DependencyError) as excinfo:
        ConanAdapter().pre_configure(root_dir=tmp_path, build_dir=tmp_path / "build")
    message = str(excinfo.value)
    assert "exit code 1" in message
    assert "package not found" in message
    assert "rerun" in message


def test_toolchain_args_point_at_the_generated_toolchain(tmp_path: Path) -> None:
    """Toolchain args point at the generated toolchain."""
    build_dir = tmp_path / "build"
    arguments = ConanAdapter().toolchain_args(build_dir)
    assert arguments == (
        f"-DCMAKE_TOOLCHAIN_FILE={build_dir / 'conan_toolchain.cmake'}",
        "-DCMAKE_BUILD_TYPE=Release",
    )


def test_resolve_fills_metadata_only() -> None:
    """Resolve fills metadata only."""
    context = ResolutionContext(root_dir=Path(), lock=LockData(packages={}))
    completed = ConanAdapter().resolve(DependencyModel(name="fmt", version="10.2.1"), context)
    assert completed.cmake_name == "fmt"
    assert completed.link_targets == ("fmt::fmt",)
    assert completed.url is None
