"""CMakeless: write your C++ builds in Python. Keep CMake. Lose the pain.

This module is the ONLY public import surface. Everything under
cmakeless.model, cmakeless.emitter, cmakeless.driver, and cmakeless.deps is
private machinery.
"""

from cmakeless._version import __version__
from cmakeless.api.dependencies import Dependency
from cmakeless.api.presets import Preset
from cmakeless.api.project import Project
from cmakeless.api.targets import Executable, Library, PythonModule, Test
from cmakeless.api.toolchains import Toolchain
from cmakeless.driver.file_api import TargetInfo
from cmakeless.errors import (
    CMakeError,
    CmakelessError,
    ConfigurationError,
    DependencyError,
    Diagnostic,
    ToolchainError,
)
from cmakeless.observer import (
    BuildEvent,
    ConsoleObserver,
    Observer,
    StepFailed,
    StepFinished,
    StepStarted,
)

__all__ = [
    "BuildEvent",
    "CMakeError",
    "CmakelessError",
    "ConfigurationError",
    "ConsoleObserver",
    "Dependency",
    "DependencyError",
    "Diagnostic",
    "Executable",
    "Library",
    "Observer",
    "Preset",
    "Project",
    "PythonModule",
    "StepFailed",
    "StepFinished",
    "StepStarted",
    "TargetInfo",
    "Test",
    "Toolchain",
    "ToolchainError",
    "__version__",
]
