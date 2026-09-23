"""Emitter coverage for private include directories and per-target cpp_std."""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import ExecutableModel, LibraryKind, LibraryModel, ProjectModel

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


def test_private_include_dirs_use_plain_relative_paths() -> None:
    """Private include dirs use plain relative paths, no BUILD_INTERFACE wrapping."""
    app = ExecutableModel(
        name="app",
        sources=(Path("src/main.cpp"),),
        private_include_dirs=(Path("src/internal"),),
    )
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert "target_include_directories(app PRIVATE\n    src/internal\n)" in text
    assert "BUILD_INTERFACE" not in text


def test_per_target_cpp_std_overrides_the_project_default() -> None:
    """Per-target cpp_std overrides the project default."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),), cpp_std=20)
    text = emit_cmakelists(make_model(cpp_std=17, executables=(app,)), tool_version=FIXED_VERSION)
    assert "target_compile_features(app PRIVATE cxx_std_20)" in text


def test_target_without_cpp_std_override_uses_the_project_default() -> None:
    """A target without its own cpp_std override uses the project's."""
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"),))
    text = emit_cmakelists(make_model(cpp_std=17, executables=(app,)), tool_version=FIXED_VERSION)
    assert "target_compile_features(app PRIVATE cxx_std_17)" in text


def test_library_private_include_dirs_stay_private_even_with_public_headers() -> None:
    """A library's private include dirs stay PRIVATE alongside PUBLIC headers."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine.cpp"),),
        public_include_dirs=(Path("include"),),
        private_include_dirs=(Path("src/engine_internal"),),
    )
    text = emit_cmakelists(make_model(libraries=(engine,)), tool_version=FIXED_VERSION)
    assert "target_include_directories(engine PRIVATE\n    src/engine_internal\n)" in text
    assert (
        "target_include_directories(engine PUBLIC\n"
        "    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>\n"
        ")"
    ) in text


def test_golden_target_vocab_file() -> None:
    """Golden target vocab file."""
    app = ExecutableModel(
        name="app",
        sources=(Path("src/main.cpp"),),
        private_include_dirs=(Path("src/internal"),),
        cpp_std=20,
    )
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine.cpp"),),
        public_include_dirs=(Path("include"),),
        private_include_dirs=(Path("src/engine_internal"),),
    )
    model = make_model(name="vocab_demo", cpp_std=17, executables=(app,), libraries=(engine,))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text == (GOLDEN_DIR / "target_vocab.cmake").read_text(encoding="utf-8")
