# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The Toolchain builder: wrapped files and generated descriptions."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project, Toolchain


@pytest.fixture
def project(project_dir: Path) -> Project:
    """A minimal buildable project."""
    built = Project("demo", cpp_std=20, root=project_dir)
    built.add_executable("demo", sources=["src/main.cpp"])
    return built


def test_from_file_wraps_an_existing_toolchain(project: Project) -> None:
    """From file wraps an existing toolchain."""
    toolchain_file = project.root / "cmake" / "rpi4.toolchain.cmake"
    toolchain_file.parent.mkdir()
    toolchain_file.write_text("set(CMAKE_SYSTEM_NAME Linux)\n", encoding="utf-8")
    project.add_toolchain(Toolchain.from_file("cmake/rpi4.toolchain.cmake"))
    model = project.freeze()
    (toolchain,) = model.toolchains
    assert toolchain.name == "rpi4.toolchain"
    assert toolchain.file == Path("cmake/rpi4.toolchain.cmake")


def test_missing_wrapped_file_is_rejected(project: Project) -> None:
    """Missing wrapped file is rejected."""
    project.add_toolchain(Toolchain.from_file("cmake/nope.cmake"))
    with pytest.raises(ConfigurationError, match="does not exist"):
        project.freeze()


def test_generated_toolchain_freezes_its_fields(project: Project) -> None:
    """Generated toolchain freezes its fields."""
    project.add_toolchain(
        Toolchain(
            "arm64-linux",
            compiler="aarch64-linux-gnu-g++",
            system_name="Linux",
            system_processor="aarch64",
        )
    )
    model = project.freeze()
    (toolchain,) = model.toolchains
    assert toolchain.file is None
    assert toolchain.compiler == "aarch64-linux-gnu-g++"
    assert toolchain.system_name == "Linux"


def test_generated_toolchain_needs_a_compiler(project: Project) -> None:
    """Generated toolchain needs a compiler."""
    project.add_toolchain(Toolchain("empty"))
    with pytest.raises(ConfigurationError, match="neither a file nor a compiler"):
        project.freeze()


def test_duplicate_toolchain_names_are_rejected(project: Project) -> None:
    """Duplicate toolchain names are rejected."""
    project.add_toolchain(Toolchain("cross", compiler="g++"))
    project.add_toolchain(Toolchain("cross", compiler="clang++"))
    with pytest.raises(ConfigurationError, match="Duplicate toolchain name"):
        project.freeze()
