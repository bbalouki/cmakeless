"""Frozen dataclasses that form the build graph.

Immutability is what makes the downstream layers simple: the emitter can rely
on the model never changing under it, and threads can share it without locks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The C++ standards CMake's cxx_std_NN compile feature knows about.
SUPPORTED_CPP_STANDARDS: frozenset[int] = frozenset({11, 14, 17, 20, 23, 26})


@dataclass(frozen=True, slots=True)
class ExecutableModel:
    """A runnable target, fully resolved: sources are project-root-relative paths."""

    name: str
    sources: tuple[Path, ...]


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
    executables: tuple[ExecutableModel, ...]
