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
    CPS_MINIMUM_VERSION,
    CXX_MODULES_MINIMUM_VERSION,
    MIN_PYTHON_VERSION,
)
from cmakeless._deprecation import deprecated, warn_deprecated_argument
from cmakeless._parallel import gil_enabled, parallel_map
from cmakeless._version import __version__
from cmakeless.api.cache import Cache
from cmakeless.api.commands import Command, CustomTarget
from cmakeless.api.cpu import Cpu
from cmakeless.api.dependencies import Dependencies, Dependency
from cmakeless.api.extensions import Extension, register_extension
from cmakeless.api.globals import CMakeGlobals
from cmakeless.api.modules import CMakeModule
from cmakeless.api.options import Option
from cmakeless.api.presets import Preset
from cmakeless.api.profiles import Profile
from cmakeless.api.project import Project
from cmakeless.api.rules import Rules
from cmakeless.api.signing import Signing
from cmakeless.api.system import Imported, System, SystemLibrary
from cmakeless.api.targets import Executable, Library, PythonModule, Test
from cmakeless.api.toolchains import Toolchain
from cmakeless.api.when import When
from cmakeless.api.workspace import WORKSPACE_SCRIPT_NAME, Workspace
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
    "CPS_MINIMUM_VERSION",
    "CXX_MODULES_MINIMUM_VERSION",
    "MIN_PYTHON_VERSION",
    "WORKSPACE_SCRIPT_NAME",
    "BuildEvent",
    "CMakeError",
    "CMakeGlobals",
    "CMakeInfo",
    "CMakeModule",
    "Cache",
    "CmakelessError",
    "Command",
    "CompilerInfo",
    "ConfigurationError",
    "ConsoleObserver",
    "Cpu",
    "CustomTarget",
    "Dependencies",
    "Dependency",
    "DependencyError",
    "Diagnostic",
    "Executable",
    "Extension",
    "Imported",
    "Library",
    "Observer",
    "Option",
    "Preset",
    "Profile",
    "Project",
    "PythonModule",
    "RegistryEntry",
    "Rules",
    "Signing",
    "StepFailed",
    "StepFinished",
    "StepStarted",
    "System",
    "SystemLibrary",
    "TargetInfo",
    "Test",
    "Toolchain",
    "ToolchainError",
    "When",
    "Workspace",
    "__version__",
    "deprecated",
    "gil_enabled",
    "parallel_map",
    "register_dependency",
    "register_extension",
    "warn_deprecated_argument",
]
