"""Layer 2: the immutable, validated build graph.

Pure data. No CMake knowledge, no subprocess calls. The model is the single
source of truth that the emitter and driver consume.
"""

from cmakeless.model.nodes import (
    DependencyModel,
    ExecutableModel,
    LibraryKind,
    LibraryModel,
    ProjectModel,
    SubprojectModel,
)
from cmakeless.model.validate import validate_project

__all__ = [
    "DependencyModel",
    "ExecutableModel",
    "LibraryKind",
    "LibraryModel",
    "ProjectModel",
    "SubprojectModel",
    "validate_project",
]
