"""Layer 1: what the user touches.

Friendly, forgiving, mutable while the user is describing the build.
Project.build() is the boundary: it freezes everything into the immutable
model, validates, and only then proceeds.

This package re-exports every public class and function from its submodules,
so `from cmakeless.api import ...` reaches the whole layer-1 surface.
"""

from cmakeless.api.assets import SHADER_COMPILERS, ShaderArgv, shader_steps
from cmakeless.api.cache import Cache
from cmakeless.api.commands import Command, CustomTarget
from cmakeless.api.cpu import Cpu
from cmakeless.api.dependencies import Dependencies, Dependency
from cmakeless.api.extensions import (
    EXTENSION_ENTRY_POINT_GROUP,
    TEMPLATE_ENTRY_POINT_GROUP,
    TOOLCHAIN_ENTRY_POINT_GROUP,
    Extension,
    load_extension,
    register_extension,
)
from cmakeless.api.globals import CMakeGlobals
from cmakeless.api.modules import CMakeModule, check_file_reference, check_module_path
from cmakeless.api.options import Option
from cmakeless.api.presets import Preset
from cmakeless.api.profiles import Profile
from cmakeless.api.project import DEFAULT_BUILD_DIR_NAME, Project
from cmakeless.api.rules import Rules
from cmakeless.api.signing import MacSigning, Signing, WindowsSigning
from cmakeless.api.system import Imported, System, SystemLibrary
from cmakeless.api.targets import (
    Executable,
    Library,
    LibraryKindName,
    Linkable,
    PythonBindingName,
    PythonModule,
    Test,
    TestFrameworkName,
    WhenArgument,
)
from cmakeless.api.toolchains import Toolchain
from cmakeless.api.when import When
from cmakeless.api.workflows import WORKFLOW_VERBS, run_workflow
from cmakeless.api.workspace import WORKSPACE_SCRIPT_NAME, Workspace
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
    "EXTENSION_ENTRY_POINT_GROUP",
    "SHADER_COMPILERS",
    "TEMPLATE_ENTRY_POINT_GROUP",
    "TOOLCHAIN_ENTRY_POINT_GROUP",
    "WORKFLOW_VERBS",
    "WORKSPACE_SCRIPT_NAME",
    "BuildEvent",
    "CMakeGlobals",
    "CMakeModule",
    "Cache",
    "Command",
    "ConsoleObserver",
    "Cpu",
    "CustomTarget",
    "Dependencies",
    "Dependency",
    "Executable",
    "Extension",
    "Imported",
    "Library",
    "LibraryKindName",
    "Linkable",
    "MacSigning",
    "Observer",
    "Option",
    "Preset",
    "Profile",
    "Project",
    "PythonBindingName",
    "PythonModule",
    "Rules",
    "ShaderArgv",
    "Signing",
    "StepFailed",
    "StepFinished",
    "StepStarted",
    "System",
    "SystemLibrary",
    "Test",
    "TestFrameworkName",
    "Toolchain",
    "When",
    "WhenArgument",
    "WindowsSigning",
    "Workspace",
    "check_file_reference",
    "check_module_path",
    "load_extension",
    "register_extension",
    "run_workflow",
    "shader_steps",
]
