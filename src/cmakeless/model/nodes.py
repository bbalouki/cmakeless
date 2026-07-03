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


@dataclass(frozen=True, slots=True)
class DefineModel:
    """A preprocessor definition.

    Attributes:
        name: The macro name, for example ``GAME_MAX_PLAYERS``.
        value: The macro value as a string, or None for a bare define.
    """

    name: str
    value: str | None = None


@dataclass(frozen=True, slots=True)
class CompileOptionsModel:
    """Extra compiler flags, optionally guarded to a set of compilers.

    Attributes:
        flags: The raw flags, in the order the user wrote them.
        compilers: Canonical compiler identifiers ("gnu", "clang",
            "appleclang", "msvc") the flags apply to; empty means all.
    """

    flags: tuple[str, ...]
    compilers: tuple[str, ...] = ()


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
        compile_options: Extra compiler flags, possibly compiler-guarded.
        links: Libraries this executable links against.
        sanitize: Sanitizer names applied to compile and link steps.
    """

    name: str
    sources: tuple[Path, ...]
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()
    sanitize: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LibraryModel:
    """A static, shared, or header-only library target.

    Attributes:
        name: Unique target name within the project.
        kind: How the library is built and consumed.
        sources: Project-root-relative source files; empty for header-only.
        public_include_dirs: Directories whose headers consumers may include.
        defines: Preprocessor definitions for this target.
        compile_options: Extra compiler flags, possibly compiler-guarded.
        links: Libraries this library links against.
        sanitize: Sanitizer names applied to compile and link steps.
    """

    name: str
    kind: LibraryKind
    sources: tuple[Path, ...]
    public_include_dirs: tuple[Path, ...] = ()
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()
    sanitize: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TestModel:
    """A test executable registered with CTest, fully resolved.

    Attributes:
        name: Unique target name within the project.
        sources: Project-root-relative source files, globs already expanded.
        framework: The test framework ("catch2", "gtest", "doctest", or
            "none" for a plain executable whose exit code is the verdict).
        defines: Preprocessor definitions for this target.
        compile_options: Extra compiler flags, possibly compiler-guarded.
        links: Libraries this test links against, framework included.
        sanitize: Sanitizer names applied to compile and link steps.
    """

    # Tell pytest this model is not a test case, despite the Test* name.
    __test__ = False

    name: str
    sources: tuple[Path, ...]
    framework: str = "none"
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()
    sanitize: tuple[str, ...] = ()


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
    """

    name: str
    optimize: str = "debug"
    sanitize: tuple[str, ...] = ()
    lto: bool = False
    toolchain: str | None = None


@dataclass(frozen=True, slots=True)
class ToolchainModel:
    """A compiler/platform description for cross or pinned builds.

    Either ``file`` points at an existing toolchain file (wrapped, never
    rewritten) or the generated fields describe a simple one CMakeless
    writes itself.

    Attributes:
        name: The toolchain name presets reference.
        file: Project-root-relative path of an existing toolchain file, or
            None when the toolchain is generated.
        compiler: The C++ compiler for a generated toolchain, or None.
        system_name: CMAKE_SYSTEM_NAME for a generated cross toolchain
            (for example "Linux"), or None for a host build.
        system_processor: CMAKE_SYSTEM_PROCESSOR for a generated cross
            toolchain (for example "aarch64"), or None.
    """

    name: str
    file: Path | None = None
    compiler: str | None = None
    system_name: str | None = None
    system_processor: str | None = None


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


type TargetModel = ExecutableModel | LibraryModel


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
        dependencies: External packages this project's targets depend on.
        subprojects: Child projects composed into this one.
        presets: Named configurations emitted into CMakePresets.json.
        toolchains: Registered toolchains presets may reference.
        installs: Install rules for this project's targets.
        package_formats: CPack formats project.package() requested.
        cache: True to wire ccache/sccache as the compiler launcher when
            one is found on PATH.
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
    dependencies: tuple[DependencyModel, ...] = ()
    subprojects: tuple[SubprojectModel, ...] = ()
    presets: tuple[PresetModel, ...] = ()
    toolchains: tuple[ToolchainModel, ...] = ()
    installs: tuple[InstallModel, ...] = ()
    package_formats: tuple[str, ...] = ()
    cache: bool = True

    def targets(self) -> tuple[TargetModel, ...]:
        """Collect this project's own compiled targets (tests excluded).

        Returns:
            Libraries first, then executables; otherwise unordered.
        """
        return (*self.libraries, *self.executables)

    def all_targets(self) -> tuple[TargetModel | TestModel, ...]:
        """Collect every target of this project, tests included.

        Returns:
            Libraries, then executables, then tests; otherwise unordered.
        """
        return (*self.libraries, *self.executables, *self.tests)
