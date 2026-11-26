"""Per-target properties, typed links, tests, instrumentation, and conditional subprojects."""

from __future__ import annotations

from pathlib import Path

from cmakeless.api.when import When
from cmakeless.emitter import emit_cmakelists, emit_target_section
from cmakeless.model.nodes import (
    ExecutableModel,
    LibraryKind,
    LibraryModel,
    LinkKind,
    LinkModel,
    ProjectModel,
    SubprojectModel,
    TestModel,
)
from cmakeless.model.properties import (
    ExtensionUseModel,
    QtModel,
    TargetPropertiesModel,
    TestPropertiesModel,
)

FIXED_VERSION = "1.2.3"


def make_model(**fields: object) -> ProjectModel:
    """Build a frozen project from keyword fields."""
    return ProjectModel(
        name="demo",
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/does/not/matter"),
        source_script="cmakelessfile.py",
        **fields,  # type: ignore[arg-type]
    )


def emit(**fields: object) -> str:
    """Emit the CMakeLists.txt of a project built from keyword fields."""
    return emit_cmakelists(make_model(**fields), tool_version=FIXED_VERSION)


def test_mixed_language_sources_extend_the_project_languages() -> None:
    """A C file and a CUDA kernel enable C and CUDA beside CXX."""
    app = ExecutableModel(name="app", sources=(Path("main.cpp"), Path("hal.c"), Path("k.cu")))
    assert "LANGUAGES CXX C CUDA\n" in emit(executables=(app,), c_std=11)


def test_c_standard_applies_only_to_targets_with_c_sources() -> None:
    """c_std_11 is declared on the target that compiles C, and only there."""
    mixed = ExecutableModel(name="mixed", sources=(Path("main.cpp"), Path("hal.c")))
    pure = ExecutableModel(name="pure", sources=(Path("other.cpp"),))
    text = emit(executables=(mixed, pure), c_std=11)
    assert "target_compile_features(mixed PRIVATE c_std_11)" in text
    assert "target_compile_features(pure PRIVATE c_std_11)" not in text


def test_typed_links_render_threads_system_framework_and_guards() -> None:
    """Threads, OS libraries, frameworks, and guarded edges each render correctly."""
    links = (
        LinkModel(target="Threads::Threads", external=True, kind=LinkKind.THREADS),
        LinkModel(
            target="ws2_32",
            external=True,
            kind=LinkKind.SYSTEM,
            when=When.platform("windows")._freeze(),
        ),
        LinkModel(target="Metal", external=True, kind=LinkKind.FRAMEWORK),
    )
    app = ExecutableModel(name="app", sources=(Path("main.cpp"),), links=links)
    text = emit(executables=(app,))
    assert "find_package(Threads REQUIRED)" in text
    assert "PRIVATE $<$<PLATFORM_ID:Windows>:ws2_32>" in text
    assert "$<LINK_LIBRARY:FRAMEWORK,Metal>" in text


def test_output_abi_and_platform_properties_render_as_one_block() -> None:
    """Output name, ABI versions, visibility, and runtime share one property call."""
    properties = TargetPropertiesModel(
        output_name="engine2",
        version="2.3.1",
        soversion="2",
        visibility="hidden",
        msvc_runtime="static",
    )
    lib = LibraryModel(
        name="engine", kind=LibraryKind.SHARED, sources=(Path("e.cpp"),), properties=properties
    )
    text = emit(libraries=(lib,))
    for expected in (
        'OUTPUT_NAME "engine2"',
        "VERSION 2.3.1",
        "SOVERSION 2",
        "CXX_VISIBILITY_PRESET hidden",
        "VISIBILITY_INLINES_HIDDEN ON",
        'MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>"',
    ):
        assert expected in text


def test_object_and_plugin_libraries_use_their_cmake_keywords() -> None:
    """Object libraries are OBJECT; plugins are MODULE with an export header."""
    objects = LibraryModel(name="objs", kind=LibraryKind.OBJECT, sources=(Path("o.cpp"),))
    plugin = LibraryModel(name="strategy", kind=LibraryKind.PLUGIN, sources=(Path("p.cpp"),))
    text = emit(libraries=(objects, plugin))
    assert "add_library(objs OBJECT)" in text
    assert "add_library(strategy MODULE)" in text
    assert "generate_export_header(strategy)" in text


def test_embedded_settings_render_linker_script_map_file_and_post_build() -> None:
    """A linker script, map file, and objcopy step all land on the firmware target."""
    properties = TargetPropertiesModel(
        linker_script=Path("boards/f4.ld"),
        map_file=True,
        post_build=(("arm-none-eabi-objcopy", "-O", "ihex", "$<TARGET_FILE:fw>", "fw.hex"),),
    )
    fw = ExecutableModel(name="fw", sources=(Path("main.c"),), properties=properties)
    text = emit(executables=(fw,))
    assert "LINKER:-T,${CMAKE_CURRENT_SOURCE_DIR}/boards/f4.ld" in text
    assert 'LINK_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/boards/f4.ld"' in text
    assert "LINKER:-Map=$<TARGET_FILE_DIR:fw>/fw.map" in text
    assert 'add_custom_command(TARGET fw POST_BUILD\n    COMMAND "arm-none-eabi-objcopy"' in text


def test_qt_targets_get_automoc_and_one_find_package() -> None:
    """Qt components from every target merge into one find_package call."""
    qt = QtModel(major=6, components=("Widgets",), resources=(Path("ui/icons.qrc"),))
    ui = ExecutableModel(
        name="ui",
        sources=(Path("main.cpp"),),
        properties=TargetPropertiesModel(qt=qt, gui=True),
        links=(LinkModel(target="Qt6::Widgets", external=True, kind=LinkKind.IMPORTED),),
    )
    text = emit(executables=(ui,))
    assert "find_package(Qt6 REQUIRED COMPONENTS Widgets)" in text
    assert "AUTOMOC ON" in text and "WIN32_EXECUTABLE ON" in text
    assert "    ui/icons.qrc" in text


def test_extension_snippets_are_fenced_with_their_origin() -> None:
    """Plugin output names the plugin and its version."""
    use = ExtensionUseModel(name="nvtx", version="0.3.0", snippet="# nvtx for app")
    app = ExecutableModel(
        name="app", sources=(Path("m.cpp"),), properties=TargetPropertiesModel(extensions=(use,))
    )
    assert "# extension nvtx 0.3.0 for target 'app':\n# nvtx for app" in emit(executables=(app,))


def test_discovered_tests_forward_their_ctest_properties() -> None:
    """Timeouts, labels, and serial runs reach gtest_discover_tests."""
    properties = TestPropertiesModel(timeout=30, labels=("unit", "fast"), serial=True)
    test = TestModel(
        name="t", sources=(Path("t.cpp"),), framework="gtest", test_properties=properties
    )
    text = emit(tests=(test,))
    assert "gtest_discover_tests(t\n    PROPERTIES\n        TIMEOUT 30" in text
    assert 'LABELS "unit\\\\;fast"' in text
    assert "RUN_SERIAL ON" in text


def test_plain_tests_use_set_tests_properties() -> None:
    """A framework-less test gets its properties through set_tests_properties."""
    properties = TestPropertiesModel(env=(("MODE", "ci"),), will_fail=True)
    test = TestModel(name="t", sources=(Path("t.cpp"),), test_properties=properties)
    text = emit(tests=(test,))
    assert 'set_tests_properties(t PROPERTIES\n    ENVIRONMENT "MODE=ci"\n    WILL_FAIL ON' in text


def test_coverage_instrumentation_reaches_every_compiled_target() -> None:
    """--coverage lands on compile and link of each target, guarded to GNU syntax."""
    app = ExecutableModel(name="app", sources=(Path("m.cpp"),))
    text = emit(executables=(app,), instrumentation=("coverage",))
    assert text.count("$<$<NOT:${CMAKELESS_MSVC_SYNTAX}>:--coverage>") == 2


def test_pgo_use_reads_different_paths_for_gcc_and_clang() -> None:
    """GCC reads the profile directory; Clang reads the merged .profdata file."""
    app = ExecutableModel(name="app", sources=(Path("m.cpp"),))
    text = emit(executables=(app,), instrumentation=("pgo-use",))
    assert "-fprofile-use=${CMAKELESS_PGO_DIR};-fprofile-correction" in text
    assert "-fprofile-use=${CMAKELESS_PGO_DIR}/cmakeless.profdata" in text
    assert 'set(CMAKELESS_PGO_DIR "${CMAKE_BINARY_DIR}/../pgo-profiles" CACHE PATH' in text


def test_a_conditional_subproject_is_wrapped_in_an_if_block() -> None:
    """add_subproject(when=...) becomes a configure-time if() around the subdirectory."""
    child = make_model()
    node = SubprojectModel(
        directory=Path("gui"), project=child, when=When.platform("windows", "linux")._freeze()
    )
    text = emit(subprojects=(node,))
    assert (
        'if(CMAKE_SYSTEM_NAME STREQUAL "Windows" OR CMAKE_SYSTEM_NAME STREQUAL "Linux")\n'
        "    add_subdirectory(gui)\nendif()"
    ) in text


def test_emit_target_section_returns_one_target_or_none() -> None:
    """'cmakeless explain' can render exactly one target's CMake."""
    app = ExecutableModel(name="app", sources=(Path("m.cpp"),))
    model = make_model(executables=(app,))
    section = emit_target_section(model, "app", tool_version=FIXED_VERSION)
    assert section is not None and section.startswith("add_executable(app)")
    assert emit_target_section(model, "missing", tool_version=FIXED_VERSION) is None
