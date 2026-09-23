"""Emitter coverage for C++20 module interfaces: FILE_SET CXX_MODULES."""

from __future__ import annotations

from pathlib import Path

from cmakeless import CMAKE_MINIMUM_VERSION, CXX_MODULES_MINIMUM_VERSION
from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import ExecutableModel, LibraryKind, LibraryModel, ProjectModel

FIXED_VERSION = "1.2.3"
GOLDEN_DIR = Path(__file__).parent / "golden"


def make_model(**overrides: object) -> ProjectModel:
    """Build a frozen project with the given field overrides."""
    fields: dict[str, object] = {
        "name": "demo",
        "version": "1.0.0",
        "cpp_std": 23,
        "root_dir": Path("/does/not/matter"),
        "source_script": "cmakelessfile.py",
    }
    fields.update(overrides)
    return ProjectModel(**fields)  # type: ignore[arg-type]


def test_library_modules_are_public() -> None:
    """A library's module interfaces are PUBLIC, because consumers import them."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(),
        cxx_modules=(Path("src/geometry.cppm"),),
    )
    text = emit_cmakelists(make_model(libraries=(engine,)), tool_version=FIXED_VERSION)
    assert (
        "target_sources(engine PUBLIC\n    FILE_SET CXX_MODULES FILES\n        src/geometry.cppm\n)"
    ) in text


def test_executable_modules_are_private() -> None:
    """An executable's module interfaces are PRIVATE: nothing links against it."""
    app = ExecutableModel(
        name="app", sources=(Path("src/main.cpp"),), cxx_modules=(Path("src/app.cppm"),)
    )
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    expected = "target_sources(app PRIVATE\n    FILE_SET CXX_MODULES FILES\n        src/app.cppm\n)"
    assert expected in text


def test_modules_are_sorted_for_determinism() -> None:
    """Modules are sorted for determinism."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(),
        cxx_modules=(Path("src/z.cppm"), Path("src/a.cppm")),
    )
    text = emit_cmakelists(make_model(libraries=(engine,)), tool_version=FIXED_VERSION)
    assert text.index("src/a.cppm") < text.index("src/z.cppm")


def test_a_module_only_target_emits_no_empty_source_block() -> None:
    """A module only target emits no empty source block."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(),
        cxx_modules=(Path("src/geometry.cppm"),),
    )
    text = emit_cmakelists(make_model(libraries=(engine,)), tool_version=FIXED_VERSION)
    assert "target_sources(engine PRIVATE\n)" not in text


def test_modules_raise_the_cmake_floor() -> None:
    """Modules raise the cmake floor."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(),
        cxx_modules=(Path("src/geometry.cppm"),),
    )
    text = emit_cmakelists(make_model(libraries=(engine,)), tool_version=FIXED_VERSION)
    assert f"cmake_minimum_required(VERSION {CXX_MODULES_MINIMUM_VERSION})" in text


def test_a_project_without_modules_keeps_the_lower_floor() -> None:
    """A project without modules keeps the lower floor."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert f"cmake_minimum_required(VERSION {CMAKE_MINIMUM_VERSION})" in text
    assert "FILE_SET CXX_MODULES" not in text


def test_golden_cxx_modules() -> None:
    """Golden cxx modules."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine/util.cpp"),),
        cxx_modules=(Path("src/engine/geometry.cppm"), Path("src/engine/shapes.cppm")),
    )
    app = ExecutableModel(
        name="demo_app",
        sources=(Path("src/main.cpp"),),
        cxx_modules=(Path("src/app.cppm"),),
        links=(),
    )
    model = make_model(libraries=(engine,), executables=(app,), warnings="strict")
    golden = GOLDEN_DIR / "cxx_modules.cmake"
    assert emit_cmakelists(model, tool_version=FIXED_VERSION) == golden.read_text(encoding="utf-8")
