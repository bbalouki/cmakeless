# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Emitter coverage for project.lint()/target.lint(): CXX_CLANG_TIDY and IWYU."""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import ExecutableModel, LibraryKind, LibraryModel, ProjectModel

FIXED_VERSION = "1.2.3"


def make_model(**overrides: object) -> ProjectModel:
    """Build a frozen project with the given field overrides."""
    fields: dict[str, object] = {
        "name": "demo",
        "version": "1.0.0",
        "cpp_std": 20,
        "root_dir": Path("/does/not/matter"),
        "source_script": "cmakelessfile.py",
    }
    fields.update(overrides)
    return ProjectModel(**fields)  # type: ignore[arg-type]


def test_no_lint_block_by_default() -> None:
    """No lint block by default."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert "CXX_CLANG_TIDY" not in text
    assert "CXX_INCLUDE_WHAT_YOU_USE" not in text


def test_project_wide_clang_tidy_applies_to_every_target() -> None:
    """Project wide clang tidy applies to every target."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    model = make_model(executables=(app,), lint_clang_tidy=("clang-tidy",))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert 'CXX_CLANG_TIDY "clang-tidy"' in text


def test_project_wide_iwyu_with_extra_arguments() -> None:
    """Project wide iwyu with extra arguments."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    model = make_model(
        executables=(app,), lint_iwyu=("include-what-you-use", "-Xiwyu", "--verbose=3")
    )
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert 'CXX_INCLUDE_WHAT_YOU_USE "include-what-you-use;-Xiwyu;--verbose=3"' in text


def test_target_override_wins_over_project_default() -> None:
    """Target override wins over project default."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),), clang_tidy=())
    model = make_model(executables=(app,), lint_clang_tidy=("clang-tidy",))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "CXX_CLANG_TIDY" not in text


def test_target_can_set_its_own_tool_regardless_of_project_default() -> None:
    """Target can set its own tool regardless of project default."""
    app = ExecutableModel(
        name="app", sources=(Path("src/main.cpp"),), clang_tidy=("clang-tidy", "-checks=-*")
    )
    model = make_model(executables=(app,))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert 'CXX_CLANG_TIDY "clang-tidy;-checks=-*"' in text


def test_header_only_library_never_gets_a_lint_block() -> None:
    """Header only library never gets a lint block."""
    lib = LibraryModel(
        name="hdr",
        kind=LibraryKind.HEADER_ONLY,
        sources=(),
        public_include_dirs=(Path("include"),),
    )
    model = make_model(libraries=(lib,), lint_clang_tidy=("clang-tidy",))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "CXX_CLANG_TIDY" not in text
