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
    """

    name: str
    sources: tuple[Path, ...]
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()


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
    """

    name: str
    kind: LibraryKind
    sources: tuple[Path, ...]
    public_include_dirs: tuple[Path, ...] = ()
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()


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
        dependencies: External packages this project's targets depend on.
        subprojects: Child projects composed into this one.
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
    dependencies: tuple[DependencyModel, ...] = ()
    subprojects: tuple[SubprojectModel, ...] = ()

    def targets(self) -> tuple[TargetModel, ...]:
        """Collect this project's own targets (not those of subprojects).

        Returns:
            Libraries first, then executables; otherwise unordered.
        """
        return (*self.libraries, *self.executables)
