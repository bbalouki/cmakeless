"""Emitter coverage for the escape hatch and project-level optimize/lto.

The guard-text assertions lock the "an active preset wins" contract: the
default build type and LTO are emitted behind CMake if() guards that a preset's
cache variables switch off.
"""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import (
    ExecutableModel,
    LibraryKind,
    LibraryModel,
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
        "source_script": "build.py",
    }
    fields.update(overrides)
    return ProjectModel(**fields)  # type: ignore[arg-type]


def test_plain_project_emits_no_build_config() -> None:
    """A project that sets neither optimize nor lto emits no build config."""
    text = emit_cmakelists(make_model(), tool_version=FIXED_VERSION)
    assert "CMAKE_BUILD_TYPE" not in text
    assert "CMAKE_INTERPROCEDURAL_OPTIMIZATION" not in text


def test_optimize_emits_guarded_build_type() -> None:
    """optimize maps to a guarded CMAKE_BUILD_TYPE so a preset can override it."""
    text = emit_cmakelists(make_model(optimize="release"), tool_version=FIXED_VERSION)
    assert "if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)" in text
    assert 'set(CMAKE_BUILD_TYPE "Release" CACHE STRING' in text


def test_lto_emits_guarded_ipo() -> None:
    """lto maps to a guarded CMAKE_INTERPROCEDURAL_OPTIMIZATION default."""
    text = emit_cmakelists(make_model(lto=True), tool_version=FIXED_VERSION)
    assert "if(NOT DEFINED CMAKE_INTERPROCEDURAL_OPTIMIZATION)" in text
    assert "set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON)" in text


def test_target_raw_cmake_is_emitted_verbatim_and_fenced() -> None:
    """A target's raw_cmake snippets appear verbatim, after the link block."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine.cpp"),),
        raw_cmake=("set_target_properties(engine PROPERTIES UNITY_BUILD ON)",),
    )
    text = emit_cmakelists(make_model(libraries=(engine,)), tool_version=FIXED_VERSION)
    assert "# raw_cmake from build.py for target 'engine':" in text
    assert "set_target_properties(engine PROPERTIES UNITY_BUILD ON)" in text
    fence = text.index("# raw_cmake from build.py for target 'engine':")
    add_library = text.index("add_library(engine")
    assert fence > add_library


def test_raw_cmake_file_is_included_near_the_top() -> None:
    """A raw_cmake_file becomes a fenced include() before the targets."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    model = make_model(executables=(app,), raw_cmake_files=(Path("cmake/extra.cmake"),))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "# raw_cmake_file from build.py: cmake/extra.cmake" in text
    assert "include(${CMAKE_CURRENT_SOURCE_DIR}/cmake/extra.cmake)" in text
    assert text.index("cmake/extra.cmake") < text.index("add_executable(app")


def test_new_features_output_is_deterministic() -> None:
    """The escape hatch and build config emit byte-identically across runs."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine.cpp"),),
        raw_cmake=("set_target_properties(engine PROPERTIES UNITY_BUILD ON)",),
    )
    model = make_model(
        libraries=(engine,),
        optimize="release",
        lto=True,
        raw_cmake_files=(Path("cmake/extra.cmake"),),
    )
    assert emit_cmakelists(model, tool_version=FIXED_VERSION) == emit_cmakelists(
        model, tool_version=FIXED_VERSION
    )


def test_optimize_lto_golden_file() -> None:
    """Project-level optimize and lto render to the optimize_lto golden."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    model = make_model(name="opt_demo", executables=(app,), optimize="release", lto=True)
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text == (GOLDEN_DIR / "optimize_lto.cmake").read_text(encoding="utf-8")


def test_raw_cmake_golden_file() -> None:
    """Target raw_cmake and a raw_cmake_file render to the raw_cmake golden."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine.cpp"),),
        raw_cmake=(
            "set_target_properties(engine PROPERTIES UNITY_BUILD ON)",
            "target_precompile_headers(engine PRIVATE <vector>)",
        ),
    )
    model = make_model(
        name="raw_demo",
        libraries=(engine,),
        raw_cmake_files=(Path("cmake/extra.cmake"),),
    )
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text == (GOLDEN_DIR / "raw_cmake.cmake").read_text(encoding="utf-8")
