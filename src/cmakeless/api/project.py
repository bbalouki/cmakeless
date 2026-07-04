# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The Project facade: the root object users interact with.

project.build() hides freeze, validate, emit, configure, and compile behind
one verb.
"""

from __future__ import annotations

import dataclasses
import inspect
import runpy
import shutil
import sysconfig
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless._parallel import parallel_map
from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.api.commands import Command, CustomTarget
from cmakeless.api.dependencies import Dependencies
from cmakeless.api.options import Option
from cmakeless.api.presets import Preset
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
from cmakeless.deps import (
    LOCKFILE_NAME,
    DependencyProvider,
    collect_tree_dependencies,
    provider_for,
    read_lockfile,
    resolve_dependencies,
)
from cmakeless.driver import CMakeDriver, select_generator
from cmakeless.driver.file_api import TargetInfo
from cmakeless.emitter import emit_tree
from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import (
    BUILD_TYPE_BY_OPTIMIZE,
    InstallModel,
    PresetModel,
    ProjectModel,
    PythonModuleModel,
    SubprojectModel,
)
from cmakeless.model.validate import validate_project
from cmakeless.observer import ConsoleObserver, Observer

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
    ) -> None:
        """Start describing a project.

        Args:
            name: The CMake project name.
            version: The project version string, passed to CMake.
            cpp_std: The C++ standard every target compiles with.
            warnings: Warning preset ("strict", "default", or "none").
            root: Project root directory; defaults to the directory of the
                script that constructed the Project (usually cmakelessfile.py).
        """
        self._name = name
        self._version = version
        self._cpp_std = cpp_std
        self.warnings = warnings
        self.package_manager = "auto"
        self.cache = True
        self.optimize: str | None = None
        self.lto = False
        script = _calling_script()
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
        self._executables: list[Executable] = []
        self._libraries: list[Library] = []
        self._tests: list[Test] = []
        self._python_modules: list[PythonModule] = []
        self._presets: list[Preset] = []
        self._options: list[Option] = []
        self._toolchains: list[Toolchain] = []
        self._installs: list[tuple[str, bool]] = []
        self._package_formats: tuple[str, ...] = ()
        self._raw_cmake_files: list[str] = []
        self._subprojects: list[tuple[Path, Project]] = []
        self._commands: list[Command] = []
        self._custom_targets: list[CustomTarget] = []

    @property
    def name(self) -> str:
        """The CMake project name."""
        return self._name

    @property
    def root(self) -> Path:
        """Absolute path of the project root directory."""
        return self._root

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

    def add_executable(self, name: str, sources: Sequence[str]) -> Executable:
        """Declare a runnable target built from the given source files or globs.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns, project-root-relative.

        Returns:
            The mutable Executable builder, for further link()/define() calls.
        """
        executable = Executable(
            name, sources, script=self._source_script, dependencies=self._dependencies
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
    ) -> Library:
        """Declare a library target.

        Args:
            name: Unique target name within the project.
            sources: Source files or glob patterns; empty for header-only.
            public_headers: Directory (or directories) whose headers
                consumers may include.
            kind: "static", "shared", or "header_only".

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
            script=self._source_script,
            dependencies=self._dependencies,
        )
        self._libraries.append(library)
        return library

    def add_subproject(self, path: str | Path) -> Project:
        """Mount a self-contained child project at a directory under the root.

        The child directory must contain its own cmakelessfile.py describing
        exactly one Project; it is executed in description mode, so its own
        project.build() call registers the project instead of building.

        Args:
            path: Directory of the child project, relative to this root.

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
        self._subprojects.append((directory, child))
        return child

    def add_test(
        self,
        name: str,
        sources: Sequence[str],
        *,
        framework: TestFrameworkName = "gtest",
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
        if framework in _FRAMEWORK_SPECS:
            dependency = self._dependencies.add(_FRAMEWORK_SPECS[framework])
            test._dependency_links.append((dependency, False))
        self._tests.append(test)
        return test

    def add_python_module(
        self,
        name: str,
        sources: Sequence[str],
        *,
        binding: PythonBindingName = "pybind11",
        stubs: bool = True,
        install: bool = True,
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

        Returns:
            The mutable PythonModule builder, for further link()/define()
            calls.

        Raises:
            ConfigurationError: When ``binding`` is not a known backend.
        """
        module = PythonModule(
            name,
            sources,
            binding=binding,
            stubs=stubs,
            install=install,
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

    def install(self, target: Executable | Library, *, headers: bool = False) -> None:
        """Declare that a target ships: emitted as install and export rules.

        Installed libraries come with an export set and Config.cmake files,
        so other CMake users can find_package() this project.

        Args:
            target: An executable or library created by this project.
            headers: True to also install the target's public header
                directories.

        Raises:
            ConfigurationError: When ``target`` is not a target object.
        """
        if not isinstance(target, Executable | Library):
            raise ConfigurationError(
                f"project.install() in {self._source_script} needs a target "
                f"created by add_executable() or add_library(), got "
                f"{type(target).__name__}."
            )
        self._installs.append((target.name, headers))

    def package(self, *, formats: Sequence[str] = ("zip",)) -> None:
        """Request CPack packaging of everything install() declared.

        Args:
            formats: Package formats to produce: "zip", "tgz", "deb",
                or "rpm".
        """
        self._package_formats = tuple(formats)

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
        self._prepare().driver.configure()

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
        driver.configure()
        return driver.targets_info()

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
            provider.pre_configure(root_dir=self._root, build_dir=build_dir, build_type=build_type)
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
        driver.configure()
        driver.build()
        driver.test()

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
        elif verb == "test":
            self.test()
        elif verb in ("install", "package"):
            self._run_post_build_verb(verb)
        else:
            prepared = self._prepare()
            prepared.driver.configure()
            prepared.driver.build()
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
        driver.configure()
        driver.build()
        if verb == "install":
            driver.install(prefix=_context.active_prefix())
        else:
            driver.package()

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

    def _prepare(self) -> _Prepared:
        """Freeze, resolve, write outputs, and bind a driver to the result.

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
        build_dir = self._build_dir(preset)
        if provider is not None:
            build_type = self._resolve_build_type(model, preset)
            provider.pre_configure(root_dir=self._root, build_dir=build_dir, build_type=build_type)
        return _Prepared(self._driver(model, provider, preset=preset), model, build_dir)

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
            build/ for the default configuration, build/<preset> otherwise
            (matching the binaryDir emitted into CMakePresets.json).
        """
        if preset is None:
            return self._root / DEFAULT_BUILD_DIR_NAME
        return self._root / DEFAULT_BUILD_DIR_NAME / preset

    def _freeze_without_validation(self) -> ProjectModel:
        """Freeze this project and its subprojects without validating.

        Validation runs once, at the top of the tree, in freeze().

        Returns:
            The frozen but not yet validated ProjectModel.
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
            subprojects=tuple(
                SubprojectModel(directory=directory, project=child._freeze_without_validation())
                for directory, child in self._subprojects
            ),
            presets=tuple(preset._freeze() for preset in self._presets),
            options=tuple(option._freeze() for option in self._options),
            commands=tuple(command._freeze() for command in self._commands),
            custom_targets=tuple(target._freeze() for target in self._custom_targets),
            toolchains=tuple(toolchain._freeze() for toolchain in self._toolchains),
            installs=tuple(
                InstallModel(target=name, headers=headers) for name, headers in self._installs
            ),
            package_formats=self._package_formats,
            cache=self.cache,
            optimize=self.optimize,
            lto=self.lto,
            raw_cmake_files=tuple(Path(raw_file) for raw_file in self._raw_cmake_files),
        )

    def _resolved_model(self) -> ProjectModel:
        """Freeze, validate, and resolve dependencies into a complete model.

        Returns:
            The model with every dependency pin filled; resolution also
            refreshes cmakeless.lock when the tree has dependencies.
        """
        return resolve_dependencies(self.freeze(), lock_path=self._root / LOCKFILE_NAME)

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
            files.update(provider.manifest_files(model, read_lockfile(self._root / LOCKFILE_NAME)))
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
    ) -> CMakeDriver:
        """Build the driver for this project's source and build directories.

        Args:
            model: The resolved project model, presets included.
            provider: The dependency backend whose toolchain arguments the
                configure step needs, or None for a dependency-free tree.
            preset: The active preset name, or None for the default
                configuration.

        Returns:
            A CMakeDriver honoring the project's or CLI's generator choice,
            the preset's build directory, and the cache setting.
        """
        build_dir = self._build_dir(preset)
        build_type = self._resolve_build_type(model, preset)
        extra = (
            provider.toolchain_args(build_dir, build_type=build_type)
            if provider is not None
            else ()
        )
        return CMakeDriver(
            source_dir=self._root,
            build_dir=build_dir,
            generator=select_generator(self._generator or _context.active_generator()),
            extra_configure_args=extra,
            preset=preset,
            use_cache=self.cache,
            observers=self._observers,
        )


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


def _calling_script() -> Path | None:
    """Find the user's script (usually cmakelessfile.py) that invoked the cmakeless API.

    Walking the stack keeps Project's root defaulting to the directory of the
    build description, not the process working directory, so 'python
    somewhere/cmakelessfile.py' behaves identically to 'cmakeless build' run inside it.

    Returns:
        Absolute path of the first stack frame outside the cmakeless
        package, or None when every frame is internal (REPL, embedding).
    """
    package_root = Path(__file__).resolve().parent.parent
    for frame_info in inspect.stack():
        filename = frame_info.filename
        if not filename or filename.startswith("<"):
            continue
        candidate = Path(filename).resolve()
        if not candidate.is_relative_to(package_root):
            return candidate
    return None
