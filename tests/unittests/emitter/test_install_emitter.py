"""Install components, RPATH, runtime DLLs, files, exports, CPack metadata, signing."""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists, emit_tree
from cmakeless.model.nodes import (
    ExecutableModel,
    InstallModel,
    LibraryKind,
    LibraryModel,
    ProjectModel,
)
from cmakeless.model.properties import (
    ExportModel,
    InstallFilesModel,
    InstallOptionsModel,
    PackageMetadataModel,
    SigningModel,
)

FIXED_VERSION = "1.2.3"
APP = ExecutableModel(name="app", sources=(Path("m.cpp"),))
LIB = LibraryModel(name="engine", kind=LibraryKind.SHARED, sources=(Path("e.cpp"),))


def make_model(**fields: object) -> ProjectModel:
    """Build a frozen project shipping the app and the engine."""
    return ProjectModel(
        name="demo",
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/does/not/matter"),
        source_script="cmakelessfile.py",
        executables=(APP,),
        libraries=(LIB,),
        **fields,  # type: ignore[arg-type]
    )


def test_components_and_relative_rpath() -> None:
    """A component is appended to each destination; RPATH is split per platform."""
    options = InstallOptionsModel(component="runtime", rpath="relative")
    text = emit_cmakelists(
        make_model(installs=(InstallModel(target="app", options=options),)),
        tool_version=FIXED_VERSION,
    )
    assert "RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR} COMPONENT runtime" in text
    assert '"$ORIGIN/../${CMAKE_INSTALL_LIBDIR};$ORIGIN"' in text
    assert '"@loader_path/../${CMAKE_INSTALL_LIBDIR};@loader_path"' in text


def test_runtime_dependencies_are_bundled_where_cmake_can_resolve_them() -> None:
    """Runtime dependency sets are guarded to native Windows, Linux, and macOS."""
    options = InstallOptionsModel(runtime_dependencies=True)
    text = emit_cmakelists(
        make_model(installs=(InstallModel(target="app", options=options),)),
        tool_version=FIXED_VERSION,
    )
    assert "RUNTIME_DEPENDENCY_SET app_runtime_dependencies" in text
    assert 'PRE_EXCLUDE_REGEXES "api-ms-.*" "ext-ms-.*"' in text
    assert "AND NOT CMAKE_CROSSCOMPILING)" in text


def test_install_files_respects_trailing_slash_semantics() -> None:
    """A contents-only directory install keeps its trailing slash."""
    files = InstallFilesModel(
        paths=(Path("assets"),), destination="share/demo", directory=True, contents_only=True
    )
    text = emit_cmakelists(make_model(install_files=(files,)), tool_version=FIXED_VERSION)
    assert "install(DIRECTORY\n    assets/\n    DESTINATION share/demo\n)" in text
    assert "include(GNUInstallDirs)" in text


def test_cps_export_raises_the_floor_and_adds_package_info() -> None:
    """A CPS export needs CMake 4.3, so only that project's floor moves."""
    model = make_model(
        installs=(InstallModel(target="engine"),),
        export=ExportModel(cps=True),
        package_metadata=PackageMetadataModel(description="An engine"),
    )
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text.splitlines()[4] == "cmake_minimum_required(VERSION 4.3)"
    assert (
        "install(PACKAGE_INFO demo\n    EXPORT demoTargets\n"
        '    VERSION ${PROJECT_VERSION}\n    DESCRIPTION "An engine"' in text
    )


def test_pkg_config_template_lists_installed_libraries() -> None:
    """The .pc template links every installed compiled library."""
    model = make_model(
        installs=(InstallModel(target="engine"),), export=ExportModel(pkg_config=True)
    )
    files = emit_tree(model, tool_version=FIXED_VERSION)
    template = files[Path("cmake") / "demo.pc.in"]
    assert "Libs: -L${libdir} -lengine\n" in template
    assert "configure_file(" in files[Path("CMakeLists.txt")]


def test_cpack_metadata_and_a_stable_wix_upgrade_code() -> None:
    """Metadata maps to CPACK_* variables; the WiX upgrade code is derived, not random."""
    metadata = PackageMetadataModel(
        vendor="Acme", contact="ops@acme.test", deb_depends=("libc6", "libstdc++6")
    )
    model = make_model(
        installs=(InstallModel(target="app"),),
        package_formats=("deb", "wix"),
        package_metadata=metadata,
    )
    first = emit_cmakelists(model, tool_version=FIXED_VERSION)
    second = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert first == second
    assert 'set(CPACK_PACKAGE_VENDOR "Acme")' in first
    assert 'set(CPACK_DEBIAN_PACKAGE_DEPENDS "libc6, libstdc++6")' in first
    assert "CPACK_WIX_UPGRADE_GUID" in first
    assert 'set(CPACK_GENERATOR "DEB;WIX")' in first


def test_signing_reads_credentials_only_from_the_environment() -> None:
    """The signing script names environment variables, never secrets."""
    signing = SigningModel(windows_cert_env="WIN_CERT", macos_identity_env="APPLE_ID")
    model = make_model(installs=(InstallModel(target="app"),), signing=signing)
    files = emit_tree(model, tool_version=FIXED_VERSION)
    script = files[Path("cmake") / "cmakeless_sign.cmake"]
    assert "if(WIN32 AND DEFINED ENV{WIN_CERT})" in script
    assert '--sign "$ENV{APPLE_ID}"' in script
    assert (
        "install(SCRIPT ${CMAKE_CURRENT_SOURCE_DIR}/cmake/cmakeless_sign.cmake)"
        in files[Path("CMakeLists.txt")]
    )


def test_python_modules_install_but_never_join_the_export_set() -> None:
    """A Python module is imported, not found with find_package()."""
    from cmakeless.model.nodes import PythonModuleModel

    module = PythonModuleModel(name="core", sources=(Path("b.cpp"),))
    model = ProjectModel(
        name="demo",
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/x"),
        source_script="cmakelessfile.py",
        python_modules=(module,),
        installs=(InstallModel(target="core"),),
    )
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "install(TARGETS core\n    LIBRARY DESTINATION .\n)" in text
    assert "install(EXPORT" not in text
