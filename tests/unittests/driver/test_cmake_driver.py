"""Driver behavior with the subprocess boundary mocked (a true external)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cmakeless.driver.cmake_driver import CMakeDriver
from cmakeless.errors import CMakeError, ToolchainError


class FakeRun:
    """Records subprocess invocations and returns a scripted result."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        """Script the result every recorded invocation returns."""
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        """Record the command and return the scripted result."""
        self.commands.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


@pytest.fixture
def driver(tmp_path: Path) -> CMakeDriver:
    """A driver bound to a temporary source and build directory."""
    return CMakeDriver(source_dir=tmp_path, build_dir=tmp_path / "build")


def patch_tools(monkeypatch: pytest.MonkeyPatch, *, ninja: bool = True) -> None:
    """Make cmake (and optionally ninja) discoverable on a fake PATH."""
    tool_paths = {"cmake": "/usr/bin/cmake", "ninja": "/usr/bin/ninja" if ninja else None}
    monkeypatch.setattr(
        "cmakeless.driver.cmake_driver.shutil.which",
        lambda tool: tool_paths.get(tool),
    )


def test_configure_invokes_cmake_with_ninja(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Configure invokes cmake with ninja."""
    patch_tools(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver.configure()
    command = fake_run.commands[0]
    assert command[0] == "/usr/bin/cmake"
    assert command[1:5] == ["-S", str(tmp_path), "-B", str(tmp_path / "build")]
    assert command[5:] == ["-G", "Ninja"]


def test_configure_without_ninja_uses_default_generator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Configure without ninja uses default generator."""
    patch_tools(monkeypatch, ninja=False)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    # Generator auto-selection happens at construction, so build the driver
    # only after ninja has been made unavailable.
    driver = CMakeDriver(source_dir=tmp_path, build_dir=tmp_path / "build")
    driver.configure()
    assert "-G" not in fake_run.commands[0]


def test_build_invokes_cmake_build(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Build invokes cmake build."""
    patch_tools(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver.build()
    assert fake_run.commands[0][1:] == ["--build", str(tmp_path / "build")]


def test_missing_cmake_raises_toolchain_error(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing cmake raises toolchain error."""
    monkeypatch.setattr("cmakeless.driver.cmake_driver.shutil.which", lambda _: None)
    with pytest.raises(ToolchainError, match=r"cmake\.org"):
        driver.configure()


def test_failure_raises_structured_cmake_error(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Failure raises structured cmake error."""
    patch_tools(monkeypatch)
    fake_run = FakeRun(returncode=2, stderr="CMake Error: something broke\n")
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    with pytest.raises(CMakeError) as excinfo:
        driver.configure()
    error = excinfo.value
    assert error.exit_code == 2
    assert error.command[0] == "/usr/bin/cmake"
    assert error.log_path is not None
    assert error.log_path.is_file()
    assert "something broke" in error.log_path.read_text(encoding="utf-8")
    # The message must say what went wrong, where, and what to try next.
    message = str(error)
    assert "exit code 2" in message
    assert str(tmp_path) in message
    assert "rerun" in message
