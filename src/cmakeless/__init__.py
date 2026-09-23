"""CMakeless: write your C++ builds in Python. Keep CMake. Lose the pain.

This module is the ONLY public import surface. Everything under
cmakeless.model, cmakeless.emitter, cmakeless.driver, and cmakeless.deps is
private machinery.
"""

from cmakeless._constants import (
    BUILD_SCRIPT_NAME,
    CMAKE_MINIMUM_VERSION,
    CMAKELESS_SYSTEM_NAME_VAR,
    CMAKELESS_SYSTEM_PROCESSOR_VAR,
    CXX_MODULES_MINIMUM_VERSION,
    MIN_PYTHON_VERSION,
)
from cmakeless._deprecation import deprecated, warn_deprecated_argument
from cmakeless._parallel import gil_enabled, parallel_map
from cmakeless._version import __version__
from cmakeless.api.commands import Command, CustomTarget
from cmakeless.api.dependencies import Dependencies, Dependency
from cmakeless.api.globals import CMakeGlobals
from cmakeless.api.modules import CMakeModule
from cmakeless.api.options import Option
from cmakeless.api.presets import Preset
from cmakeless.api.project import Project
from cmakeless.api.targets import Executable, Library, PythonModule, Test
from cmakeless.api.toolchains import Toolchain
from cmakeless.api.when import When
from cmakeless.deps.registry import RegistryEntry
from cmakeless.deps.registry import register as register_dependency
from cmakeless.driver.file_api import CMakeInfo, CompilerInfo, TargetInfo
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
    "BUILD_SCRIPT_NAME",
    "CMAKELESS_SYSTEM_NAME_VAR",
    "CMAKELESS_SYSTEM_PROCESSOR_VAR",
    "CMAKE_MINIMUM_VERSION",
    "CXX_MODULES_MINIMUM_VERSION",
    "MIN_PYTHON_VERSION",
    "BuildEvent",
    "CMakeError",
    "CMakeGlobals",
    "CMakeInfo",
    "CMakeModule",
    "CmakelessError",
    "Command",
    "CompilerInfo",
    "ConfigurationError",
    "ConsoleObserver",
    "CustomTarget",
    "Dependencies",
    "Dependency",
    "DependencyError",
    "Diagnostic",
    "Executable",
    "Library",
    "Observer",
    "Option",
    "Preset",
    "Project",
    "PythonModule",
    "RegistryEntry",
    "StepFailed",
    "StepFinished",
    "StepStarted",
    "TargetInfo",
    "Test",
    "Toolchain",
    "ToolchainError",
    "When",
    "__version__",
    "deprecated",
    "gil_enabled",
    "parallel_map",
    "register_dependency",
    "warn_deprecated_argument",
]
