"""CMakeless: write your C++ builds in Python. Keep CMake. Lose the pain.

This module is the ONLY public import surface. Everything under
cmakeless.model, cmakeless.emitter, cmakeless.driver, and cmakeless.deps is
private machinery.
"""

from cmakeless._version import __version__
from cmakeless.api.dependencies import Dependency
from cmakeless.api.project import Project
from cmakeless.api.targets import Executable, Library
from cmakeless.errors import (
    CMakeError,
    CmakelessError,
    ConfigurationError,
    DependencyError,
    Diagnostic,
    ToolchainError,
)

__all__ = [
    "CMakeError",
    "CmakelessError",
    "ConfigurationError",
    "Dependency",
    "DependencyError",
    "Diagnostic",
    "Executable",
    "Library",
    "Project",
    "ToolchainError",
    "__version__",
]
