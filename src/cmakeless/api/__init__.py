"""Layer 1: what the user touches.

Friendly, forgiving, mutable while the user is describing the build.
Project.build() is the boundary: it freezes everything into the immutable
model, validates, and only then proceeds.

This package re-exports every public class and function from its submodules,
so `from cmakeless.api import ...` reaches the whole layer-1 surface.
"""

from cmakeless.api.commands import Command, CustomTarget
from cmakeless.api.dependencies import Dependencies, Dependency
from cmakeless.api.globals import CMakeGlobals
from cmakeless.api.modules import CMakeModule, check_file_reference, check_module_path
from cmakeless.api.options import Option
from cmakeless.api.presets import Preset
from cmakeless.api.project import DEFAULT_BUILD_DIR_NAME, Project
from cmakeless.api.targets import (
    Executable,
    Library,
    LibraryKindName,
    PythonBindingName,
    PythonModule,
    Test,
    TestFrameworkName,
    WhenArgument,
)
from cmakeless.api.toolchains import Toolchain
from cmakeless.api.when import When
from cmakeless.observer import (
    BuildEvent,
    ConsoleObserver,
    Observer,
    StepFailed,
    StepFinished,
    StepStarted,
)

__all__ = [
    "DEFAULT_BUILD_DIR_NAME",
    "BuildEvent",
    "CMakeGlobals",
    "CMakeModule",
    "Command",
    "ConsoleObserver",
    "CustomTarget",
    "Dependencies",
    "Dependency",
    "Executable",
    "Library",
    "LibraryKindName",
    "Observer",
    "Option",
    "Preset",
    "Project",
    "PythonBindingName",
    "PythonModule",
    "StepFailed",
    "StepFinished",
    "StepStarted",
    "Test",
    "TestFrameworkName",
    "Toolchain",
    "When",
    "WhenArgument",
    "check_file_reference",
    "check_module_path",
]
