# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""CMakeless: write your C++ builds in Python. Keep CMake. Lose the pain.

This module is the ONLY public import surface. Everything under
cmakeless.model, cmakeless.emitter, cmakeless.driver, and cmakeless.deps is
private machinery.
"""

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
    "register_dependency",
]
