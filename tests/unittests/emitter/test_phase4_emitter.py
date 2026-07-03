"""Emitter coverage for Python modules: backends, stubs, and settings reuse."""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import (
    DefineModel,
    LibraryKind,
    LibraryModel,
    LinkModel,
    ProjectModel,
    PythonModuleModel,
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


def nanobind_module(**overrides: object) -> PythonModuleModel:
    """A nanobind module with one source, overridable per test."""
    fields: dict[str, object] = {
        "name": "core",
        "sources": (Path("src/bindings.cpp"),),
        "binding": "nanobind",
    }
    fields.update(overrides)
    return PythonModuleModel(**fields)  # type: ignore[arg-type]


def test_python_module_finds_python_and_calls_add_module() -> None:
    """Python module finds python and calls add module."""
    model = make_model(python_modules=(nanobind_module(),))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "find_package(Python 3.13 COMPONENTS Interpreter Development.Module REQUIRED)" in text
    assert "nanobind_add_module(core)" in text
    assert "target_sources(core PRIVATE" in text
    assert "target_compile_features(core PRIVATE cxx_std_17)" in text


def test_nanobind_module_generates_a_stub() -> None:
    """Nanobind module generates a stub."""
    model = make_model(python_modules=(nanobind_module(),))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "nanobind_add_stub(core_stub" in text
    assert "OUTPUT core.pyi" in text


def test_stubs_disabled_emits_no_stub_block() -> None:
    """Stubs disabled emits no stub block."""
    module = nanobind_module(stubs=False)
    text = emit_cmakelists(make_model(python_modules=(module,)), tool_version=FIXED_VERSION)
    assert "nanobind_add_stub" not in text


def test_pybind11_module_forces_findpython_and_skips_stub() -> None:
    """Pybind11 module forces findpython and skips stub."""
    module = nanobind_module(binding="pybind11")
    text = emit_cmakelists(make_model(python_modules=(module,)), tool_version=FIXED_VERSION)
    assert "pybind11_add_module(core)" in text
    assert "set(PYBIND11_FINDPYTHON ON)" in text
    # pybind11 ships no CMake stub command, so no stub target is emitted.
    assert "nanobind_add_stub" not in text


def test_module_settings_and_links_reuse_the_shared_blocks() -> None:
    """Module settings and links reuse the shared blocks."""
    module = nanobind_module(
        defines=(DefineModel(name="CORE_FAST", value="1"),),
        links=(LinkModel(target="engine"),),
    )
    engine = LibraryModel(name="engine", kind=LibraryKind.STATIC, sources=(Path("src/e.cpp"),))
    text = emit_cmakelists(
        make_model(libraries=(engine,), python_modules=(module,)), tool_version=FIXED_VERSION
    )
    assert "target_compile_definitions(core PRIVATE" in text
    assert "target_link_libraries(core" in text
    assert "PRIVATE engine" in text


def test_no_python_preamble_without_modules() -> None:
    """No python preamble without modules."""
    text = emit_cmakelists(make_model(), tool_version=FIXED_VERSION)
    assert "find_package(Python" not in text


def test_python_module_output_is_deterministic() -> None:
    """Python module output is deterministic."""
    model = make_model(python_modules=(nanobind_module(binding="pybind11"),))
    assert emit_cmakelists(model, tool_version=FIXED_VERSION) == emit_cmakelists(
        model, tool_version=FIXED_VERSION
    )


def test_python_module_golden_file() -> None:
    """Python module golden file."""
    engine = LibraryModel(name="engine", kind=LibraryKind.STATIC, sources=(Path("src/engine.cpp"),))
    module = PythonModuleModel(
        name="mymath",
        sources=(Path("src/bindings.cpp"),),
        binding="pybind11",
        stubs=False,
        defines=(DefineModel(name="MYMATH_VERSION", value="1"),),
        links=(LinkModel(target="engine"),),
    )
    model = make_model(
        name="mymath_demo", libraries=(engine,), python_modules=(module,), warnings="strict"
    )
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text == (GOLDEN_DIR / "python_module.cmake").read_text(encoding="utf-8")
