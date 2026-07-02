"""Frozen dataclasses that form the build graph.

Immutability is what makes the downstream layers simple: the emitter can rely
on the model never changing under it, and threads can share it without locks.
The model knows the *concepts* of a build (targets, links, visibility) but no
CMake syntax; translating concepts to syntax is the emitter's job.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path

# The C++ standards CMake's cxx_std_NN compile feature knows about.
SUPPORTED_CPP_STANDARDS: frozenset[int] = frozenset({11, 14, 17, 20, 23, 26})

# The warning presets translated per compiler by the emitter.
WARNING_PRESETS: frozenset[str] = frozenset({"strict", "default", "none"})


class LibraryKind(enum.Enum):
    STATIC = "static"
    SHARED = "shared"
    HEADER_ONLY = "header_only"


@dataclass(frozen=True, slots=True)
class DefineModel:
    """A preprocessor definition; value None means a bare define."""

    name: str
    value: str | None = None


@dataclass(frozen=True, slots=True)
class CompileOptionsModel:
    """Extra compiler flags, optionally guarded to a set of compilers.

    The compilers tuple holds canonical compiler identifiers ("gnu", "clang",
    "appleclang", "msvc"); empty means the flags apply everywhere.
    """

    flags: tuple[str, ...]
    compilers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LinkModel:
    """An edge in the link graph, pointing at a library target by name."""

    target: str
    public: bool = False


@dataclass(frozen=True, slots=True)
class ExecutableModel:
    """A runnable target, fully resolved: sources are project-root-relative paths."""

    name: str
    sources: tuple[Path, ...]
    defines: tuple[DefineModel, ...] = ()
    compile_options: tuple[CompileOptionsModel, ...] = ()
    links: tuple[LinkModel, ...] = ()


@dataclass(frozen=True, slots=True)
class LibraryModel:
    """A static, shared, or header-only library target."""

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
    """A child project mounted at a directory relative to its parent's root."""

    directory: Path
    project: ProjectModel


@dataclass(frozen=True, slots=True)
class ProjectModel:
    """The root of the frozen build graph."""

    name: str
    version: str
    cpp_std: int
    root_dir: Path
    # Display name of the build description that produced this model, for the
    # self-describing header comment in generated files.
    source_script: str
    warnings: str = "default"
    executables: tuple[ExecutableModel, ...] = ()
    libraries: tuple[LibraryModel, ...] = ()
    subprojects: tuple[SubprojectModel, ...] = field(default=())

    def targets(self) -> tuple[TargetModel, ...]:
        """All targets of this project (not of subprojects), unordered."""
        return (*self.libraries, *self.executables)
