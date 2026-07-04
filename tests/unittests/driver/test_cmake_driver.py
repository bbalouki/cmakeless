# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Driver behavior with the subprocess boundary mocked (a true external)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cmakeless.driver.cmake_driver import CMakeDriver, resolve_tool
from cmakeless.driver.generators import select_generator
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


def patch_tools(
    monkeypatch: pytest.MonkeyPatch, *, ninja: bool = True, ccache: bool = False
) -> None:
    """Make the CMake suite (and optionally ninja/ccache) discoverable."""
    tool_paths = {
        "cmake": "/usr/bin/cmake",
        "ctest": "/usr/bin/ctest",
        "cpack": "/usr/bin/cpack",
        "ninja": "/usr/bin/ninja" if ninja else None,
        "ccache": "/usr/bin/ccache" if ccache else None,
    }
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
    assert command[5:] == ["-G", "Ninja", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]


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


def test_extra_configure_args_are_appended(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Extra configure args are appended."""
    patch_tools(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver = CMakeDriver(
        source_dir=tmp_path,
        build_dir=tmp_path / "build",
        extra_configure_args=("-DCMAKE_TOOLCHAIN_FILE=/vcpkg/scripts/buildsystems/vcpkg.cmake",),
    )
    driver.configure()
    assert "-DCMAKE_TOOLCHAIN_FILE=/vcpkg/scripts/buildsystems/vcpkg.cmake" in fake_run.commands[0]


def test_build_invokes_cmake_build(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Build invokes cmake build."""
    patch_tools(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver.build()
    assert fake_run.commands[0][1:] == ["--build", str(tmp_path / "build")]


def test_test_invokes_ctest_with_output_on_failure(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Test invokes ctest with output on failure."""
    patch_tools(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver.test()
    assert fake_run.commands[0] == [
        "/usr/bin/ctest",
        "--test-dir",
        str(tmp_path / "build"),
        "--output-on-failure",
    ]


def test_install_invokes_cmake_install(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Install invokes cmake install."""
    patch_tools(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver.install()
    assert fake_run.commands[0] == ["/usr/bin/cmake", "--install", str(tmp_path / "build")]


def test_package_invokes_cpack(driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch) -> None:
    """Package invokes cpack."""
    patch_tools(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver.package()
    assert fake_run.commands[0] == ["/usr/bin/cpack"]


def test_preset_replaces_explicit_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Preset replaces explicit directories."""
    patch_tools(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver = CMakeDriver(
        source_dir=tmp_path, build_dir=tmp_path / "build" / "debug", preset="debug"
    )
    driver.configure()
    command = fake_run.commands[0]
    assert command[1:3] == ["--preset", "debug"]
    assert "-S" not in command
    assert "-B" not in command


@pytest.mark.parametrize("generator_name", ["ninja", "ninja-multi", "make"])
def test_ccache_is_wired_as_launcher_for_makefile_and_ninja_families(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, generator_name: str
) -> None:
    """Ccache is wired as launcher for makefile and ninja families."""
    patch_tools(monkeypatch, ccache=True)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver = CMakeDriver(
        source_dir=tmp_path,
        build_dir=tmp_path / "build",
        generator=select_generator(generator_name),
    )
    driver.configure()
    assert "-DCMAKE_CXX_COMPILER_LAUNCHER=/usr/bin/ccache" in fake_run.commands[0]


@pytest.mark.parametrize("generator_name", ["vs", "xcode"])
def test_ccache_is_not_wired_for_vs_or_xcode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, generator_name: str
) -> None:
    """Ccache is not wired for vs or xcode."""
    patch_tools(monkeypatch, ccache=True)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver = CMakeDriver(
        source_dir=tmp_path,
        build_dir=tmp_path / "build",
        generator=select_generator(generator_name),
    )
    driver.configure()
    assert not any("COMPILER_LAUNCHER" in arg for arg in fake_run.commands[0])


def test_cache_opt_out_disables_the_launcher(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cache opt out disables the launcher."""
    patch_tools(monkeypatch, ccache=True)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    driver = CMakeDriver(source_dir=tmp_path, build_dir=tmp_path / "build", use_cache=False)
    driver.configure()
    assert not any("COMPILER_LAUNCHER" in arg for arg in fake_run.commands[0])


def test_compile_commands_are_copied_to_the_root(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Compile commands are copied to the root."""
    patch_tools(monkeypatch)
    fake_run = FakeRun()
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "compile_commands.json").write_text("[]", encoding="utf-8")
    driver.configure()
    assert (tmp_path / "compile_commands.json").read_text(encoding="utf-8") == "[]"


def test_configure_writes_the_file_api_query(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Configure writes the file api query."""
    patch_tools(monkeypatch)
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", FakeRun())
    driver.configure()
    query_dir = tmp_path / "build" / ".cmake" / "api" / "v1" / "query" / "client-cmakeless"
    assert (query_dir / "query.json").is_file()


def test_cmake_info_reads_from_the_driver_own_build_dir(
    driver: CMakeDriver, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cmake info reads from the driver's own build dir, mirroring targets_info()."""
    patch_tools(monkeypatch)
    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", FakeRun())
    driver.configure()
    reply_dir = tmp_path / "build" / ".cmake" / "api" / "v1" / "reply"
    reply_dir.mkdir(parents=True)
    index = {"cmake": {"generator": {"name": "Ninja", "multiConfig": False}}, "reply": {}}
    (reply_dir / "index-1.json").write_text(json.dumps(index), encoding="utf-8")
    assert driver.cmake_info().generator == "Ninja"


def test_resolve_tool_raises_toolchain_error_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve tool raises toolchain error when missing, usable outside a driver instance."""
    monkeypatch.setattr("cmakeless.driver.cmake_driver.shutil.which", lambda _: None)
    with pytest.raises(ToolchainError, match=r"cmake\.org"):
        resolve_tool("cmake")


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
