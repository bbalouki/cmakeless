# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Emitter coverage for tests, sanitizers, presets, toolchains, and install."""

from __future__ import annotations

import json
from pathlib import Path

from cmakeless.emitter import emit_cmakelists, emit_presets, emit_tree
from cmakeless.model.nodes import (
    ExecutableModel,
    InstallModel,
    LibraryKind,
    LibraryModel,
    LinkModel,
    PresetModel,
    ProjectModel,
    SubprojectModel,
    TestModel,
    ToolchainModel,
)

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


def catch2_test() -> TestModel:
    """A catch2 test target linking the framework's imported target."""
    return TestModel(
        name="engine_tests",
        sources=(Path("tests/engine_test.cpp"),),
        framework="catch2",
        links=(LinkModel(target="Catch2::Catch2WithMain", external=True),),
    )


def test_tests_enable_testing_and_discover_cases() -> None:
    """Tests enable testing and discover cases."""
    text = emit_cmakelists(make_model(tests=(catch2_test(),)), tool_version=FIXED_VERSION)
    assert "enable_testing()" in text
    assert "add_executable(engine_tests)" in text
    assert "include(Catch)" in text
    assert "list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/extras)" in text
    assert "catch_discover_tests(engine_tests)" in text


def test_gtest_and_doctest_discovery() -> None:
    """Gtest and doctest discovery."""
    gtest = TestModel(name="gt", sources=(Path("t.cpp"),), framework="gtest")
    doctest = TestModel(name="dt", sources=(Path("t.cpp"),), framework="doctest")
    text = emit_cmakelists(make_model(tests=(gtest, doctest)), tool_version=FIXED_VERSION)
    assert "include(GoogleTest)" in text
    assert "gtest_discover_tests(gt)" in text
    assert "include(${doctest_SOURCE_DIR}/scripts/cmake/doctest.cmake)" in text
    assert "doctest_discover_tests(dt)" in text


def test_framework_none_registers_a_plain_test() -> None:
    """Framework none registers a plain test."""
    smoke = TestModel(name="smoke", sources=(Path("t.cpp"),), framework="none")
    text = emit_cmakelists(make_model(tests=(smoke,)), tool_version=FIXED_VERSION)
    assert "add_test(NAME smoke COMMAND smoke)" in text
    assert "include(Catch)" not in text


def test_parent_of_testing_subproject_enables_testing() -> None:
    """Parent of testing subproject enables testing."""
    child = make_model(tests=(catch2_test(),))
    mounted = SubprojectModel(directory=Path("libs/engine"), project=child)
    parent = make_model(subprojects=(mounted,))
    files = emit_tree(parent, tool_version=FIXED_VERSION)
    assert "enable_testing()" in files[Path("CMakeLists.txt")]


def test_tests_linking_shared_libraries_get_dll_copies() -> None:
    """Tests linking shared libraries get dll copies."""
    engine = LibraryModel(name="engine", kind=LibraryKind.SHARED, sources=(Path("e.cpp"),))
    linked = TestModel(
        name="t",
        sources=(Path("t.cpp"),),
        framework="none",
        links=(LinkModel(target="engine"),),
    )
    text = emit_cmakelists(
        make_model(libraries=(engine,), tests=(linked,)), tool_version=FIXED_VERSION
    )
    assert "$<TARGET_RUNTIME_DLLS:t>" in text
    assert "COMMAND_EXPAND_LISTS" in text


def test_static_only_tests_get_no_dll_copy() -> None:
    """Static only tests get no dll copy."""
    engine = LibraryModel(name="engine", kind=LibraryKind.STATIC, sources=(Path("e.cpp"),))
    linked = TestModel(
        name="t",
        sources=(Path("t.cpp"),),
        framework="none",
        links=(LinkModel(target="engine"),),
    )
    text = emit_cmakelists(
        make_model(libraries=(engine,), tests=(linked,)), tool_version=FIXED_VERSION
    )
    assert "TARGET_RUNTIME_DLLS" not in text


def test_sanitizers_pair_compile_and_link_flags() -> None:
    """Sanitizers pair compile and link flags."""
    app = ExecutableModel(name="app", sources=(Path("m.cpp"),), sanitize=("address",))
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert (
        "target_compile_options(app PRIVATE\n"
        "    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-fsanitize=address;-fno-omit-frame-pointer>\n"
        "    $<$<CXX_COMPILER_ID:MSVC>:/fsanitize=address>\n"
        ")"
    ) in text
    assert (
        "target_link_options(app PRIVATE\n"
        "    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-fsanitize=address>\n"
        ")"
    ) in text


def test_msvc_rejects_unsupported_sanitizers_loudly() -> None:
    """Msvc rejects unsupported sanitizers loudly."""
    app = ExecutableModel(name="app", sources=(Path("m.cpp"),), sanitize=("address", "undefined"))
    text = emit_cmakelists(make_model(executables=(app,)), tool_version=FIXED_VERSION)
    assert "if(MSVC)" in text
    assert "MSVC does not support: undefined" in text


def test_preset_sanitizers_ride_the_cache_variable() -> None:
    """Preset sanitizers ride the cache variable."""
    app = ExecutableModel(name="app", sources=(Path("m.cpp"),))
    debug = PresetModel(name="debug", optimize="none", sanitize=("address",))
    text = emit_cmakelists(
        make_model(executables=(app,), presets=(debug,)), tool_version=FIXED_VERSION
    )
    assert 'set(CMAKELESS_SANITIZE "" CACHE STRING' in text
    assert (
        "$<$<AND:$<IN_LIST:address,${CMAKELESS_SANITIZE}>,$<NOT:$<CXX_COMPILER_ID:MSVC>>>:"
        "-fsanitize=address;-fno-omit-frame-pointer>"
    ) in text
    assert "target_link_options(app PRIVATE" in text


def test_presets_without_sanitizers_add_no_machinery() -> None:
    """Presets without sanitizers add no machinery."""
    app = ExecutableModel(name="app", sources=(Path("m.cpp"),))
    release = PresetModel(name="release", optimize="release")
    text = emit_cmakelists(
        make_model(executables=(app,), presets=(release,)), tool_version=FIXED_VERSION
    )
    assert "CMAKELESS_SANITIZE" not in text


def test_install_rules_and_export_set() -> None:
    """Install rules and export set."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("e.cpp"),),
        public_include_dirs=(Path("include"),),
    )
    model = make_model(libraries=(engine,), installs=(InstallModel(target="engine", headers=True),))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "include(GNUInstallDirs)" in text
    assert "install(TARGETS engine" in text
    assert "EXPORT demoTargets" in text
    assert "INCLUDES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}" in text
    assert "install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})" in text
    assert "NAMESPACE demo::" in text
    assert "write_basic_package_version_file" in text
    assert "configure_package_config_file" in text


def test_shared_install_ships_the_export_header() -> None:
    """Shared install ships the export header."""
    plugin = LibraryModel(name="plugin", kind=LibraryKind.SHARED, sources=(Path("p.cpp"),))
    model = make_model(libraries=(plugin,), installs=(InstallModel(target="plugin", headers=True),))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "install(FILES ${CMAKE_CURRENT_BINARY_DIR}/plugin_export.h" in text


def test_emit_tree_writes_the_config_template() -> None:
    """Emit tree writes the config template."""
    app = ExecutableModel(name="app", sources=(Path("m.cpp"),))
    model = make_model(executables=(app,), installs=(InstallModel(target="app"),))
    files = emit_tree(model, tool_version=FIXED_VERSION)
    template = files[Path("cmake/demoConfig.cmake.in")]
    assert "@PACKAGE_INIT@" in template
    assert "demoTargets.cmake" in template


def test_cpack_section_maps_formats_to_generators() -> None:
    """Cpack section maps formats to generators."""
    app = ExecutableModel(name="app", sources=(Path("m.cpp"),))
    model = make_model(
        executables=(app,),
        installs=(InstallModel(target="app"),),
        package_formats=("zip", "deb"),
    )
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert 'set(CPACK_GENERATOR "DEB;ZIP")' in text
    assert "set(CPACK_PACKAGE_CONTACT" in text
    assert text.rstrip().endswith("include(CPack)")


def test_presets_json_shape() -> None:
    """Presets json shape."""
    model = make_model(
        presets=(
            PresetModel(name="debug", optimize="none", sanitize=("address",)),
            PresetModel(name="release", optimize="release", lto=True),
        )
    )
    document = json.loads(emit_presets(model))
    debug, release = document["configurePresets"]
    assert debug["binaryDir"] == "${sourceDir}/build/debug"
    assert debug["cacheVariables"]["CMAKE_BUILD_TYPE"] == "Debug"
    assert debug["cacheVariables"]["CMAKELESS_SANITIZE"] == "address"
    assert release["cacheVariables"]["CMAKE_INTERPROCEDURAL_OPTIMIZATION"] == "ON"
    assert [preset["name"] for preset in document["buildPresets"]] == ["debug", "release"]
    assert document["testPresets"][0]["output"] == {"outputOnFailure": True}


def test_presets_json_resolves_toolchain_files() -> None:
    """Presets json resolves toolchain files."""
    model = make_model(
        presets=(PresetModel(name="cross", optimize="release", toolchain="arm64-linux"),),
        toolchains=(ToolchainModel(name="arm64-linux", compiler="aarch64-linux-gnu-g++"),),
    )
    document = json.loads(emit_presets(model))
    assert document["configurePresets"][0]["toolchainFile"] == (
        "${sourceDir}/cmake/toolchains/arm64-linux.cmake"
    )


def test_presets_json_includes_options_env_and_inherits() -> None:
    """Presets json includes options env and inherits."""
    model = make_model(
        presets=(
            PresetModel(name="base", optimize="release"),
            PresetModel(
                name="ci",
                optimize="release",
                options=(("MYLIB_BUILD_GUI", False), ("MYLIB_JOBS", 8)),
                env=(("CI", "1"),),
                inherits="base",
            ),
        )
    )
    document = json.loads(emit_presets(model))
    base, ci = document["configurePresets"]
    assert "inherits" not in base
    assert "environment" not in base
    assert ci["inherits"] == "base"
    assert ci["environment"] == {"CI": "1"}
    assert ci["cacheVariables"]["MYLIB_BUILD_GUI"] == "OFF"
    assert ci["cacheVariables"]["MYLIB_JOBS"] == "8"


def test_emit_tree_writes_presets_and_toolchains() -> None:
    """Emit tree writes presets and toolchains."""
    model = make_model(
        presets=(PresetModel(name="cross", optimize="release", toolchain="arm64-linux"),),
        toolchains=(
            ToolchainModel(
                name="arm64-linux",
                compiler="aarch64-linux-gnu-g++",
                system_name="Linux",
                system_processor="aarch64",
            ),
        ),
    )
    files = emit_tree(model, tool_version=FIXED_VERSION)
    assert Path("CMakePresets.json") in files
    toolchain = files[Path("cmake/toolchains/arm64-linux.cmake")]
    assert "set(CMAKE_SYSTEM_NAME Linux)" in toolchain
    assert "set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)" in toolchain
    assert "set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)" in toolchain


def test_wrapped_toolchains_are_never_rewritten() -> None:
    """Wrapped toolchains are never rewritten."""
    model = make_model(
        toolchains=(ToolchainModel(name="rpi4", file=Path("cmake/rpi4.toolchain.cmake")),)
    )
    files = emit_tree(model, tool_version=FIXED_VERSION)
    assert list(files) == [Path("CMakeLists.txt")]


def test_wrapped_toolchain_with_variables_gets_a_generated_wrapper(tmp_path: Path) -> None:
    """Wrapped toolchain with variables gets a generated wrapper."""
    ndk_toolchain = tmp_path / "ndk" / "build" / "cmake" / "android.toolchain.cmake"
    model = make_model(
        toolchains=(
            ToolchainModel(
                name="android-arm64-v8a",
                file=ndk_toolchain,
                variables=(("ANDROID_ABI", "arm64-v8a"), ("ANDROID_PLATFORM", "android-24")),
            ),
        )
    )
    files = emit_tree(model, tool_version=FIXED_VERSION)
    wrapper = files[Path("cmake/toolchains/android-arm64-v8a.cmake")]
    assert 'set(ANDROID_ABI "arm64-v8a")' in wrapper
    assert 'set(ANDROID_PLATFORM "android-24")' in wrapper
    assert f'include("{ndk_toolchain.as_posix()}")' in wrapper


def test_wrapped_toolchain_with_relative_file_includes_via_source_dir() -> None:
    """Wrapped toolchain with relative file includes via source dir."""
    model = make_model(
        toolchains=(
            ToolchainModel(
                name="custom",
                file=Path("cmake/custom.toolchain.cmake"),
                variables=(("FOO", "bar"),),
            ),
        )
    )
    files = emit_tree(model, tool_version=FIXED_VERSION)
    wrapper = files[Path("cmake/toolchains/custom.cmake")]
    assert 'include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/custom.toolchain.cmake")' in wrapper


def test_presets_point_absolute_wrapped_toolchains_at_their_own_path(tmp_path: Path) -> None:
    """Presets point absolute wrapped toolchains at their own path."""
    ndk_toolchain = tmp_path / "ndk" / "build" / "cmake" / "android.toolchain.cmake"
    model = make_model(
        presets=(PresetModel(name="cross", optimize="release", toolchain="ndk"),),
        toolchains=(ToolchainModel(name="ndk", file=ndk_toolchain),),
    )
    document = json.loads(emit_presets(model))
    assert document["configurePresets"][0]["toolchainFile"] == ndk_toolchain.as_posix()


def test_presets_point_variable_bearing_toolchains_at_the_generated_wrapper() -> None:
    """Presets point variable bearing toolchains at the generated wrapper."""
    model = make_model(
        presets=(PresetModel(name="cross", optimize="release", toolchain="ndk"),),
        toolchains=(
            ToolchainModel(
                name="ndk",
                file=Path("/opt/ndk/build/cmake/android.toolchain.cmake"),
                variables=(("ANDROID_ABI", "arm64-v8a"),),
            ),
        ),
    )
    document = json.loads(emit_presets(model))
    assert document["configurePresets"][0]["toolchainFile"] == (
        "${sourceDir}/cmake/toolchains/ndk.cmake"
    )


def test_presets_output_is_deterministic() -> None:
    """Presets output is deterministic."""
    model = make_model(presets=(PresetModel(name="debug"),))
    assert emit_presets(model) == emit_presets(model)


def _ship_targets() -> dict[str, object]:
    """The targets of the ship model: a library, an app, and a test."""
    engine = LibraryModel(
        name="engine",
        kind=LibraryKind.STATIC,
        sources=(Path("src/engine.cpp"),),
        public_include_dirs=(Path("include"),),
    )
    app = ExecutableModel(
        name="app",
        sources=(Path("src/main.cpp"),),
        links=(LinkModel(target="engine"),),
        sanitize=("address", "undefined"),
    )
    tests = TestModel(
        name="engine_tests",
        sources=(Path("tests/engine_test.cpp"),),
        framework="catch2",
        links=(
            LinkModel(target="engine"),
            LinkModel(target="Catch2::Catch2WithMain", external=True),
        ),
    )
    return {"libraries": (engine,), "executables": (app,), "tests": (tests,)}


def ship_model() -> ProjectModel:
    """One model exercising every construct the Phase 3 emitter knows."""
    return make_model(
        warnings="strict",
        **_ship_targets(),
        presets=(
            PresetModel(name="debug", optimize="none", sanitize=("address",)),
            PresetModel(name="release", optimize="release", lto=True),
            PresetModel(name="cross", optimize="release", toolchain="arm64-linux"),
        ),
        toolchains=(
            ToolchainModel(
                name="arm64-linux",
                compiler="aarch64-linux-gnu-g++",
                system_name="Linux",
                system_processor="aarch64",
            ),
        ),
        installs=(InstallModel(target="app"), InstallModel(target="engine", headers=True)),
        package_formats=("zip", "tgz"),
    )


def test_golden_ship_project() -> None:
    """Golden ship project."""
    golden_dir = Path(__file__).parent / "golden"
    files = emit_tree(ship_model(), tool_version=FIXED_VERSION)
    assert files[Path("CMakeLists.txt")] == (golden_dir / "ship.cmake").read_text(encoding="utf-8")
    assert files[Path("CMakePresets.json")] == (golden_dir / "ship_presets.json").read_text(
        encoding="utf-8"
    )
    assert files[Path("cmake/toolchains/arm64-linux.cmake")] == (
        golden_dir / "ship_toolchain.cmake"
    ).read_text(encoding="utf-8")
