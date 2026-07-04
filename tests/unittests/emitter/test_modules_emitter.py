# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Emitter coverage for reflected includes: project.include()/include_module()."""

from __future__ import annotations

from pathlib import Path

from cmakeless._constants import CMAKELESS_SYSTEM_NAME_VAR, CMAKELESS_SYSTEM_PROCESSOR_VAR
from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import (
    ExecutableModel,
    ModuleCallModel,
    ModuleKind,
    ModuleModel,
    ProjectModel,
)

FIXED_VERSION = "1.2.3"
GOLDEN_DIR = Path(__file__).parent / "golden"


def make_model(**overrides: object) -> ProjectModel:
    """Build a frozen project with the given field overrides."""
    fields: dict[str, object] = {
        "name": "demo",
        "version": "1.0.0",
        "cpp_std": 17,
        "root_dir": Path("/does/not/matter"),
        "source_script": "cmakelessfile.py",
    }
    fields.update(overrides)
    return ProjectModel(**fields)  # type: ignore[arg-type]


def test_reflection_preamble_is_always_emitted() -> None:
    """The CMAKELESS_SYSTEM_NAME/PROCESSOR promotion is always emitted."""
    text = emit_cmakelists(make_model(), tool_version=FIXED_VERSION)
    assert f'set({CMAKELESS_SYSTEM_NAME_VAR} "${{CMAKE_SYSTEM_NAME}}" CACHE INTERNAL "")' in text
    assert (
        f'set({CMAKELESS_SYSTEM_PROCESSOR_VAR} "${{CMAKE_SYSTEM_PROCESSOR}}" CACHE INTERNAL "")'
        in text
    )


def test_file_include_is_anchored_to_the_source_dir() -> None:
    """A FILE include is emitted as include() anchored to the source dir."""
    module = ModuleModel(kind=ModuleKind.FILE, reference="cmake/helper.cmake")
    text = emit_cmakelists(make_model(modules=(module,)), tool_version=FIXED_VERSION)
    assert "include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/helper.cmake)" in text
    assert "# project.include() from cmakelessfile.py: cmake/helper.cmake" in text


def test_named_include_is_emitted_bare() -> None:
    """A NAMED include is emitted as a bare include(), no path prefix."""
    module = ModuleModel(kind=ModuleKind.NAMED, reference="CheckCXXCompilerFlag")
    text = emit_cmakelists(make_model(modules=(module,)), tool_version=FIXED_VERSION)
    assert "include(CheckCXXCompilerFlag)" in text
    assert "${CMAKE_CURRENT_SOURCE_DIR}/CheckCXXCompilerFlag" not in text
    assert "# project.include_module() from cmakelessfile.py: CheckCXXCompilerFlag" in text


def test_module_path_appends_to_cmake_module_path() -> None:
    """A NAMED include with module_path prepends a CMAKE_MODULE_PATH append."""
    module = ModuleModel(
        kind=ModuleKind.NAMED, reference="MyModule", module_path=Path("cmake/modules")
    )
    text = emit_cmakelists(make_model(modules=(module,)), tool_version=FIXED_VERSION)
    assert (
        'list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake/modules")\n'
        "include(MyModule)" in text
    )


def test_calls_are_emitted_after_the_include_in_declaration_order() -> None:
    """Calls are emitted after the include, in declaration order, never sorted."""
    module = ModuleModel(
        kind=ModuleKind.FILE,
        reference="cmake/helper.cmake",
        calls=(
            ModuleCallModel(function="zeta_fn", args=("a",)),
            ModuleCallModel(function="alpha_fn"),
        ),
    )
    text = emit_cmakelists(make_model(modules=(module,)), tool_version=FIXED_VERSION)
    include_index = text.index("include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/helper.cmake)")
    zeta_index = text.index("zeta_fn(a)")
    alpha_index = text.index("alpha_fn()")
    assert include_index < zeta_index < alpha_index


def test_module_sections_precede_dependencies_and_targets() -> None:
    """A reflected include is emitted before dependencies and targets use it."""
    module = ModuleModel(kind=ModuleKind.FILE, reference="cmake/helper.cmake")
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    text = emit_cmakelists(
        make_model(modules=(module,), executables=(app,)), tool_version=FIXED_VERSION
    )
    include_index = text.index("include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/helper.cmake)")
    target_index = text.index("add_executable(app)")
    assert include_index < target_index


def test_golden_cmake_interop_file() -> None:
    """Golden cmake interop file."""
    helper = ModuleModel(
        kind=ModuleKind.FILE,
        reference="cmake/print_summary.cmake",
        calls=(ModuleCallModel(function="print_summary", args=("hello",)),),
    )
    builtin = ModuleModel(kind=ModuleKind.NAMED, reference="CheckCXXCompilerFlag")
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    model = make_model(name="cmake_interop_demo", executables=(app,), modules=(helper, builtin))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text == (GOLDEN_DIR / "cmake_interop.cmake").read_text(encoding="utf-8")
