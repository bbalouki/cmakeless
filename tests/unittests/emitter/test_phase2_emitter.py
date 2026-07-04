# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Emitter coverage for dependency sections across every backend mode."""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import (
    DependencyModel,
    ExecutableModel,
    LinkModel,
    ProjectModel,
)

FIXED_VERSION = "1.2.3"
FAKE_SHA256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def make_model(
    *,
    package_manager: str = "auto",
    dependencies: tuple[DependencyModel, ...] = (),
    executables: tuple[ExecutableModel, ...] = (),
) -> ProjectModel:
    """Build a frozen project around the given dependencies."""
    return ProjectModel(
        name="demo",
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/does/not/matter"),
        source_script="cmakelessfile.py",
        package_manager=package_manager,
        dependencies=dependencies,
        executables=executables,
    )


def resolved_fmt() -> DependencyModel:
    """A fully resolved fmt dependency with a fake pin."""
    return DependencyModel(
        name="fmt",
        version="10.2.1",
        cmake_name="fmt",
        link_targets=("fmt::fmt",),
        url="https://github.com/fmtlib/fmt/archive/refs/tags/10.2.1.tar.gz",
        sha256=FAKE_SHA256,
    )


def resolved_boost() -> DependencyModel:
    """A resolved boost dependency with components (no fetch pin)."""
    return DependencyModel(
        name="boost",
        version="1.84.0",
        components=("beast", "asio"),
        cmake_name="Boost",
        link_targets=("Boost::beast", "Boost::asio"),
    )


def fmt_app() -> ExecutableModel:
    """An executable linking the fmt imported target."""
    return ExecutableModel(
        name="app",
        sources=(Path("src/main.cpp"),),
        links=(LinkModel(target="fmt::fmt", external=True),),
    )


def test_auto_mode_emits_the_fallback_block() -> None:
    """Auto mode emits the fallback block."""
    text = emit_cmakelists(make_model(dependencies=(resolved_fmt(),)), tool_version=FIXED_VERSION)
    assert "include(FetchContent)" in text
    assert "find_package(fmt 10.2.1 QUIET)" in text
    assert "if(NOT fmt_FOUND AND NOT TARGET fmt::fmt)" in text
    assert f"URL_HASH SHA256={FAKE_SHA256}" in text
    assert "FetchContent_MakeAvailable(fmt)" in text


def test_find_package_mode_requires_the_version() -> None:
    """Find package mode requires the version."""
    model = make_model(package_manager="find_package", dependencies=(resolved_fmt(),))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "find_package(fmt 10.2.1 REQUIRED)" in text
    assert "FetchContent" not in text


def test_vcpkg_mode_uses_config_packages() -> None:
    """Vcpkg mode uses config packages."""
    model = make_model(package_manager="vcpkg", dependencies=(resolved_fmt(),))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "find_package(fmt CONFIG REQUIRED)" in text
    assert "vcpkg.json" in text
    assert "FetchContent" not in text


def test_conan_mode_relies_on_cmakedeps() -> None:
    """Conan mode relies on cmakedeps."""
    model = make_model(package_manager="conan", dependencies=(resolved_fmt(),))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "find_package(fmt REQUIRED)" in text
    assert "conanfile.txt" in text


def test_components_are_sorted_into_the_find_package_call() -> None:
    """Components are sorted into the find package call."""
    model = make_model(package_manager="vcpkg", dependencies=(resolved_boost(),))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "find_package(Boost CONFIG REQUIRED COMPONENTS asio beast)" in text


def test_dependencies_are_sorted_by_name() -> None:
    """Dependencies are sorted by name."""
    model = make_model(package_manager="vcpkg", dependencies=(resolved_fmt(), resolved_boost()))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text.index("find_package(Boost") < text.index("find_package(fmt")


def test_no_dependencies_means_no_fetchcontent_include() -> None:
    """No dependencies means no fetchcontent include."""
    text = emit_cmakelists(make_model(), tool_version=FIXED_VERSION)
    assert "FetchContent" not in text


def test_golden_fallback_project() -> None:
    """Golden fallback project."""
    golden = Path(__file__).parent / "golden" / "dependencies_fallback.cmake"
    model = make_model(dependencies=(resolved_fmt(),), executables=(fmt_app(),))
    assert emit_cmakelists(model, tool_version=FIXED_VERSION) == golden.read_text(encoding="utf-8")


def test_golden_vcpkg_project() -> None:
    """Golden vcpkg project."""
    golden = Path(__file__).parent / "golden" / "dependencies_vcpkg.cmake"
    model = make_model(
        package_manager="vcpkg",
        dependencies=(resolved_fmt(), resolved_boost()),
        executables=(fmt_app(),),
    )
    assert emit_cmakelists(model, tool_version=FIXED_VERSION) == golden.read_text(encoding="utf-8")


def test_golden_conan_project() -> None:
    """Golden conan project."""
    golden = Path(__file__).parent / "golden" / "dependencies_conan.cmake"
    model = make_model(
        package_manager="conan",
        dependencies=(resolved_fmt(),),
        executables=(fmt_app(),),
    )
    assert emit_cmakelists(model, tool_version=FIXED_VERSION) == golden.read_text(encoding="utf-8")
