# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The Project builder freezes into a validated model."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Executable, Preset, Project
from cmakeless.api import _context


def test_add_executable_returns_builder(project_dir: Path) -> None:
    """Add executable returns builder."""
    project = Project("demo", root=project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    assert isinstance(app, Executable)
    assert app.name == "app"


def test_freeze_produces_model_with_tuples(project_dir: Path) -> None:
    """Freeze produces model with tuples."""
    project = Project("demo", version="2.1.0", cpp_std=23, root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    model = project.freeze()
    assert model.name == "demo"
    assert model.version == "2.1.0"
    assert model.cpp_std == 23
    assert model.root_dir == project_dir
    assert model.executables[0].sources == (Path("src/main.cpp"),)


def test_freeze_validates_missing_sources(project_dir: Path) -> None:
    """Freeze validates missing sources."""
    project = Project("demo", root=project_dir)
    project.add_executable("app", sources=["src/missing.cpp"])
    with pytest.raises(ConfigurationError, match=r"missing\.cpp"):
        project.freeze()


def test_freeze_validates_cpp_std(project_dir: Path) -> None:
    """Freeze validates cpp std."""
    project = Project("demo", cpp_std=42, root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    with pytest.raises(ConfigurationError, match="42"):
        project.freeze()


def test_add_sources_appends(project_dir: Path) -> None:
    """Add sources appends."""
    (project_dir / "src" / "extra.cpp").write_text("", encoding="utf-8")
    project = Project("demo", root=project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.add_sources("src/extra.cpp")
    model = project.freeze()
    assert Path("src/extra.cpp") in model.executables[0].sources


def test_root_defaults_to_calling_script_directory(project_dir: Path) -> None:
    """Root defaults to calling script directory.

    This test file is the "calling script", so the default root must be its
    directory, not the process working directory.
    """
    project = Project("demo")
    assert project.root == Path(__file__).resolve().parent


def test_generate_writes_cmakelists_without_cmake(project_dir: Path) -> None:
    """Generate writes cmakelists without cmake."""
    project = Project("demo", root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    written = project.generate()
    assert written == [project_dir / "CMakeLists.txt"]
    assert "add_executable(app)" in written[0].read_text(encoding="utf-8")


def test_optimize_and_lto_freeze_into_model(project_dir: Path) -> None:
    """Project optimize and lto attributes round-trip into the model."""
    project = Project("demo", root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    project.optimize = "release"
    project.lto = True
    model = project.freeze()
    assert model.optimize == "release"
    assert model.lto is True


def test_lint_freezes_the_project_wide_default(project_dir: Path) -> None:
    """project.lint() freezes into ProjectModel's project-wide default fields."""
    project = Project("demo", root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    project.lint(clang_tidy=True, iwyu=["include-what-you-use", "-Xiwyu"])
    model = project.freeze()
    assert model.lint_clang_tidy == ("clang-tidy",)
    assert model.lint_iwyu == ("include-what-you-use", "-Xiwyu")
    # Targets themselves stay unresolved (None): the emitter resolves
    # inheritance, mirroring how cpp_std overrides are resolved there too.
    assert model.executables[0].clang_tidy is None


def test_lint_off_by_default(project_dir: Path) -> None:
    """A project that never calls lint() has empty project-wide defaults."""
    project = Project("demo", root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    model = project.freeze()
    assert model.lint_clang_tidy == ()
    assert model.lint_iwyu == ()


def test_raw_cmake_file_freezes_into_model(project_dir: Path) -> None:
    """A raw_cmake_file lands in the model when the file exists."""
    (project_dir / "cmake").mkdir()
    (project_dir / "cmake" / "extra.cmake").write_text("# noop\n", encoding="utf-8")
    project = Project("demo", root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    project.raw_cmake_file("cmake/extra.cmake")
    model = project.freeze()
    assert model.raw_cmake_files == (Path("cmake/extra.cmake"),)


def test_missing_raw_cmake_file_fails_at_freeze(project_dir: Path) -> None:
    """A raw_cmake_file that does not exist fails at freeze, before CMake."""
    project = Project("demo", root=project_dir)
    project.add_executable("app", sources=["src/main.cpp"])
    project.raw_cmake_file("cmake/missing.cmake")
    with pytest.raises(ConfigurationError, match="does not exist"):
        project.freeze()


def test_target_raw_cmake_freezes_into_model(project_dir: Path) -> None:
    """A target's raw_cmake snippet round-trips into the target model."""
    project = Project("demo", root=project_dir)
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.raw_cmake("set_target_properties(app PROPERTIES ENABLE_EXPORTS ON)")
    model = project.freeze()
    assert model.executables[0].raw_cmake == (
        "set_target_properties(app PROPERTIES ENABLE_EXPORTS ON)",
    )


class _FakeConanRun:
    """Records subprocess invocations and reports success for every one."""

    def __init__(self) -> None:
        """Start with no recorded commands."""
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        """Record the command and report a successful exit."""
        self.commands.append(command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")


def test_conan_debug_preset_installs_debug_dependencies(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Debug preset makes the Conan adapter install Debug dependencies.

    Regression test for IMPROVEMENTS.md 2.2: the Conan adapter used to
    hard-code build_type=Release regardless of the active preset.
    """
    monkeypatch.setattr("cmakeless.deps.conan.shutil.which", lambda _: "/usr/bin/conan")
    fake_run = _FakeConanRun()
    monkeypatch.setattr("cmakeless.deps.conan.subprocess.run", fake_run)

    project = Project("demo", root=project_dir)
    project.package_manager = "conan"
    project.add_preset(Preset("debug", optimize="debug"))
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.depends("fmt/10.2.1")

    with _context.preset_override("debug"):
        project._prepare()

    (command,) = fake_run.commands
    assert "build_type=Debug" in command
