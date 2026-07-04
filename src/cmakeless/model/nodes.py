# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Frozen dataclasses that form the build graph.

Immutability is what makes the downstream layers simple: the emitter can rely
on the model never changing under it, and threads can share it without locks.
The model knows the *concepts* of a build (targets, links, visibility) but no
CMake syntax; translating concepts to syntax is the emitter's job.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

from cmakeless._constants import MIN_PYTHON_VERSION

# The C++ standards CMake's cxx_std_NN compile feature knows about.
SUPPORTED_CPP_STANDARDS: frozenset[int] = frozenset({11, 14, 17, 20, 23, 26})

# The warning presets translated per compiler by the emitter.
WARNING_PRESETS: frozenset[str] = frozenset({"strict", "default", "none"})

# The dependency acquisition strategies a project can opt into. "auto" is the
# find_package-then-FetchContent fallback; the others delegate to one backend.
PACKAGE_MANAGERS: frozenset[str] = frozenset({"auto", "find_package", "vcpkg", "conan"})

# The test frameworks add_test() integrates automatically; "none" registers
# the test executable with CTest without any framework.
TEST_FRAMEWORKS: frozenset[str] = frozenset({"catch2", "gtest", "doctest", "none"})

# The Python binding backends add_python_module() can build against. Both
# provide a CMake <backend>_add_module command once fetched.
PYTHON_BINDING_BACKENDS: frozenset[str] = frozenset({"nanobind", "pybind11"})

# The sanitizers the emitter can translate into compile and link flags.
SANITIZERS: frozenset[str] = frozenset({"address", "undefined", "thread", "leak"})

# CMake build types by user-facing optimize level. "none" and "debug" are
# synonyms because both mean "no optimization, full debug information".
BUILD_TYPE_BY_OPTIMIZE: dict[str, str] = {
    "none": "Debug",
    "debug": "Debug",
    "release": "Release",
    "relwithdebinfo": "RelWithDebInfo",
    "minsize": "MinSizeRel",
}

# CPack generators by user-facing package format name.
CPACK_GENERATOR_BY_FORMAT: dict[str, str] = {
    "zip": "ZIP",
    "tgz": "TGZ",
    "deb": "DEB",
    "rpm": "RPM",
}

# Friendly compiler names accepted by When.compiler() (and the legacy
# when="gcc|clang" string sugar), mapped to canonical compiler identifiers.
COMPILERS_BY_TOKEN: dict[str, tuple[str, ...]] = {
    "gcc": ("gnu",),
    "clang": ("clang", "appleclang"),
    "appleclang": ("appleclang",),
    "msvc": ("msvc",),
}

# Canonical compiler identifiers (model vocabulary) to the CXX_COMPILER_ID
# values CMake's own generator expressions report.
CMAKE_COMPILER_ID_BY_CANONICAL: dict[str, str] = {
    "gnu": "GNU",
    "clang": "Clang",
    "appleclang": "AppleClang",
    "msvc": "MSVC",
}

# Friendly platform names accepted by When.platform(), mapped to the values
# CMake's $<PLATFORM_ID:...> generator expression reports.
CMAKE_PLATFORM_ID_BY_TOKEN: dict[str, str] = {
    "windows": "Windows",
    "linux": "Linux",
    "macos": "Darwin",
}


class LibraryKind(enum.Enum):
    """How a library target is built and consumed.

    Attributes:
        STATIC: Compiled into a static archive linked at build time.
        SHARED: Compiled into a shared library (DLL/so/dylib).
        HEADER_ONLY: No compiled artifact; consumers get headers and usage
            requirements only.
    """

    STATIC = "static"
    SHARED = "shared"
    HEADER_ONLY = "header_only"


class WhenKind(enum.Enum):
    """Which leaf or combinator one WhenModel node is.

    Attributes:
        PLATFORM: Matches one of a set of target platforms.
        COMPILER: Matches one of a set of compiler families.
        CONFIG: Matches one of a set of build configurations.
        OPTION: Matches a declared project option's value.
        AND: True only when every operand is true.
        OR: True when any operand is true.
        NOT: True when its single operand is false.
    """

    PLATFORM = "platform"
    COMPILER = "compiler"
    CONFIG = "config"
    OPTION = "option"
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass(frozen=True, slots=True)
class WhenModel:
    """A closed boolean-condition tree the emitter renders as CMake syntax.

    Built exclusively through When's factory classmethods and &, |, ~
    composition; never constructed with an arbitrary shape by user code.

    Attributes:
        kind: Which leaf or combinator this node is.
        names: Already-canonical CMake identifiers for PLATFORM/COMPILER
            (CMAKE_PLATFORM_ID_BY_TOKEN/CMAKE_COMPILER_ID_BY_CANONICAL
            values) or raw CMake config names for CONFIG; empty for OPTION
            and the combinators.
        option_name: The option this OPTION leaf tests; None otherwise.
        option_equals: The value the option must equal, for OPTION leaves.
        operands: Child conditions for AND/OR/NOT; empty for leaves.
    """

    kind: WhenKind
    names: tuple[str, ...] = ()
    option_name: str | None = None
    option_equals: bool | int | str = True
    operands: tuple[WhenModel, ...] = ()


@dataclass(frozen=True, slots=True)
class DefineModel:
    """A preprocessor definition.

    Attributes:
        name: The macro name, for example ``GAME_MAX_PLAYERS``.
        value: The macro value as a string, or None for a bare define.
        when: A condition guarding the define, or None to apply it
            unconditionally.
    """

    name: str
    value: str | None = None
    when: WhenModel | None = None


@dataclass(frozen=True, slots=True)
class CompileOptionsModel:
    """Extra compiler flags, optionally guarded by a condition.

    Attributes:
        flags: The raw flags, in the order the user wrote them.
        when: A condition guarding the flags, or None to apply them
            unconditionally.
    """

    flags: tuple[str, ...]
    when: WhenModel | None = None


@dataclass(frozen=True, slots=True)
class LinkOptionsModel:
    """Extra linker flags, optionally guarded by a condition.

    Attributes:
        flags: The raw flags, in the order the user wrote them.
        when: A condition guarding the flags, or None to apply them
            unconditionally.
    """

    flags: tuple[str, ...]
    when: WhenModel | None = None


@dataclass(frozen=True, slots=True)
class LinkModel:
    """An edge in the link graph, pointing at a library target by name.

    Attributes:
        target: Name of the linked library target; for external edges this
            is the imported target name (for example ``fmt::fmt``).
        public: True when consumers of the linking target also need the
            linked library (the linking target's headers expose it).
        external: True when the target comes from an external dependency
            rather than this project's own add_library() calls.
    """

    target: str
    public: bool = False
    external: bool = False


@dataclass(frozen=True, slots=True)
class DependencyModel:
    """One external package requirement, backend-agnostic.

    The API layer fills the metadata (cmake_name, link_targets) at freeze
    time; the resolver fills the fetch pin (url, sha256) from the lockfile,
    user overrides, the registry, or a one-time download-and-hash.

    Attributes:
        name: The package name, the part left of '/' in "fmt/10.2.1".
        version: The required version, the part right of '/'.
        components: Package components, for example Boost's "asio".
        cmake_name: The name find_package() knows the package by, or None
            until resolved.
        link_targets: The imported targets consumers link, for example
            ("fmt::fmt",); empty until known.
        url: Source archive URL for FetchContent, or None when the backend
            does not fetch sources.
        sha256: SHA256 pin of the source archive, or None when unpinned.
    """

    name: str
    version: str
    components: tuple[str, ...] = ()
    cmake_name: str | None = None
    link_targets: tuple[str, ...] = ()
    url: str | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutableModel:
    """A runnable target, fully resolved.

    Attributes:
        name: Unique target name within the project.
        sources: Project-root-relative source files, globs already expanded.
        defines: Preprocessor definitions for this target.
        compile_options: Extra compiler flags, possibly guarded by a When
            condition.
        link_options: Extra linker flags, possibly guarded by a When
            condition.
        links: Libraries this executable links against.
        sanitize: Sanitizer names applied to compile and link steps.
        raw_cmake: Verbatim CMake snippets emitted after the target is
            defined, in the order they were added (the escape hatch).
        private_include_dirs: Directories, private to this target, that its
            own sources may #include.
        cpp_std: This target's own C++ standard override, or None to use
            the project's.
        pch_headers: Headers to precompile, angle-bracket system headers
            (``<vector>``) verbatim and project-relative paths otherwise.
        unity: True to build this target as a single unity translation
            unit (UNITY_BUILD).
        clang_tidy: This target's own clang-tidy command (and extra
            arguments) to run as CXX_CLANG_TIDY, or None to inherit the
            project's project.lint() setting; a target that called
            target.lint() always has a concrete tuple (possibly empty, to
            opt out of the project default).
        iwyu: This target's own include-what-you-use command (and extra
            arguments) to run as CXX_INCLUDE_WHAT_YOU_USE, or None to
            inherit the project's project.lint() setting.
    """

    name: str
    sources: tuple[Path, ...]
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    link_options: tuple[LinkOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()
    sanitize: tuple[str, ...] = ()
    raw_cmake: tuple[str, ...] = ()
    private_include_dirs: tuple[Path, ...] = ()
    cpp_std: int | None = None
    pch_headers: tuple[str, ...] = ()
    unity: bool = False
    clang_tidy: tuple[str, ...] | None = None
    iwyu: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class LibraryModel:
    """A static, shared, or header-only library target.

    Attributes:
        name: Unique target name within the project.
        kind: How the library is built and consumed.
        sources: Project-root-relative source files; empty for header-only.
        public_include_dirs: Directories whose headers consumers may include.
        defines: Preprocessor definitions for this target.
        compile_options: Extra compiler flags, possibly guarded by a When
            condition.
        link_options: Extra linker flags, possibly guarded by a When
            condition.
        links: Libraries this library links against.
        sanitize: Sanitizer names applied to compile and link steps.
        raw_cmake: Verbatim CMake snippets emitted after the target is
            defined, in the order they were added (the escape hatch).
        private_include_dirs: Directories, private to this target, that its
            own sources may #include.
        cpp_std: This target's own C++ standard override, or None to use
            the project's.
        pch_headers: Headers to precompile, angle-bracket system headers
            (``<vector>``) verbatim and project-relative paths otherwise.
        unity: True to build this target as a single unity translation
            unit (UNITY_BUILD).
        clang_tidy: This target's own clang-tidy command (and extra
            arguments) to run as CXX_CLANG_TIDY, or None to inherit the
            project's project.lint() setting; a target that called
            target.lint() always has a concrete tuple (possibly empty, to
            opt out of the project default).
        iwyu: This target's own include-what-you-use command (and extra
            arguments) to run as CXX_INCLUDE_WHAT_YOU_USE, or None to
            inherit the project's project.lint() setting.
    """

    name: str
    kind: LibraryKind
    sources: tuple[Path, ...]
    public_include_dirs: tuple[Path, ...] = ()
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    link_options: tuple[LinkOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()
    sanitize: tuple[str, ...] = ()
    raw_cmake: tuple[str, ...] = ()
    private_include_dirs: tuple[Path, ...] = ()
    cpp_std: int | None = None
    pch_headers: tuple[str, ...] = ()
    unity: bool = False
    clang_tidy: tuple[str, ...] | None = None
    iwyu: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class TestModel:
    """A test executable registered with CTest, fully resolved.

    Attributes:
        name: Unique target name within the project.
        sources: Project-root-relative source files, globs already expanded.
        framework: The test framework ("catch2", "gtest", "doctest", or
            "none" for a plain executable whose exit code is the verdict).
        defines: Preprocessor definitions for this target.
        compile_options: Extra compiler flags, possibly guarded by a When
            condition.
        link_options: Extra linker flags, possibly guarded by a When
            condition.
        links: Libraries this test links against, framework included.
        sanitize: Sanitizer names applied to compile and link steps.
        raw_cmake: Verbatim CMake snippets emitted after the target is
            defined, in the order they were added (the escape hatch).
        private_include_dirs: Directories, private to this target, that its
            own sources may #include.
        cpp_std: This target's own C++ standard override, or None to use
            the project's.
        pch_headers: Headers to precompile, angle-bracket system headers
            (``<vector>``) verbatim and project-relative paths otherwise.
        unity: True to build this target as a single unity translation
            unit (UNITY_BUILD).
        clang_tidy: This target's own clang-tidy command, or None to
            inherit the project's project.lint() setting.
        iwyu: This target's own include-what-you-use command, or None to
            inherit the project's project.lint() setting.
    """

    # Tell pytest this model is not a test case, despite the Test* name.
    __test__ = False

    name: str
    sources: tuple[Path, ...]
    framework: str = "none"
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    link_options: tuple[LinkOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()
    sanitize: tuple[str, ...] = ()
    raw_cmake: tuple[str, ...] = ()
    private_include_dirs: tuple[Path, ...] = ()
    cpp_std: int | None = None
    pch_headers: tuple[str, ...] = ()
    unity: bool = False
    clang_tidy: tuple[str, ...] | None = None
    iwyu: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class PythonModuleModel:
    """A Python extension module built with nanobind or pybind11.

    The binding library is fetched like any dependency; the emitter drives
    it through the backend's own <backend>_add_module command rather than a
    plain add_library, which is why this is its own node kind.

    Attributes:
        name: The importable module name and CMake target name.
        sources: Project-root-relative source files, globs already expanded.
        binding: The binding backend ("pybind11" or "nanobind").
        stubs: True to generate a .pyi stub next to the module (nanobind
            only; pybind11 ships no CMake stub command).
        install_to_environment: True to copy the built module (and stub)
            into the invoking interpreter after build, so it imports at once.
        python_version: The minimum Python version find_package(Python ...)
            requires for this module, independent of whichever interpreter
            happens to run cmakeless, so the generated CMake is deterministic
            across machines.
        defines: Preprocessor definitions for this target.
        compile_options: Extra compiler flags, possibly guarded by a When
            condition.
        link_options: Extra linker flags, possibly guarded by a When
            condition.
        links: Libraries this module links against.
        sanitize: Sanitizer names applied to compile and link steps.
        raw_cmake: Verbatim CMake snippets emitted after the target is
            defined, in the order they were added (the escape hatch).
        private_include_dirs: Directories, private to this target, that its
            own sources may #include.
        cpp_std: This target's own C++ standard override, or None to use
            the project's.
        pch_headers: Headers to precompile, angle-bracket system headers
            (``<vector>``) verbatim and project-relative paths otherwise.
        unity: True to build this target as a single unity translation
            unit (UNITY_BUILD).
        clang_tidy: This target's own clang-tidy command, or None to
            inherit the project's project.lint() setting.
        iwyu: This target's own include-what-you-use command, or None to
            inherit the project's project.lint() setting.
    """

    name: str
    sources: tuple[Path, ...]
    binding: str = "pybind11"
    stubs: bool = True
    install_to_environment: bool = True
    python_version: str = MIN_PYTHON_VERSION
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    link_options: tuple[LinkOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()
    sanitize: tuple[str, ...] = ()
    raw_cmake: tuple[str, ...] = ()
    private_include_dirs: tuple[Path, ...] = ()
    cpp_std: int | None = None
    pch_headers: tuple[str, ...] = ()
    unity: bool = False
    clang_tidy: tuple[str, ...] | None = None
    iwyu: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class PresetModel:
    """One named configuration bundle mapped onto CMake presets.

    Attributes:
        name: The preset name shown by IDEs and passed to --preset.
        optimize: Optimization level ("none", "debug", "release",
            "relwithdebinfo", or "minsize").
        sanitize: Sanitizer names this preset applies to every target.
        lto: True to enable interprocedural optimization.
        toolchain: Name of a registered toolchain to configure with, or
            None for the host toolchain.
        options: Cache-variable overrides for this preset's declared
            project.option()s, as sorted (name, value) pairs.
        env: Environment variables for this preset's configure, build, and
            test steps, as sorted (name, value) pairs.
        inherits: Name of another preset this preset inherits unset
            settings from, or None.
    """

    name: str
    optimize: str = "debug"
    sanitize: tuple[str, ...] = ()
    lto: bool = False
    toolchain: str | None = None
    options: tuple[tuple[str, bool | int | str], ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    inherits: str | None = None


@dataclass(frozen=True, slots=True)
class ToolchainModel:
    """A compiler/platform description for cross or pinned builds.

    Either ``file`` points at an existing toolchain file (wrapped, never
    rewritten) or the generated fields describe a simple one CMakeless
    writes itself.

    Attributes:
        name: The toolchain name presets reference.
        file: Project-root-relative (or absolute) path of an existing
            toolchain file, or None when the toolchain is generated.
        compiler: The C++ compiler for a generated toolchain, or None.
        system_name: CMAKE_SYSTEM_NAME for a generated cross toolchain
            (for example "Linux"), or None for a host build.
        system_processor: CMAKE_SYSTEM_PROCESSOR for a generated cross
            toolchain (for example "aarch64"), or None.
        variables: Extra (name, value) cache-variable pairs seeded before
            compiler/system_name/processor and any wrapped ``file``'s
            include() (for example ANDROID_ABI, CMAKE_OSX_SYSROOT); empty
            for a plain generated or wrapped toolchain.
    """

    name: str
    file: Path | None = None
    compiler: str | None = None
    system_name: str | None = None
    system_processor: str | None = None
    variables: tuple[tuple[str, str], ...] = ()


class OptionType(enum.Enum):
    """The CMake cache-variable shape a project.option() declares.

    Attributes:
        BOOL: A plain option(), ON/OFF.
        INT: A CACHE STRING holding an integer.
        STRING: A CACHE STRING holding free text.
    """

    BOOL = "bool"
    INT = "int"
    STRING = "string"


@dataclass(frozen=True, slots=True)
class OptionModel:
    """A typed CMake cache variable declared by project.option().

    Attributes:
        name: The CMake cache-variable name.
        default: The default value, matching value_type.
        value_type: BOOL (emitted as option()), INT, or STRING (both
            emitted as set(... CACHE ...)).
        help: The cache-variable help string shown by cmake-gui/ccmake and
            the 'cmakeless options' verb.
    """

    name: str
    default: bool | int | str
    value_type: OptionType = OptionType.BOOL
    help: str = ""


@dataclass(frozen=True, slots=True)
class InstallModel:
    """One install rule: ship a target (and optionally its headers).

    Attributes:
        target: Name of the executable or library target to install.
        headers: True to also install the target's public header
            directories.
    """

    target: str
    headers: bool = False


@dataclass(frozen=True, slots=True)
class CommandModel:
    """A build-time step that produces files other targets/commands consume.

    Attributes:
        outputs: Project-root-relative paths this command produces.
        command: The argument vector to run (never a shell string).
        depends: Project-root-relative paths that trigger a re-run when
            changed; includes both plain files and other commands' outputs.
        comment: Shown by the generator while the command runs, or None.
    """

    outputs: tuple[Path, ...]
    command: tuple[str, ...]
    depends: tuple[Path, ...] = ()
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class CustomTargetModel:
    """An always-runnable target with no file output.

    Attributes:
        name: The CMake target name.
        command: The argument vector to run.
        depends: Project-root-relative paths (or other commands' outputs)
            that must be up to date first.
    """

    name: str
    command: tuple[str, ...]
    depends: tuple[Path, ...] = ()


class ModuleKind(enum.Enum):
    """Which form a project.include()/include_module() call takes.

    Attributes:
        FILE: A project-relative .cmake file, included by path.
        NAMED: A bare module name, included by CMake's own module lookup.
    """

    FILE = "file"
    NAMED = "named"


@dataclass(frozen=True, slots=True)
class ModuleCallModel:
    """One validated call to a function or macro a reflected include defined.

    Attributes:
        function: The function or macro name, exactly as CMake reported it.
        args: Positional arguments, in call order.
    """

    function: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModuleModel:
    """A project.include()/include_module() call, reflection already resolved.

    Reflection (discovering functions, variables, and targets by running
    real CMake) happens eagerly in the API layer, since mod.call(...) must
    validate immediately; this node only carries what was already validated.

    Attributes:
        kind: FILE (a path) or NAMED (a bare module name).
        reference: Project-root-relative path, POSIX-normalized (FILE), or
            the bare module name exactly as given (NAMED).
        module_path: Project-root-relative extra CMAKE_MODULE_PATH entry for
            NAMED includes, or None.
        calls: Validated mod.call(...) invocations, in declaration order.
            Never sorted, unlike commands/custom_targets: CMake function
            calls can have order-dependent side effects.
    """

    kind: ModuleKind
    reference: str
    module_path: Path | None = None
    calls: tuple[ModuleCallModel, ...] = ()


type TargetModel = ExecutableModel | LibraryModel

# Every node the emitter compiles and settings blocks apply to, sharing the
# name/sources/defines/compile_options/links/sanitize shape.
type CompiledModel = ExecutableModel | LibraryModel | TestModel | PythonModuleModel


@dataclass(frozen=True, slots=True)
class SubprojectModel:
    """A child project mounted at a directory relative to its parent's root.

    Attributes:
        directory: Parent-root-relative directory the child lives in.
        project: The child's own frozen build graph.
    """

    directory: Path
    project: ProjectModel


@dataclass(frozen=True, slots=True)
class ProjectModel:
    """The root of the frozen build graph.

    Attributes:
        name: The CMake project name.
        version: The project version string (semver-ish, passed to CMake).
        cpp_std: The C++ standard every target compiles with.
        root_dir: Absolute path to the project root on disk.
        source_script: Display name of the build description that produced
            this model, for the self-describing header comment in generated
            files.
        warnings: Warning preset name ("strict", "default", or "none").
        package_manager: Dependency strategy name ("auto", "find_package",
            "vcpkg", or "conan").
        executables: All executable targets of this project.
        libraries: All library targets of this project.
        tests: All test targets of this project.
        python_modules: All Python extension modules of this project.
        dependencies: External packages this project's targets depend on.
        subprojects: Child projects composed into this one.
        presets: Named configurations emitted into CMakePresets.json.
        toolchains: Registered toolchains presets may reference.
        installs: Install rules for this project's targets.
        options: Typed CMake cache variables declared by project.option().
        commands: Build-time steps declared by project.add_command().
        custom_targets: Always-runnable targets declared by
            project.add_custom_target().
        modules: Reflected includes declared by project.include()/
            include_module().
        package_formats: CPack formats project.package() requested.
        cache: True to wire ccache/sccache as the compiler launcher when
            one is found on PATH.
        optimize: Optimization level applied to the default (no-preset)
            build ("none", "debug", "release", "relwithdebinfo", or
            "minsize"), or None to leave the build type unset. An active
            preset always overrides it.
        lto: True to enable interprocedural optimization on the default
            build; a preset's own setting wins when one is active.
        raw_cmake_files: Extra CMake files include()d at the top of the
            generated CMakeLists.txt, in the order they were added.
        lint_clang_tidy: The project-wide clang-tidy command (and extra
            arguments) project.lint() declared, applied to every compiled
            target that has not called its own target.lint(); empty means
            clang-tidy is off by default.
        lint_iwyu: The project-wide include-what-you-use command declared
            by project.lint(), same inheritance rule as lint_clang_tidy.
    """

    name: str
    version: str
    cpp_std: int
    root_dir: Path
    source_script: str
    warnings: str = "default"
    package_manager: str = "auto"
    executables: tuple[ExecutableModel, ...] = ()
    libraries: tuple[LibraryModel, ...] = ()
    tests: tuple[TestModel, ...] = ()
    python_modules: tuple[PythonModuleModel, ...] = ()
    dependencies: tuple[DependencyModel, ...] = ()
    subprojects: tuple[SubprojectModel, ...] = ()
    presets: tuple[PresetModel, ...] = ()
    toolchains: tuple[ToolchainModel, ...] = ()
    installs: tuple[InstallModel, ...] = ()
    options: tuple[OptionModel, ...] = ()
    commands: tuple[CommandModel, ...] = ()
    custom_targets: tuple[CustomTargetModel, ...] = ()
    modules: tuple[ModuleModel, ...] = ()
    package_formats: tuple[str, ...] = ()
    cache: bool = True
    optimize: str | None = None
    lto: bool = False
    raw_cmake_files: tuple[Path, ...] = ()
    lint_clang_tidy: tuple[str, ...] = ()
    lint_iwyu: tuple[str, ...] = ()

    def targets(self) -> tuple[TargetModel, ...]:
        """Collect this project's own compiled targets (tests excluded).

        Returns:
            Libraries first, then executables; otherwise unordered.
        """
        return (*self.libraries, *self.executables)

    def all_targets(self) -> tuple[CompiledModel, ...]:
        """Collect every compiled target of this project, tests included.

        Returns:
            Libraries, executables, tests, then Python modules; otherwise
            unordered.
        """
        return (*self.libraries, *self.executables, *self.tests, *self.python_modules)
