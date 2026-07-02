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
        target: Name of the linked library target.
        public: True when consumers of the linking target also need the
            linked library (the linking target's headers expose it).
    """

    target: str
    public: bool = False


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
        executables: All executable targets of this project.
        libraries: All library targets of this project.
        subprojects: Child projects composed into this one.
    """

    name: str
    version: str
    cpp_std: int
    root_dir: Path
    source_script: str
    warnings: str = "default"
    executables: tuple[ExecutableModel, ...] = ()
    libraries: tuple[LibraryModel, ...] = ()
    subprojects: tuple[SubprojectModel, ...] = ()

    def targets(self) -> tuple[TargetModel, ...]:
        """Collect this project's own targets (not those of subprojects).

        Returns:
            Libraries first, then executables; otherwise unordered.
        """
        return (*self.libraries, *self.executables)
