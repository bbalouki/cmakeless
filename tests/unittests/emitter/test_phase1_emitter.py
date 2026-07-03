"""Emitter coverage for libraries, settings, links, and subproject trees."""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists, emit_tree
from cmakeless.model.nodes import (
    CompileOptionsModel,
    DefineModel,
    ExecutableModel,
    LibraryKind,
    LibraryModel,
    LinkModel,
    ProjectModel,
    SubprojectModel,
)

FIXED_VERSION = "1.2.3"


def make_model(
    *,
    warnings: str = "default",
    executables: tuple[ExecutableModel, ...] = (),
    libraries: tuple[LibraryModel, ...] = (),
    subprojects: tuple[SubprojectModel, ...] = (),
) -> ProjectModel:
    """Build a frozen project around the given targets and subprojects."""
    return ProjectModel(
        name="demo",
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/does/not/matter"),
        source_script="cmakelessfile.py",
        warnings=warnings,
        executables=executables,
        libraries=libraries,
        subprojects=subprojects,
    )


def test_static_library_emission() -> None:
    """Static library emission."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine.cpp"),),
        public_include_dirs=(Path("include"),),
    )
    text = emit_cmakelists(make_model(libraries=(engine,)), tool_version=FIXED_VERSION)
    assert "add_library(engine STATIC)" in text
    assert (
        "target_include_directories(engine PUBLIC\n"
        "    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>\n"
        ")"
    ) in text
    assert "target_compile_features(engine PUBLIC cxx_std_20)" in text
    assert "POSITION_INDEPENDENT_CODE ON" in text
    assert "GenerateExportHeader" not in text


def test_shared_library_gets_export_header() -> None:
    """Shared library gets export header."""
    plugin = LibraryModel(name="plugin", kind=LibraryKind.SHARED, sources=(Path("src/plugin.cpp"),))
    text = emit_cmakelists(make_model(libraries=(plugin,)), tool_version=FIXED_VERSION)
    assert "include(GenerateExportHeader)" in text
    assert "add_library(plugin SHARED)" in text
    assert "generate_export_header(plugin)" in text
    assert "$<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}>" in text


def test_header_only_library_is_interface() -> None:
    """Header only library is interface."""
    headers = LibraryModel(
        name="headers",
        kind=LibraryKind.HEADER_ONLY,
        sources=(),
        public_include_dirs=(Path("include"),),
    )
    text = emit_cmakelists(make_model(libraries=(headers,)), tool_version=FIXED_VERSION)
    assert "add_library(headers INTERFACE)" in text
    assert "target_include_directories(headers INTERFACE" in text
    assert "target_compile_features(headers INTERFACE cxx_std_20)" in text
    assert "target_sources(headers" not in text
    assert "POSITION_INDEPENDENT_CODE" not in text


def test_links_use_visibility_keywords() -> None:
    """Links use visibility keywords."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine.cpp"),),
        links=(LinkModel(target="math", public=True), LinkModel(target="zlib", public=False)),
    )
    text = emit_cmakelists(make_model(libraries=(engine,)), tool_version=FIXED_VERSION)
    assert ("target_link_libraries(engine\n    PUBLIC math\n    PRIVATE zlib\n)") in text


def test_strict_warnings_are_translated_per_compiler() -> None:
    """Strict warnings are translated per compiler."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    text = emit_cmakelists(
        make_model(warnings="strict", executables=(app,)), tool_version=FIXED_VERSION
    )
    assert "$<$<CXX_COMPILER_ID:MSVC>:/W4;/permissive->" in text
    assert (
        "$<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall;-Wextra;-Wconversion;-Wsign-conversion;-pedantic>"
    ) in text


def test_default_warnings_emit_nothing() -> None:
    """Default warnings emit nothing."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert "target_compile_options" not in text


def test_defines_and_guarded_options() -> None:
    """Defines and guarded options."""
    app = ExecutableModel(
        name="app",
        sources=(Path("src/main.cpp"),),
        defines=(DefineModel("USE_AUDIO"), DefineModel("GAME_MAX_PLAYERS", "8")),
        compile_options=(
            CompileOptionsModel(flags=("-march=native",), compilers=("gnu", "clang")),
            CompileOptionsModel(flags=("-fno-exceptions",)),
        ),
    )
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert (
        "target_compile_definitions(app PRIVATE\n    GAME_MAX_PLAYERS=8\n    USE_AUDIO\n)"
    ) in text
    assert "$<$<CXX_COMPILER_ID:GNU,Clang>:-march=native>" in text
    assert "    -fno-exceptions" in text


def test_tree_emission_paths() -> None:
    """Tree emission paths."""
    child = make_model(executables=(ExecutableModel(name="tool", sources=(Path("main.cpp"),)),))
    parent = make_model(
        executables=(ExecutableModel(name="app", sources=(Path("src/main.cpp"),)),),
        subprojects=(SubprojectModel(directory=Path("tools/stamp"), project=child),),
    )
    files = emit_tree(parent, tool_version=FIXED_VERSION)
    assert list(files) == [Path("CMakeLists.txt"), Path("tools/stamp/CMakeLists.txt")]
    assert "add_subdirectory(tools/stamp)" in files[Path("CMakeLists.txt")]


def test_golden_single_project() -> None:
    """Golden single project."""
    golden = Path(__file__).parent / "golden" / "kitchen_sink.cmake"
    model = kitchen_sink_model()
    assert emit_cmakelists(model, tool_version=FIXED_VERSION) == golden.read_text(encoding="utf-8")


def test_golden_subproject_tree() -> None:
    """Golden subproject tree."""
    golden_dir = Path(__file__).parent / "golden"
    child = make_model(executables=(ExecutableModel(name="tool", sources=(Path("main.cpp"),)),))
    parent = make_model(
        executables=(ExecutableModel(name="app", sources=(Path("src/main.cpp"),)),),
        subprojects=(SubprojectModel(directory=Path("tools/stamp"), project=child),),
    )
    files = emit_tree(parent, tool_version=FIXED_VERSION)
    assert files[Path("CMakeLists.txt")] == (golden_dir / "tree_parent.cmake").read_text(
        encoding="utf-8"
    )
    assert files[Path("tools/stamp/CMakeLists.txt")] == (golden_dir / "tree_child.cmake").read_text(
        encoding="utf-8"
    )


def _kitchen_sink_libraries() -> tuple[LibraryModel, ...]:
    """One library of each kind, wired into a small link graph."""
    headers = LibraryModel(
        name="headers",
        kind=LibraryKind.HEADER_ONLY,
        sources=(),
        public_include_dirs=(Path("include"),),
    )
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine.cpp"), Path("src/audio.cpp")),
        public_include_dirs=(Path("include"),),
        defines=(DefineModel("ENGINE_INTERNAL"),),
        links=(LinkModel(target="headers", public=True),),
    )
    plugin = LibraryModel(
        name="plugin",
        kind=LibraryKind.SHARED,
        sources=(Path("src/plugin.cpp"),),
        links=(LinkModel(target="engine", public=False),),
    )
    return (headers, engine, plugin)


def kitchen_sink_model() -> ProjectModel:
    """One model exercising every construct the Phase 1 emitter knows."""
    app = ExecutableModel(
        name="app",
        sources=(Path("src/main.cpp"),),
        defines=(DefineModel("GAME_MAX_PLAYERS", "8"),),
        compile_options=(
            CompileOptionsModel(flags=("-march=native",), compilers=("gnu", "clang")),
        ),
        links=(LinkModel(target="engine", public=False),),
    )
    return make_model(
        warnings="strict",
        executables=(app,),
        libraries=_kitchen_sink_libraries(),
    )
