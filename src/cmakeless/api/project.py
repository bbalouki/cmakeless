"""The Project facade: the root object users interact with.

project.build() hides freeze, validate, emit, configure, and compile behind
one verb.
"""

from __future__ import annotations

import dataclasses
import os
import runpy
import shutil
import sys
import sysconfig
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless._parallel import parallel_map
from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.api._callsite import calling_frame
from cmakeless.api._runs import build_options, test_options
from cmakeless.api.assets import shader_steps
from cmakeless.api.cache import Cache
from cmakeless.api.commands import Command, CustomTarget
from cmakeless.api.dependencies import Dependencies
from cmakeless.api.globals import CMakeGlobals
from cmakeless.api.modules import CMakeModule, check_file_reference, check_module_path
from cmakeless.api.options import Option
from cmakeless.api.presets import Preset
from cmakeless.api.profiles import Profile
from cmakeless.api.rules import Rules
from cmakeless.api.signing import MacSigning, WindowsSigning
from cmakeless.api.targets import (
    Executable,
    Library,
    LibraryKindName,
    PythonBindingName,
    PythonModule,
    Test,
    TestFrameworkName,
)
from cmakeless.api.toolchains import Toolchain
from cmakeless.api.when import When
from cmakeless.api.workflows import WORKFLOW_VERBS, run_workflow
from cmakeless.deps import (
    LOCKFILE_NAME,
    DependencyProvider,
    collect_tree_dependencies,
    provider_for,
    read_lockfile,
    resolve_dependencies,
)
from cmakeless.driver import CMakeDriver, select_generator
from cmakeless.driver.cmake_driver import resolve_tool
from cmakeless.driver.file_api import CMakeInfo, TargetInfo
from cmakeless.driver.globals import probe_globals
from cmakeless.driver.reflection import reflect, reflect_work_dir
from cmakeless.emitter import emit_tree
from cmakeless.errors import ConfigurationError
from cmakeless.model.languages import NON_COMPILED_SUFFIXES, is_known_suffix
from cmakeless.model.nodes import (
    BUILD_TYPE_BY_OPTIMIZE,
    CompileOptionsModel,
    InstallModel,
    LinkOptionsModel,
    ModuleKind,
    OptionType,
    PresetModel,
    ProjectModel,
    PythonModuleModel,
    SubprojectModel,
    ToolchainModel,
    WhenModel,
)
from cmakeless.model.properties import (
    ExportModel,
    InstallFilesModel,
    InstallOptionsModel,
    PackageMetadataModel,
    SigningModel,
)
from cmakeless.model.validate import validate_project
from cmakeless.observer import (
    ConsoleObserver,
    DependencyResolved,
    JsonObserver,
    Observer,
    publish,
)

DEFAULT_BUILD_DIR_NAME = "build"

# The dynamic-library suffixes a built Python extension can carry, so the
# current-environment install can find it under the build tree.
_MODULE_SUFFIXES: tuple[str, ...] = (".pyd", ".so", ".dylib")


class _Prepared(NamedTuple):
    """A configured pipeline run: the driver plus the context it needs.

    Attributes:
        driver: The CMake driver bound to the selected build directory.
        model: The resolved project model that produced the outputs.
        build_dir: The build directory of the selected preset.
    """

    driver: CMakeDriver
    model: ProjectModel
    build_dir: Path


# The framework versions add_test() requires when the user does not; every
# version here carries a curated SHA256 pin in the registry, so test projects
# resolve without any network.
_FRAMEWORK_SPECS: dict[str, str] = {
    "catch2": "catch2/3.5.4",
    "gtest": "googletest/1.14.0",
    "doctest": "doctest/2.4.11",
}

# The binding-library package add_python_module() fetches per backend; the
# registry knows each one's source URL and CMake name, and the pin is hashed
# and written to cmakeless.lock on first resolution.
_BINDING_SPECS: dict[str, str] = {
    "nanobind": "nanobind/2.4.0",
    "pybind11": "pybind11/2.13.6",
}


# libFuzzer supplies main() and instruments coverage; ASan and UBSan turn
# silent memory corruption into a crash the fuzzer can minimize.
_LIBFUZZER_FLAGS: tuple[str, ...] = ("-fsanitize=fuzzer,address,undefined",)
_MSVC_FUZZER_FLAGS: tuple[str, ...] = ("/fsanitize=fuzzer", "/fsanitize=address")


class Project:
    """The root build description and the facade over the whole pipeline.

    Attributes:
        warnings: Warning preset name ("strict", "default", or "none");
            plain attribute, assign to change it.
        package_manager: Dependency strategy ("auto", "find_package",
            "vcpkg", or "conan"); plain attribute, assign to change it.
        cache: True (the default) to wire ccache/sccache as the compiler
            launcher when one is on PATH; plain attribute, assign to
            change it.
        optimize: Optimization level for the default (no-preset) build
            ("none", "debug", "release", "relwithdebinfo", or "minsize"),
            or None (the default) to leave the build type unset; an active
            preset overrides it. Plain attribute, assign to change it.
        lto: True to enable interprocedural optimization on the default
            build; a preset's own setting wins when one is active. Plain
            attribute, assign to change it.
        warnings_as_errors: True to fail the build on any warning
            (COMPILE_WARNING_AS_ERROR); 'cmake --compile-no-warning-as-error'
            still relaxes it locally. Plain attribute.
        c_std: The C standard C sources compile with, or None for the
            compiler default. Plain attribute.
        profile: The project-wide Profile, or None. Plain attribute.
        supply_chain: "default", or "strict" to refuse trust-on-first-use
            pins, plain-HTTP URLs, and unlisted system packages. Plain
            attribute.
        name: The project name (read-only property).
        root: Absolute project root directory (read-only property).
        dependencies: The project's dependency collection (read-only
            property).
    """

    def __init__(
        self,
        name: str,
        *,
        version: str = "0.1.0",
        cpp_std: int = 17,
        warnings: str = "default",
        root: str | Path | None = None,
        c_std: int | None = None,
        profile: Profile | None = None,
        supply_chain: str = "default",
    ) -> None:
        """Start describing a project.

        Args:
            name: The CMake project name.
            version: The project version string, passed to CMake.
            cpp_std: The C++ standard every target compiles with.
            warnings: Warning preset ("max", "strict", "default", or "none").
            root: Project root directory; defaults to the directory of the
                script that constructed the Project (usually cmakelessfile.py).
            c_std: The C standard C sources compile with, or None.
            profile: A Profile applied to every target, or None.
            supply_chain: "default" or "strict" dependency checking.
        """
        self._name = name
        self._version = version
        self._cpp_std = cpp_std
        self.warnings = warnings
        self.package_manager = "auto"
        self.optimize: str | None = None
        self.lto = False
        self.warnings_as_errors = False
        self.c_std = c_std
        self.profile = profile
        self.supply_chain = supply_chain
        self.cache: bool | Cache = True
        frame = calling_frame()
        script = frame[0] if frame is not None else None
        self._root = _resolve_root(root, script)
        self._source_script = script.name if script is not None else BUILD_SCRIPT_NAME
        self._dependencies = Dependencies(self)
        self._generator: str | None = None
        # The console display is the default listener; add_observer() adds more.
        self._observers: list[Observer] = [ConsoleObserver()]
        self._init_collections()
        _context.register_project(self)

    def _init_collections(self) -> None:
        """Initialize the empty target, preset, and rule collections."""
        self._lint_clang_tidy: tuple[str, ...] = ()
        self._lint_iwyu: tuple[str, ...] = ()
        self._lint_cppcheck: tuple[str, ...] = ()
        self._executables: list[Executable] = []
        self._libraries: list[Library] = []
        self._tests: list[Test] = []
        self._python_modules: list[PythonModule] = []
        self._presets: list[Preset] = []
        self._options: list[Option] = []
        self._toolchains: list[Toolchain] = []
        self._installs: list[InstallModel] = []
        self._install_files: list[InstallFilesModel] = []
        self._package_formats: tuple[str, ...] = ()
        self._package_metadata = PackageMetadataModel()
        self._signing: SigningModel | None = None
        self._export = ExportModel()
        self._allow_system: list[str] = []
        self._fuzz_targets: list[Executable] = []
        self._raw_cmake_files: list[str] = []
        self._subprojects: list[tuple[Path, Project, WhenModel | None]] = []
        self._commands: list[Command] = []
        self._custom_targets: list[CustomTarget] = []
        self._modules: list[CMakeModule] = []
        self._cmake_globals_cache: dict[str | None, CMakeGlobals] = {}

    @property
    def name(self) -> str:
        """The CMake project name."""
        return self._name

    @property
    def root(self) -> Path:
        """Absolute path of the project root directory."""
        return self._root

    @property
    def lock_path(self) -> Path:
        """Where this project's pins live: its own lockfile, or its workspace's."""
        shared = _context.active_lock_path()
        return shared if shared is not None else self._root / LOCKFILE_NAME

    @property
    def dependencies(self) -> Dependencies:
        """The project's dependency collection; supports .lock()."""
        return self._dependencies

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The name, version, C++ standard, and root of this project.
        """
        return (
            f"Project(name={self._name!r}, version={self._version!r}, "
            f"cpp_std={self._cpp_std}, root={str(self._root)!r})"
        )

    def add_executable(
        self, name: str, sources: Sequence[str], *, modules: Sequence[str] = ()
    ) -> Executable:
        """Declare a runnable target built from the given source files or globs.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns, project-root-relative.
            modules: C++20 module interface units this target defines, or
                glob patterns matching them.

        Returns:
            The mutable Executable builder, for further link()/define() calls.
        """
        executable = Executable(
            name,
            sources,
            modules=modules,
            script=self._source_script,
            dependencies=self._dependencies,
        )
        self._executables.append(executable)
        return executable

    def add_library(
        self,
        name: str,
        sources: Sequence[str] = (),
        *,
        public_headers: str | Sequence[str] = (),
        kind: LibraryKindName = "static",
        modules: Sequence[str] = (),
        version: str | None = None,
        soversion: str | None = None,
    ) -> Library:
        """Declare a library target.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns; empty for header-only.
            public_headers: Directory (or directories) whose headers
                consumers may include.
            kind: "static", "shared", "object", "plugin", or "header_only".
            modules: C++20 module interface units this library exports, or
                glob patterns matching them; consumers import them without
                any include directory.
            version: A shared library's full ABI version, for example "2.3.1".
            soversion: A shared library's ABI compatibility version, for
                example "2".

        Returns:
            The mutable Library builder, for further link()/define() calls.

        Raises:
            ConfigurationError: When ``kind`` is not a known library kind.
        """
        library = Library(
            name,
            sources,
            public_headers=public_headers,
            kind=kind,
            modules=modules,
            version=version,
            soversion=soversion,
            script=self._source_script,
            dependencies=self._dependencies,
        )
        self._libraries.append(library)
        return library

    def add_subproject(self, path: str | Path, *, when: When | None = None) -> Project:
        """Mount a self-contained child project at a directory under the root.

        The child directory must contain its own cmakelessfile.py describing
        exactly one Project; it is executed in description mode, so its own
        project.build() call registers the project instead of building.

        Args:
            path: Directory of the child project, relative to this root.
            when: A configure-time condition (platform, compiler, or option;
                never a build configuration) guarding the whole subproject.

        Returns:
            The captured child Project.

        Raises:
            ConfigurationError: When the child has no cmakelessfile.py,
                describes a number of projects other than one, or closes a
                mount cycle.
        """
        directory = Path(path)
        script = self._root / directory / BUILD_SCRIPT_NAME
        if not script.is_file():
            raise ConfigurationError(
                f"Subproject '{directory.as_posix()}' added in {self._source_script} "
                f"has no build description (looked for {script}). Create a "
                f"{BUILD_SCRIPT_NAME} there, or fix the path."
            )
        with _context.loading_script(script), _context.capturing_projects() as captured:
            runpy.run_path(str(script))
        if len(captured) != 1:
            raise ConfigurationError(
                f"Subproject '{directory.as_posix()}' must describe exactly one "
                f"Project in its {BUILD_SCRIPT_NAME}, found {len(captured)}. Keep one "
                f"Project per {BUILD_SCRIPT_NAME}; split anything else into further "
                f"subprojects."
            )
        child = captured[0]
        self._subprojects.append((directory, child, when._freeze() if when is not None else None))
        return child

    def add_test(
        self,
        name: str,
        sources: Sequence[str],
        *,
        framework: TestFrameworkName = "gtest",
        timeout: int | None = None,
        labels: Sequence[str] = (),
    ) -> Test:
        """Declare a test executable registered with CTest.

        The framework is acquired like any dependency (registry-pinned
        FetchContent fallback, or the project's package manager) and linked
        automatically; 'cmakeless test' builds and runs everything.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns, project-root-relative.
            framework: "gtest" (the default), "catch2", "doctest", or "none"
                for a plain executable whose exit code is the verdict.
            timeout: Seconds before CTest kills a case, or None.
            labels: Labels for 'cmakeless test --label'.

        Returns:
            The mutable Test builder, for further link()/define() calls.

        Raises:
            ConfigurationError: When ``framework`` is not a known one.
        """
        test = Test(
            name,
            sources,
            framework=framework,
            script=self._source_script,
            dependencies=self._dependencies,
        )
        test.timeout = timeout
        test.labels = list(labels)
        if framework in _FRAMEWORK_SPECS:
            dependency = self._dependencies.add(_FRAMEWORK_SPECS[framework])
            test._dependency_links.append((dependency, False, None))
        self._tests.append(test)
        return test

    def add_fuzz_target(self, name: str, sources: Sequence[str]) -> Executable:
        """Declare a libFuzzer target, built with the fuzzer and ASan runtimes.

        The sources define LLVMFuzzerTestOneInput(); libFuzzer supplies
        main(). Clang and MSVC (cl and clang-cl) are supported; GCC has no
        libFuzzer, so the flags are inert there. Run it with 'cmakeless fuzz'.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns, project-root-relative.

        Returns:
            The executable builder, for further link()/define() calls.
        """
        target = Executable(
            name, sources, script=self._source_script, dependencies=self._dependencies
        )
        clang = When.compiler("clang")._freeze()
        msvc = When.compiler("msvc")._freeze()
        target._compile_options.extend(
            (
                CompileOptionsModel(flags=_LIBFUZZER_FLAGS, when=clang),
                CompileOptionsModel(flags=_MSVC_FUZZER_FLAGS, when=msvc),
            )
        )
        target._link_options.append(LinkOptionsModel(flags=_LIBFUZZER_FLAGS, when=clang))
        self._fuzz_targets.append(target)
        return target

    def add_python_module(
        self,
        name: str,
        sources: Sequence[str],
        *,
        binding: PythonBindingName = "pybind11",
        stubs: bool = True,
        install: bool = True,
        python_version: str | None = None,
    ) -> PythonModule:
        """Declare a Python extension module built with pybind11 or nanobind.

        The binding backend is acquired like any dependency (registry-pinned
        FetchContent fallback) so its <binding>_add_module command is
        available. After 'cmakeless build' the module is copied into the
        invoking interpreter, so 'import <name>' works immediately.

        Args:
            name: The importable module name and unique target name.
            sources: Source files or glob patterns, project-root-relative.
            binding: "pybind11" (the default) or "nanobind".
            stubs: True to generate a .pyi stub (nanobind only).
            install: True to copy the built module into the current
                environment after build.
            python_version: The minimum Python version find_package(Python
                ...) requires, as "MAJOR.MINOR" (for example "3.12"), or
                None (the default) to use CMakeless's own supported floor.
                This is independent of whichever interpreter happens to
                invoke cmakeless, so the generated CMakeLists.txt stays
                byte-identical across machines.

        Returns:
            The mutable PythonModule builder, for further link()/define()
            calls.

        Raises:
            ConfigurationError: When ``binding`` is not a known backend, or
                ``python_version`` is not a well-formed "MAJOR.MINOR" string.
        """
        module = PythonModule(
            name,
            sources,
            binding=binding,
            stubs=stubs,
            install=install,
            python_version=python_version,
            script=self._source_script,
            dependencies=self._dependencies,
        )
        # The <binding>_add_module command links the backend itself, so the
        # dependency is registered for the fetch and lockfile only, never as
        # a manual link edge.
        self._dependencies.add(_BINDING_SPECS[binding])
        self._python_modules.append(module)
        return module

    def add_preset(self, preset: Preset) -> Preset:
        """Register a named configuration, emitted into CMakePresets.json.

        Args:
            preset: The preset to register.

        Returns:
            The registered preset, unchanged.
        """
        self._presets.append(preset)
        return preset

    def option(
        self,
        name: str,
        *,
        default: bool | int | str,
        help: str = "",
        type: type[bool] | type[int] | type[str] | None = None,
    ) -> Option:
        """Declare a CMake cache variable this project's users can override.

        Args:
            name: The cache-variable name, for example "MYLIB_BUILD_GUI".
            default: The default value.
            help: Shown by cmake-gui/ccmake and the 'cmakeless options' verb.
            type: bool, int, or str; inferred from default when omitted.

        Returns:
            The typed Option handle, usable in When.option(...) and
            Preset(options={...}).

        Raises:
            ConfigurationError: When neither ``type`` nor ``default`` names
                a supported cache-variable type.
        """
        option = Option(name, default=default, help=help, type=type, script=self._source_script)
        self._options.append(option)
        return option

    def add_toolchain(self, toolchain: Toolchain) -> Toolchain:
        """Register a toolchain that presets can reference by name.

        Args:
            toolchain: The toolchain to register.

        Returns:
            The registered toolchain, unchanged.
        """
        self._toolchains.append(toolchain)
        return toolchain

    def lint(
        self,
        *,
        clang_tidy: bool | Sequence[str] | Rules = False,
        iwyu: bool | Sequence[str] = False,
        cppcheck: bool | Sequence[str] = False,
    ) -> None:
        """Wire clang-tidy, include-what-you-use, and cppcheck into every compiled target.

        Applies to every executable, library, test, and Python module that
        has not called its own target.lint() (which always wins for that
        target); header-only libraries compile nothing, so they are
        silently skipped rather than erroring.

        Args:
            clang_tidy: True to run clang-tidy with its own defaults, a
                sequence to pass the command and extra arguments (for
                example ["clang-tidy", "-checks=-*,modernize-*"]), or False
                (the default) to disable it.
            iwyu: True to run include-what-you-use, a sequence for the
                command and extra arguments, or False (the default) to
                disable it.
            cppcheck: True to run cppcheck alongside the compiler, a
                sequence for the command and extra arguments, or False.
        """
        tidy = clang_tidy.command() if isinstance(clang_tidy, Rules) else clang_tidy
        self._lint_clang_tidy = _lint_tool_names(tidy, tool="clang-tidy")
        self._lint_iwyu = _lint_tool_names(iwyu, tool="include-what-you-use")
        self._lint_cppcheck = _lint_tool_names(cppcheck, tool="cppcheck")

    def install(
        self,
        target: Executable | Library | PythonModule,
        *,
        headers: bool = False,
        component: str | None = None,
        rpath: str | None = None,
        destination: str | None = None,
        runtime_dependencies: bool = False,
    ) -> None:
        """Declare that a target ships: emitted as install and export rules.

        Installed libraries come with an export set and Config.cmake files,
        so other CMake users can find_package() this project.

        Args:
            target: An executable, library, or Python module of this project.
            headers: True to also install the target's public header
                directories.
            component: The CPack component ("runtime", "dev", ...), or None.
            rpath: "relative" so the installed binary finds its sibling
                libraries without LD_LIBRARY_PATH; None for CMake's default.
            destination: An install-prefix-relative directory overriding the
                GNUInstallDirs default.
            runtime_dependencies: True to also install the shared libraries
                (DLLs, .so, .dylib) the target loads, so an archive runs on a
                clean machine.

        Raises:
            ConfigurationError: When ``target`` is not a target object.
        """
        if not isinstance(target, Executable | Library | PythonModule):
            raise ConfigurationError(
                f"project.install() in {self._source_script} needs a target "
                f"created by add_executable(), add_library(), or "
                f"add_python_module(), got {type(target).__name__}."
            )
        options = InstallOptionsModel(
            component=component,
            rpath=rpath,
            destination=destination,
            runtime_dependencies=runtime_dependencies,
        )
        self._installs.append(InstallModel(target=target.name, headers=headers, options=options))

    def install_files(self, *paths: str, destination: str, component: str | None = None) -> None:
        """Ship plain files or directories (configs, assets, licenses) on install.

        A directory written with a trailing '/' installs its contents; without
        it, the directory itself lands inside ``destination``.

        Args:
            *paths: Project-relative files or directories, all of one kind.
            destination: Install-prefix-relative directory, for example
                "share/mygame".
            component: The CPack component, or None.

        Raises:
            ConfigurationError: When no path is given, or files and
                directories are mixed in one call.
        """
        self._install_files.append(
            _install_files_model(self._root, paths, destination, component, self._source_script)
        )

    def export(self, *, cmake: bool = True, cps: bool = False, pkg_config: bool = False) -> None:
        """Choose which package metadata formats install() exports.

        Args:
            cmake: Classic Config.cmake files for find_package().
            cps: A Common Package Specification file, readable by any
                CPS-aware tool (raises this project's CMake floor to 4.3).
            pkg_config: A .pc file, for Meson, Autotools, and pkg-config.
        """
        self._export = ExportModel(cmake=cmake, cps=cps, pkg_config=pkg_config)

    def package(
        self,
        *,
        formats: Sequence[str] = ("zip",),
        vendor: str | None = None,
        contact: str | None = None,
        description: str | None = None,
        homepage: str | None = None,
        license_file: str | None = None,
        deb_depends: Sequence[str] = (),
        rpm_requires: Sequence[str] = (),
    ) -> None:
        """Request CPack packaging of everything install() declared.

        Args:
            formats: Package formats: "zip", "tgz", "txz", "7z", "deb",
                "rpm", "nsis", "wix", "dmg", or "productbuild".
            vendor: The organization shipping the package.
            contact: Maintainer contact; Debian packages require one.
            description: One-line package summary.
            homepage: Project homepage URL.
            license_file: Project-relative license file shown by installers.
            deb_depends: Debian package dependencies, for example "libc6".
            rpm_requires: RPM package requirements.
        """
        self._package_formats = tuple(formats)
        self._package_metadata = PackageMetadataModel(
            vendor=vendor,
            contact=contact,
            description=description,
            homepage=homepage,
            license_file=Path(license_file) if license_file is not None else None,
            deb_depends=tuple(deb_depends),
            rpm_requires=tuple(rpm_requires),
        )

    def sign(
        self, *, windows: WindowsSigning | None = None, macos: MacSigning | None = None
    ) -> None:
        """Sign installed binaries at install time, reading credentials from the environment.

        Args:
            windows: Signing.signtool(...) settings, or None.
            macos: Signing.codesign(...) settings, or None.
        """
        self._signing = SigningModel(
            windows_cert_env=windows.cert_env if windows is not None else None,
            windows_timestamp_url=windows.timestamp_url if windows is not None else None,
            macos_identity_env=macos.identity_env if macos is not None else None,
        )

    def allow_system(self, *names: str) -> None:
        """Let supply_chain="strict" take these packages from the system.

        Args:
            *names: Package names, as written in depends() specs.
        """
        self._allow_system.extend(names)

    def add_shaders(
        self,
        pattern: str,
        *,
        compiler: str,
        output: str,
        profile: str | None = None,
    ) -> tuple[Command, ...]:
        """Compile shaders as build steps, one per source, rebuilt when they change.

        Args:
            pattern: A project-relative glob, for example "shaders/*.hlsl".
            compiler: "dxc", "glslc", "glslangValidator", or "slangc".
            output: Project-relative directory the compiled shaders land in,
                under the build tree.
            profile: The compiler's target profile (required for dxc, for
                example "ps_6_6").

        Returns:
            One Command per shader; pass them to target.add_sources(*shaders).

        Raises:
            ConfigurationError: When the compiler is unknown, dxc has no
                profile, or the pattern matches nothing.
        """
        sources = sorted(path.relative_to(self._root) for path in self._root.glob(pattern))
        steps = shader_steps(sources, compiler=compiler, profile=profile, output=output)
        return tuple(
            self.add_command(
                output=[compiled], command=argv, depends=[source], comment=f"Compiling {source}"
            )
            for compiled, argv, source in steps
        )

    def add_assets(
        self, directory: str, *, cook: Sequence[str], into: str, name: str | None = None
    ) -> CustomTarget:
        """Cook a directory of assets with your own tool, as an always-run target.

        Args:
            directory: The project-relative asset directory.
            cook: The cooking tool's argument vector; the source directory
                and the output directory are appended.
            into: The output directory, relative to the build tree.
            name: The custom target name, or None for "cook_<directory>".

        Returns:
            The registered CustomTarget.
        """
        stem = Path(directory).name or "assets"
        files = sorted(
            path.relative_to(self._root).as_posix()
            for path in (self._root / directory).rglob("*")
            if path.is_file()
        )
        return self.add_custom_target(
            name or f"cook_{stem}", command=[*cook, directory, into], depends=files
        )

    def raw_cmake_file(self, path: str | Path) -> None:
        """Include an existing CMake file at the top of the generated build.

        The project-level escape hatch: the file is emitted as an include()
        near the top of CMakeLists.txt, fenced with a comment naming its
        cmakelessfile.py origin, in the order added. The path must name a real file
        inside the project root; existence is checked at freeze time.

        Args:
            path: The CMake file to include, relative to the project root,
                for example "cmake/legacy_weirdness.cmake".
        """
        self._raw_cmake_files.append(str(path))

    def add_command(
        self,
        output: Sequence[str],
        command: Sequence[str],
        *,
        depends: Sequence[str | Command] = (),
        comment: str | None = None,
    ) -> Command:
        """Declare a build-time step that produces files other targets consume.

        Args:
            output: Files this command produces, project-root-relative.
            command: The argument vector to run; never a shell string.
            depends: Files (or other Command handles) that trigger a re-run
                when changed.
            comment: Shown while the command runs, or None.

        Returns:
            The Command handle; pass it to a target's add_sources(), or to
            another add_command()'s/add_custom_target()'s depends=, to wire
            the dependency edge.

        Raises:
            ConfigurationError: When ``output`` or ``command`` is empty.
        """
        command_step = Command(
            output=output,
            command=command,
            depends=depends,
            comment=comment,
            script=self._source_script,
        )
        self._commands.append(command_step)
        return command_step

    def add_custom_target(
        self, name: str, *, command: Sequence[str], depends: Sequence[str | Command] = ()
    ) -> CustomTarget:
        """Declare an always-run target: docs, lint, asset cooking.

        Args:
            name: The CMake target name; shares the project's target
                namespace.
            command: The argument vector to run.
            depends: Files (or Command handles) that must be up to date
                first.

        Returns:
            The registered CustomTarget.

        Raises:
            ConfigurationError: When ``command`` is empty.
        """
        target = CustomTarget(name, command=command, depends=depends, script=self._source_script)
        self._custom_targets.append(target)
        return target

    def include(self, path: str | Path) -> CMakeModule:
        """Include a local CMake file, reflected via real CMake immediately.

        Discovers the file's functions, variables, and targets by running
        real CMake (never a hand-written CMake-language parser), so
        mod.call(...) can validate against what the file actually defines
        before any CMakeLists.txt is emitted. This is the one exception to
        "generating CMakeLists.txt never needs CMake": reflection needs the
        real tool, so CMake must be on PATH when this is called (the same
        way targets_info() already needs it, just earlier in the script).

        Args:
            path: The CMake file to include, relative to the project root,
                for example "cmake/print_build_summary.cmake".

        Returns:
            The CMakeModule handle: read .functions/.variables/.targets,
            call mod.call(...) to invoke a discovered function or macro, or
            mod.variable(...) to read a discovered variable's value.

        Raises:
            ConfigurationError: When the path is not relative, escapes the
                project root, or does not exist.
            ToolchainError: When cmake is not on PATH.
            CMakeError: When reflecting the file fails.
        """
        relative = Path(path)
        check_file_reference(relative, root=self._root, script=self._source_script)
        reflection = reflect(
            resolve_tool("cmake"),
            work_dir=self._reflect_work_dir(relative.as_posix()),
            reference=str(self._root / relative),
            is_file=True,
            module_path=None,
            cpp_std=self._cpp_std,
        )
        module = CMakeModule(
            kind=ModuleKind.FILE,
            reference=relative.as_posix(),
            module_path=None,
            reflection=reflection,
            script=self._source_script,
        )
        self._modules.append(module)
        return module

    def include_module(self, name: str, *, module_path: str | Path | None = None) -> CMakeModule:
        """Include a named CMake module, reflected via real CMake immediately.

        Args:
            name: The module name, for example "CheckCXXCompilerFlag" (a
                built-in CMake module) or a project-supplied one findable
                via module_path.
            module_path: An extra directory to search for the module,
                relative to the project root, or None to use only CMake's
                own built-in modules.

        Returns:
            The CMakeModule handle, as project.include() returns.

        Raises:
            ConfigurationError: When module_path is set but not relative,
                escapes the project root, or does not exist.
            ToolchainError: When cmake is not on PATH.
            CMakeError: When reflecting the module fails.
        """
        relative_module_path = Path(module_path) if module_path is not None else None
        if relative_module_path is not None:
            check_module_path(relative_module_path, root=self._root, script=self._source_script)
        reflection = reflect(
            resolve_tool("cmake"),
            work_dir=self._reflect_work_dir(name),
            reference=name,
            is_file=False,
            module_path=(self._root / relative_module_path)
            if relative_module_path is not None
            else None,
            cpp_std=self._cpp_std,
        )
        module = CMakeModule(
            kind=ModuleKind.NAMED,
            reference=name,
            module_path=relative_module_path,
            reflection=reflection,
            script=self._source_script,
        )
        self._modules.append(module)
        return module

    def cmake_globals(self, *, toolchain: Toolchain | None = None) -> CMakeGlobals:
        """Query every CMake variable a real configure defines, right now.

        Runs a throwaway CMake configure immediately (never a hand-written
        CMake-language parser), so a branch like
        ``if hasattr(project.cmake_globals(), "ANDROID"): app.link(...)``
        can steer the rest of this description before anything is emitted.
        With no toolchain given this reflects the host build; platform
        variables such as ANDROID or IOS are only ever defined when the
        matching toolchain is passed here, since Project has no single
        "active toolchain" outside of what individual presets reference.

        Args:
            toolchain: A toolchain to probe under, or None (the default) for
                the host toolchain.

        Returns:
            The CMakeGlobals handle: ``hasattr(result, name)`` mirrors
            CMake's ``if(DEFINED name)``, and ``result.NAME`` (or
            ``result.get("NAME")``) reads a discovered variable's resolved
            value. Cached per toolchain, so a second call with the same
            argument reuses the first probe rather than reconfiguring.

        Raises:
            ConfigurationError: When ``toolchain`` wraps a file that does
                not exist.
            ToolchainError: When cmake is not on PATH.
            CMakeError: When the throwaway configure fails.
        """
        key = toolchain.name if toolchain is not None else None
        if key not in self._cmake_globals_cache:
            toolchain_model = self._checked_toolchain_model(toolchain)
            values = probe_globals(
                resolve_tool("cmake"),
                work_dir=self._reflect_work_dir(f"__globals__:{key}" if key else "__globals__"),
                cpp_std=self._cpp_std,
                toolchain=toolchain_model,
            )
            self._cmake_globals_cache[key] = CMakeGlobals(values)
        return self._cmake_globals_cache[key]

    def _checked_toolchain_model(self, toolchain: Toolchain | None) -> ToolchainModel | None:
        """Freeze and eagerly validate a toolchain for cmake_globals().

        Mirrors the freeze-time file-existence check every other toolchain
        reference gets (model/validate.py's _check_toolchain_shape),
        since cmake_globals() runs before freeze() when a toolchain
        argument is given.

        Args:
            toolchain: The toolchain to probe under, or None.

        Returns:
            The frozen ToolchainModel, or None.

        Raises:
            ConfigurationError: When the toolchain wraps a file that does
                not exist.
        """
        if toolchain is None:
            return None
        model = toolchain._freeze()
        if model.file is not None:
            resolved = model.file if model.file.is_absolute() else self._root / model.file
            if not resolved.is_file():
                raise ConfigurationError(
                    f"project.cmake_globals(toolchain={model.name!r}) in "
                    f"{self._source_script} wraps '{model.file.as_posix()}', "
                    f"which does not exist (looked for {resolved}). Check "
                    f"the path is correct."
                )
        return model

    def _reflect_work_dir(self, key: str) -> Path:
        """A unique scratch directory for one include()/include_module() reflection.

        Args:
            key: The reference being reflected (a path or a module name).

        Returns:
            A directory under build/, so project.clean() reclaims it too.
        """
        return reflect_work_dir(self._build_dir(), key)

    def freeze(self) -> ProjectModel:
        """Freeze the mutable description into the validated, immutable model.

        Returns:
            The validated ProjectModel, subprojects included.

        Raises:
            ConfigurationError: When the description is invalid.
        """
        model = _with_implicit_sanitize_preset(self._freeze_without_validation())
        validate_project(model)
        _warn_unused_command_outputs(model)
        _warn_unknown_suffixes(model)
        return model

    def generate(self) -> list[Path]:
        """Emit all CMakeLists.txt files (and manifests) without invoking CMake.

        Generation never requires CMake to be installed. Dependencies are
        resolved first, which refreshes cmakeless.lock; with a complete
        lockfile this needs no network either.

        Returns:
            The written file paths, parent project first.

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
        """
        return self._write_outputs(self._resolved_model())

    def configure(self) -> None:
        """Generate build files and run the CMake configure step.

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
            ToolchainError: When cmake or the package manager is missing.
            CMakeError: When the configure step fails.
        """
        self._configure(self._prepare().driver)

    def targets_info(self) -> tuple[TargetInfo, ...]:
        """Configure the build and return its targets as Python objects.

        Reads the CMake File API, so the result reflects the fully
        configured build (resolved dependencies, generated modules, and
        install rules included), not just the build description.

        Returns:
            One TargetInfo per configured target, sorted by name.

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
            ToolchainError: When cmake or the package manager is missing.
            CMakeError: When the configure step fails.
        """
        driver = self._prepare().driver
        self._configure(driver)
        return driver.targets_info()

    def cmake_info(self) -> CMakeInfo:
        """Configure the build and read the resolved generator, compilers, and options.

        Uses the same CMake File API pattern targets_info() does: no
        --trace-expand, no scraping.

        Returns:
            The resolved generator, compiler ID/version per language,
            system name/processor, and this project's own declared
            options' final values (after any -D override or preset
            options= override has been applied by CMake itself).

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
            ToolchainError: When cmake or the package manager is missing.
            CMakeError: When the configure step fails.
        """
        prepared = self._prepare()
        self._configure(prepared.driver)
        raw = prepared.driver.cmake_info()
        declared = {option.name: option.value_type for option in prepared.model.options}
        coerced = tuple(
            (name, _coerce_option_value(value, declared[name]))
            for name, value in raw.options
            if name in declared and isinstance(value, str)
        )
        return dataclasses.replace(raw, options=coerced)

    def configure_presets(self) -> None:
        """Configure every registered preset, concurrently where it pays.

        Each preset configures into its own out-of-source build tree, and
        the frozen model is shared across threads without locks, so on a
        free-threaded interpreter the configures overlap in wall-clock time.

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
            ToolchainError: When cmake or the package manager is missing.
            CMakeError: When any configure step fails.
        """
        model = self._resolved_model()
        self._write_outputs(model)
        provider = self._provider(model)
        names = [preset.name for preset in model.presets]
        if not names:
            self._configure_one(model, provider, None)
            return
        parallel_map(lambda name: self._configure_one(model, provider, name), names)

    def _configure_one(
        self, model: ProjectModel, provider: DependencyProvider | None, preset: str | None
    ) -> None:
        """Configure a single preset's build tree.

        Args:
            model: The resolved project model, presets included.
            provider: The dependency backend, or None for a dep-free tree.
            preset: The preset name, or None for the default configuration.
        """
        build_dir = self._build_dir(preset)
        build_type = self._resolve_build_type(model, preset)
        if provider is not None:
            provider.pre_configure(
                root_dir=self._root,
                build_dir=build_dir,
                build_type=build_type,
                offline=_context.active_offline(),
            )
        self._driver(model, provider, preset=preset).configure()

    def test(self) -> None:
        """Build everything, then run the test suite through CTest.

        Honors the active preset ('cmakeless test --preset debug') and the
        sanitizer override ('cmakeless test --sanitize=address'), which
        runs in its own build tree under build/.

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
            ToolchainError: When cmake or the package manager is missing.
            CMakeError: When configuring, compiling, or a test fails.
        """
        driver = self._prepare().driver
        self._configure(driver)
        driver.build(build_options())
        driver.test(test_options(), build=build_options())

    def clean(self) -> None:
        """Delete this project's build directory, if it exists."""
        build_dir = self._root / DEFAULT_BUILD_DIR_NAME
        if build_dir.is_dir():
            shutil.rmtree(build_dir)
            print(f"[cmakeless] Removed {build_dir}")

    def build(self) -> None:
        """Freeze, validate, emit, configure, and compile: the whole pipeline.

        Under the cmakeless CLI this dispatches to the verb the user asked
        for, so one cmakelessfile.py serves 'cmakeless build', 'configure', 'test',
        'install', 'package', 'clean', 'lock', and 'options'. In description
        mode (this project is being loaded as a subproject) it does nothing:
        the parent owns the pipeline.

        Raises:
            ConfigurationError: When the description is invalid.
            DependencyError: When a package cannot be resolved.
            ToolchainError: When cmake or the package manager is missing.
            CMakeError: When configuring, compiling, testing, installing,
                or packaging fails.
        """
        if _context.in_description_mode():
            return
        verb = _context.active_verb()
        if verb == "clean":
            self.clean()
        elif verb == "configure":
            self.configure()
        elif verb == "lock":
            self._refresh_lock()
        elif verb == "options":
            self._print_options()
        elif verb == "sbom":
            self._generate_sbom()
        elif verb == "vendor":
            self._vendor_dependencies()
        elif verb == "test":
            self.test()
        elif verb in ("install", "package"):
            self._run_post_build_verb(verb)
        elif verb in WORKFLOW_VERBS:
            run_workflow(self, verb)
        else:
            prepared = self._prepare()
            self._configure(prepared.driver)
            prepared.driver.build(build_options())
            self._install_python_modules_into_environment(prepared.model, prepared.build_dir)

    def set_generator(self, generator: str | None) -> None:
        """Choose the CMake generator for this project's builds.

        Args:
            generator: "ninja", "vs", any raw CMake -G name, or None to
                auto-select (Ninja when available).
        """
        self._generator = generator

    def add_observer(self, observer: Observer) -> Observer:
        """Register a progress-event consumer for this project's builds.

        The driver publishes a StepStarted/StepFinished/StepFailed event for
        every configure, build, test, install, and package step; observers
        run alongside the default console display.

        Args:
            observer: Any object with an on_event(event) method.

        Returns:
            The registered observer, unchanged.
        """
        self._observers.append(observer)
        return observer

    def _run_post_build_verb(self, verb: str) -> None:
        """Perform the 'install' or 'package' verb: build first, then ship.

        Args:
            verb: "install" or "package".
        """
        driver = self._prepare().driver
        self._configure(driver)
        driver.build(build_options())
        if verb == "install":
            config = _context.active_run_options().config
            driver.install(prefix=_context.active_prefix(), config=config)
        else:
            driver.package()

    def _configure(self, driver: CMakeDriver) -> None:
        """Run the configure step with the CLI's --fresh and -D settings.

        Args:
            driver: The driver bound to the selected build tree.
        """
        options = _context.active_run_options()
        driver.configure(fresh=options.fresh, defines=options.defines)

    def _install_python_modules_into_environment(
        self, model: ProjectModel, build_dir: Path
    ) -> None:
        """Copy freshly built Python modules into the invoking interpreter.

        This is what makes 'import <name>' work immediately after a build;
        the generated CMake stays standalone, so the copy lives in Python.

        Args:
            model: The resolved model, for the modules and their flags.
            build_dir: The build directory the artifacts were compiled into.
        """
        modules = [module for module in model.python_modules if module.install_to_environment]
        if not modules:
            return
        site_packages = Path(sysconfig.get_path("platlib"))
        site_packages.mkdir(parents=True, exist_ok=True)
        for module in modules:
            self._copy_built_module(module, build_dir, site_packages)

    def _copy_built_module(
        self, module: PythonModuleModel, build_dir: Path, site_packages: Path
    ) -> None:
        """Copy one built extension and its stub into site-packages.

        Args:
            module: The Python module whose artifact to copy.
            build_dir: The build directory to search for the artifact.
            site_packages: The invoking interpreter's platlib directory.
        """
        artifact = _find_built_module(build_dir, module.name)
        if artifact is None:
            return
        shutil.copyfile(artifact, site_packages / artifact.name)
        stub = next(build_dir.rglob(f"{module.name}.pyi"), None)
        if stub is not None:
            shutil.copyfile(stub, site_packages / stub.name)
        print(f"[cmakeless] Installed module {module.name!r} into {site_packages}")

    def _prepare(self, *, build_dir: Path | None = None) -> _Prepared:
        """Freeze, resolve, write outputs, and bind a driver to the result.

        Args:
            build_dir: A build tree overriding the preset's, used to build
                the same configuration twice side by side; None for the
                usual one.

        Returns:
            The driver, the resolved model, and the selected build
            directory, backend pre-configure hooks already run.

        Raises:
            ConfigurationError: When the description is invalid or the
                selected preset does not exist.
            DependencyError: When a package cannot be resolved.
        """
        model = self._resolved_model()
        self._write_outputs(model)
        preset = self._selected_preset(model)
        provider = self._provider(model)
        build_dir = build_dir if build_dir is not None else self._build_dir(preset)
        if provider is not None:
            build_type = self._resolve_build_type(model, preset)
            provider.pre_configure(
                root_dir=self._root,
                build_dir=build_dir,
                build_type=build_type,
                offline=_context.active_offline(),
            )
        driver = self._driver(model, provider, preset=preset, build_dir=build_dir)
        return _Prepared(driver, model, build_dir)

    def _resolve_build_type(self, model: ProjectModel, preset: str | None) -> str:
        """Resolve the CMake build type a dependency backend should install for.

        Args:
            model: The resolved project model, presets included.
            preset: The active preset name, or None for the default
                configuration.

        Returns:
            The active preset's optimize level translated to a CMake build
            type when a preset is selected, else project.optimize when set,
            else "Release" (the implicit default, kept for zero-config
            backward compatibility with projects that never touch optimize
            or presets).
        """
        if preset is not None:
            matching = next(candidate for candidate in model.presets if candidate.name == preset)
            return BUILD_TYPE_BY_OPTIMIZE[matching.optimize]
        if self.optimize is not None:
            return BUILD_TYPE_BY_OPTIMIZE[self.optimize]
        return "Release"

    def _selected_preset(self, model: ProjectModel) -> str | None:
        """Resolve the preset this run should use, if any.

        The CLI --preset override wins; --sanitize selects the implicit
        sanitize preset freeze() added to the model.

        Args:
            model: The frozen project, presets included.

        Returns:
            The preset name, or None for the default configuration.

        Raises:
            ConfigurationError: When the selected preset is not defined.
        """
        name = _context.active_preset()
        if name is None and _context.active_sanitize():
            name = _implicit_sanitize_preset_name(_context.active_sanitize())
        if name is None:
            return None
        known = sorted(preset.name for preset in model.presets)
        if name not in known:
            listing = ", ".join(repr(preset) for preset in known) if known else "none are defined"
            raise ConfigurationError(
                f"Unknown preset {name!r} for project {self._name!r}: known presets "
                f"are {listing}. Add project.add_preset(Preset({name!r}, ...)) in "
                f"{self._source_script}, or pick an existing one."
            )
        return name

    def _build_dir(self, preset: str | None = None) -> Path:
        """The out-of-source build directory for the given preset.

        Args:
            preset: The active preset name, or None for the default.

        Returns:
            build/ for the default configuration, build/<preset> for a
            preset (matching the binaryDir emitted into CMakePresets.json),
            and build/<instrumentation> for an instrumented run, so coverage
            or PGO never dirties the normal tree.
        """
        instrumentation = _context.active_run_options().instrumentation
        if preset is None and instrumentation:
            return self._root / DEFAULT_BUILD_DIR_NAME / "-".join(instrumentation)
        if preset is None:
            return self._root / DEFAULT_BUILD_DIR_NAME
        return self._root / DEFAULT_BUILD_DIR_NAME / preset

    def _freeze_without_validation(self) -> ProjectModel:
        """Freeze this project and its subprojects without validating.

        Validation runs once, at the top of the tree, in freeze().

        Returns:
            The frozen but not yet validated ProjectModel.
        """
        return self._freeze_shipping(self._freeze_policy(self._freeze_core()))

    def _freeze_core(self) -> ProjectModel:
        """Freeze targets, dependencies, and settings: everything but what ships.

        Returns:
            The frozen core; _freeze_shipping() adds the install side.
        """
        return ProjectModel(
            name=self._name,
            version=self._version,
            cpp_std=self._cpp_std,
            root_dir=self._root,
            source_script=self._source_script,
            warnings=self.warnings,
            package_manager=self.package_manager,
            executables=tuple(target._freeze(self._root) for target in self._executables),
            libraries=tuple(target._freeze(self._root) for target in self._libraries),
            tests=tuple(target._freeze(self._root) for target in self._tests),
            python_modules=tuple(module._freeze(self._root) for module in self._python_modules),
            dependencies=self._dependencies._freeze(),
            subprojects=self._freeze_subprojects(),
            presets=tuple(preset._freeze() for preset in self._presets),
            options=tuple(option._freeze() for option in self._options),
            commands=tuple(command._freeze() for command in self._commands),
            custom_targets=tuple(target._freeze() for target in self._custom_targets),
            modules=tuple(module._freeze() for module in self._modules),
            toolchains=tuple(toolchain._freeze() for toolchain in self._toolchains),
            cache=bool(self.cache),
            optimize=self.optimize,
            lto=self.lto,
            raw_cmake_files=tuple(Path(raw_file) for raw_file in self._raw_cmake_files),
            lint_clang_tidy=self._lint_clang_tidy,
            lint_iwyu=self._lint_iwyu,
            lint_cppcheck=self._lint_cppcheck,
        )

    def _freeze_policy(self, core: ProjectModel) -> ProjectModel:
        """Add the build-policy settings (standards, profile, supply chain) to a core.

        Args:
            core: The model _freeze_core() produced.

        Returns:
            The model with compiler, profile, cache, and supply-chain policy set.
        """
        return dataclasses.replace(
            core,
            cache_backend=self.cache._freeze() if isinstance(self.cache, Cache) else None,
            c_std=self.c_std,
            warnings_as_errors=self.warnings_as_errors,
            profile=self.profile._freeze() if self.profile is not None else None,
            supply_chain=self.supply_chain,
            allow_system=tuple(self._allow_system),
            instrumentation=_context.active_run_options().instrumentation,
            fuzz_targets=tuple(target._freeze(self._root) for target in self._fuzz_targets),
        )

    def _freeze_shipping(self, core: ProjectModel) -> ProjectModel:
        """Add the install, packaging, export, and signing settings to a frozen core.

        Args:
            core: The model _freeze_core() produced.

        Returns:
            The complete frozen model.
        """
        return dataclasses.replace(
            core,
            installs=tuple(self._installs),
            install_files=tuple(self._install_files),
            package_formats=self._package_formats,
            package_metadata=self._package_metadata,
            signing=self._signing,
            export=self._export,
        )

    def _freeze_subprojects(self) -> tuple[SubprojectModel, ...]:
        """Freeze every mounted subproject without validating it yet.

        Returns:
            One SubprojectModel per add_subproject() call, in call order.
        """
        return tuple(
            SubprojectModel(
                directory=directory, project=child._freeze_without_validation(), when=when
            )
            for directory, child, when in self._subprojects
        )

    def _resolved_model(self) -> ProjectModel:
        """Freeze, validate, and resolve dependencies into a complete model.

        Returns:
            The model with every dependency pin filled; resolution also
            refreshes cmakeless.lock when the tree has dependencies.
        """
        model = resolve_dependencies(
            self.freeze(), lock_path=self.lock_path, offline=_context.active_offline()
        )
        for dependency in collect_tree_dependencies(model):
            event = DependencyResolved(
                step="resolve",
                name=dependency.name,
                version=dependency.version,
                pin_source=dependency.pin_source,
            )
            publish(self._active_observers(), event)
        return model

    def _active_observers(self) -> list[Observer]:
        """The observers this run notifies: JSON lines replace the console under --json.

        Returns:
            The observers, in registration order.
        """
        if not _context.active_run_options().json_events:
            return self._observers
        others = [
            observer for observer in self._observers if not isinstance(observer, ConsoleObserver)
        ]
        return [JsonObserver(), *others]

    def _write_outputs(self, model: ProjectModel) -> list[Path]:
        """Write the emitted CMake tree and any backend manifest files.

        Args:
            model: The resolved project model.

        Returns:
            The written file paths, parent project first.
        """
        files = emit_tree(model, tool_version=__version__)
        provider = self._provider(model)
        if provider is not None:
            files.update(provider.manifest_files(model, read_lockfile(self.lock_path)))
        written: list[Path] = []
        for relative_path, text in files.items():
            output = self._root / relative_path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8", newline="\n")
            written.append(output)
        return written

    def _provider(self, model: ProjectModel) -> DependencyProvider | None:
        """Select the dependency provider, when the tree has dependencies.

        Args:
            model: The frozen project model.

        Returns:
            The backend adapter, or None for a dependency-free tree.
        """
        if not collect_tree_dependencies(model):
            return None
        return provider_for(model.package_manager)

    def _refresh_lock(self) -> None:
        """Perform the 'lock' verb: refresh every pin in cmakeless.lock."""
        lock_path = self._dependencies.lock()
        if lock_path.is_file():
            print(f"[cmakeless] Dependency pins refreshed in {lock_path}")
        else:
            print("[cmakeless] No dependencies to lock; nothing written.")

    def _generate_sbom(self) -> None:
        """Perform the 'sbom' verb: write a bill of materials from cmakeless.lock."""
        path = self._dependencies.sbom(
            format=_context.active_sbom_format(), output=_context.active_sbom_output()
        )
        print(f"[cmakeless] Wrote {path}")

    def _vendor_dependencies(self) -> None:
        """Perform the 'vendor' verb: download every locked dependency for offline builds."""
        directory = self._dependencies.vendor(directory=_context.active_vendor_directory())
        print(f"[cmakeless] Vendored dependencies into {directory}")

    def _print_options(self) -> None:
        """Perform the 'options' verb: list every declared option, no build.

        Uses freeze() only (validated, offline, no dependency resolution, no
        file writes, no CMake), so a project's knobs are discoverable
        without running the pipeline.
        """
        model = self.freeze()
        if not model.options:
            print("[cmakeless] No options declared.")
            return
        for option in sorted(model.options, key=lambda candidate: candidate.name):
            help_suffix = f": {option.help}" if option.help else ""
            print(
                f"[cmakeless] {option.name} ({option.value_type.value}, "
                f"default={option.default!r}){help_suffix}"
            )

    def _driver(
        self,
        model: ProjectModel,
        provider: DependencyProvider | None = None,
        *,
        preset: str | None = None,
        build_dir: Path | None = None,
    ) -> CMakeDriver:
        """Build the driver for this project's source and build directories.

        Args:
            model: The resolved project model, presets included.
            provider: The dependency backend whose toolchain arguments the
                configure step needs, or None for a dependency-free tree.
            preset: The active preset name, or None for the default
                configuration.
            build_dir: A build tree overriding the preset's, or None.

        Returns:
            A CMakeDriver honoring the project's or CLI's generator choice,
            the preset's build directory, and the cache setting.
        """
        build_dir = build_dir if build_dir is not None else self._build_dir(preset)
        build_type = self._resolve_build_type(model, preset)
        extra = (
            provider.toolchain_args(build_dir, build_type=build_type)
            if provider is not None
            else ()
        )
        extra = (*extra, *_python_hint(model))
        backend = model.cache_backend
        return CMakeDriver(
            source_dir=self._root,
            build_dir=build_dir,
            generator=select_generator(self._generator or _context.active_generator()),
            extra_configure_args=extra,
            preset=preset,
            use_cache=model.cache,
            observers=self._active_observers(),
            source_owners=_source_owners(model),
            cache_tool=backend.tool if backend is not None else None,
            cache_env=_expand_cache_env(backend.env) if backend is not None else None,
        )


def _python_hint(model: ProjectModel) -> tuple[str, ...]:
    """Point CMake's FindPython at the interpreter running cmakeless.

    Without the hint FindPython takes whichever Python it finds first, which
    can build an extension against the wrong ABI: a GIL build's module
    segfaults when a free-threaded interpreter imports it. The hint is a
    configure argument, so the generated CMakeLists.txt stays standalone.

    Args:
        model: The resolved project, subprojects included.

    Returns:
        The -DPython_EXECUTABLE argument, or nothing for a tree without
        Python modules.
    """
    if not _tree_has_python_modules(model):
        return ()
    return (f"-DPython_EXECUTABLE={Path(sys.executable).as_posix()}",)


def _tree_has_python_modules(model: ProjectModel) -> bool:
    """Tell whether a project or any subproject builds a Python module.

    Args:
        model: The project node.

    Returns:
        True when an extension module exists anywhere in the tree.
    """
    return bool(model.python_modules) or any(
        _tree_has_python_modules(node.project) for node in model.subprojects
    )


def _source_owners(model: ProjectModel) -> dict[str, str]:
    """Map every compiled source to the target that compiles it.

    Args:
        model: The frozen project.

    Returns:
        Project-relative POSIX source path to "target 'x' (declared at
        cmakelessfile.py:N)".
    """
    owners: dict[str, str] = {}
    for target in model.all_targets():
        line = target.properties.declared_line
        where = f" (declared at {model.source_script}:{line})" if line is not None else ""
        for source in target.sources:
            owners.setdefault(source.as_posix(), f"target {target.name!r}{where}")
    return owners


def _expand_cache_env(env: Sequence[tuple[str, str]]) -> dict[str, str]:
    """Resolve "$NAME" references in a cache backend's environment.

    Args:
        env: (name, value) pairs; a value starting with "$" copies another
            environment variable, so secrets never live in the description.

    Returns:
        The environment to add for build steps; unset references are dropped.
    """
    resolved: dict[str, str] = {}
    for name, value in env:
        actual = os.environ.get(value[1:]) if value.startswith("$") else value
        if actual is not None:
            resolved[name] = actual
    return resolved


def _lint_tool_names(value: bool | Sequence[str], *, tool: str) -> tuple[str, ...]:
    """Normalize a project.lint()/target.lint() argument to its command tuple.

    Args:
        value: True for the tool's own defaults, a sequence for the command
            and extra arguments, or False to disable it.
        tool: The tool's default command name ("clang-tidy" or
            "include-what-you-use"), used when ``value`` is True.

    Returns:
        An empty tuple when disabled, else the command as a tuple.
    """
    if value is False:
        return ()
    if value is True:
        return (tool,)
    return tuple(value)


def _resolve_root(root: str | Path | None, script: Path | None) -> Path:
    """Resolve the project root from the explicit argument or the script.

    Args:
        root: The root passed to Project(), or None to derive one.
        script: The build description that constructed the project, or None.

    Returns:
        The explicit root when given, else the script's directory, else the
        current working directory.
    """
    if root is not None:
        return Path(root).resolve()
    if script is not None:
        return script.parent
    return Path.cwd()


def _find_built_module(build_dir: Path, name: str) -> Path | None:
    """Locate a compiled extension module under a build tree.

    Args:
        build_dir: The build directory to search recursively.
        name: The module name; the file is name.<abi><suffix>.

    Returns:
        The first matching artifact (any platform suffix), or None when the
        build produced none (for example a failed or filtered build).
    """
    for candidate in sorted(build_dir.rglob(f"{name}.*")):
        if candidate.is_file() and candidate.suffix in _MODULE_SUFFIXES:
            return candidate
    return None


def _coerce_option_value(value: str, value_type: OptionType) -> bool | int | str:
    """Coerce a raw CMake cache-entry string into project.option()'s declared type.

    Args:
        value: The cache entry's value, as CMake's File API reported it (a
            plain string, matching CMakeCache.txt's own storage format).
        value_type: The option's declared type.

    Returns:
        A bool for BOOL options (CMake's ON/TRUE/Y/YES/1-style truthy
        strings, case-insensitively), an int for INT options, or the raw
        string for STRING options.
    """
    if value_type is OptionType.BOOL:
        return value.strip().upper() in {"ON", "TRUE", "Y", "YES", "1"}
    if value_type is OptionType.INT:
        return int(value)
    return value


def _implicit_sanitize_preset_name(sanitizers: tuple[str, ...]) -> str:
    """Derive the implicit preset name for a --sanitize selection.

    Args:
        sanitizers: The sanitizer names from the CLI.

    Returns:
        A deterministic name like "sanitize-address-undefined".
    """
    return "sanitize-" + "-".join(sorted(set(sanitizers)))


def _with_implicit_sanitize_preset(model: ProjectModel) -> ProjectModel:
    """Add the preset 'cmakeless test --sanitize=...' asks for, if any.

    The override rides through the same preset machinery as user-defined
    presets, so the sanitized run gets its own build tree and the emitted
    files stay standalone.

    Args:
        model: The frozen but not yet validated project.

    Returns:
        The model, with the implicit preset appended when the sanitize
        override is active and no preset already has its name.
    """
    sanitizers = _context.active_sanitize()
    if not sanitizers:
        return model
    name = _implicit_sanitize_preset_name(sanitizers)
    if any(preset.name == name for preset in model.presets):
        return model
    implicit = PresetModel(name=name, optimize="none", sanitize=tuple(sorted(set(sanitizers))))
    return dataclasses.replace(model, presets=(*model.presets, implicit))


def _warn_unused_command_outputs(model: ProjectModel) -> None:
    """Print a soft notice for a command output nothing consumes.

    A print(), not a ConfigurationError: an output legitimately consumed
    only by external tooling (an IDE, a doc generator) outside any target's
    add_sources()/depends= is not a mistake CMakeless can tell apart from a
    real one, so this nudges without blocking.

    Args:
        model: The validated project model, subprojects included.
    """
    consumed = _consumed_paths(model)
    for command in model.commands:
        for output in command.outputs:
            if output not in consumed:
                print(
                    f"[cmakeless] Warning: add_command() output "
                    f"'{output.as_posix()}' in {model.source_script} is not "
                    f"consumed by any target's add_sources() or another "
                    f"command's/custom target's depends=. Wire it, or remove "
                    f"it if a tool outside CMakeless reads it."
                )
    for subproject in model.subprojects:
        _warn_unused_command_outputs(subproject.project)


def _warn_unknown_suffixes(model: ProjectModel) -> None:
    """Print a notice for a listed source no language compiles.

    A notice rather than an error: CMake itself accepts such files as
    non-compiled sources, so refusing them would break descriptions that
    already build, but a typo like "main.cp" deserves to be seen.

    Args:
        model: The validated project model, subprojects included.
    """
    generated = {output for command in model.commands for output in command.outputs}
    for target in model.all_targets():
        for source in target.sources:
            if source not in generated and not is_known_suffix(source):
                known = ", ".join(sorted(NON_COMPILED_SUFFIXES)[:6])
                print(
                    f"[cmakeless] Warning: '{source.as_posix()}' in target {target.name!r} "
                    f"({model.source_script}) has a suffix no enabled language compiles; it "
                    f"is listed but not built. Rename it (.cpp, .c, .S, .cu, .f90, ...) "
                    f"or drop it; headers and resources ({known}, ...) are fine."
                )
    for subproject in model.subprojects:
        _warn_unknown_suffixes(subproject.project)


def _consumed_paths(model: ProjectModel) -> set[Path]:
    """Collect every path a target's sources or a step's depends= names.

    Args:
        model: The project node to inspect (not recursive; subprojects are
            walked separately by the caller).

    Returns:
        Every source path and every command's/custom target's depends path.
    """
    consumed: set[Path] = set()
    for target in model.all_targets():
        consumed.update(target.sources)
    for command in model.commands:
        consumed.update(command.depends)
    for custom_target in model.custom_targets:
        consumed.update(custom_target.depends)
    return consumed


def _install_files_model(
    root: Path, paths: Sequence[str], destination: str, component: str | None, script: str
) -> InstallFilesModel:
    """Validate and freeze one install_files() call.

    Args:
        root: The project root the paths are relative to.
        paths: The paths as the user wrote them.
        destination: The install-prefix-relative destination.
        component: The CPack component, or None.
        script: The build description name, for messages.

    Returns:
        The frozen install rule; existence is checked on the model.

    Raises:
        ConfigurationError: When no path is given, or kinds are mixed.
    """
    if not paths:
        raise ConfigurationError(f"install_files() in {script} needs at least one path.")
    directories = {(root / path).is_dir() for path in paths}
    if len(directories) > 1:
        raise ConfigurationError(
            f"install_files({', '.join(repr(path) for path in paths)}) in {script} mixes "
            f"files and directories; use one call per kind."
        )
    return InstallFilesModel(
        paths=tuple(Path(path.rstrip("/")) for path in paths),
        destination=destination,
        component=component,
        directory=directories == {True},
        contents_only=all(path.endswith("/") for path in paths),
    )
