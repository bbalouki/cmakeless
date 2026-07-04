# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Layer 2: the immutable, validated build graph.

Pure data. No CMake knowledge, no subprocess calls. The model is the single
source of truth that the emitter and driver consume.
"""

from cmakeless.model.nodes import (
    CommandModel,
    CompiledModel,
    CompileOptionsModel,
    CustomTargetModel,
    DefineModel,
    DependencyModel,
    ExecutableModel,
    InstallModel,
    LibraryKind,
    LibraryModel,
    LinkModel,
    LinkOptionsModel,
    ModuleCallModel,
    ModuleKind,
    ModuleModel,
    OptionModel,
    OptionType,
    PresetModel,
    ProjectModel,
    PythonModuleModel,
    SubprojectModel,
    TargetModel,
    TestModel,
    ToolchainModel,
    WhenKind,
    WhenModel,
)
from cmakeless.model.validate import validate_project

__all__ = [
    "CommandModel",
    "CompileOptionsModel",
    "CompiledModel",
    "CustomTargetModel",
    "DefineModel",
    "DependencyModel",
    "ExecutableModel",
    "InstallModel",
    "LibraryKind",
    "LibraryModel",
    "LinkModel",
    "LinkOptionsModel",
    "ModuleCallModel",
    "ModuleKind",
    "ModuleModel",
    "OptionModel",
    "OptionType",
    "PresetModel",
    "ProjectModel",
    "PythonModuleModel",
    "SubprojectModel",
    "TargetModel",
    "TestModel",
    "ToolchainModel",
    "WhenKind",
    "WhenModel",
    "validate_project",
]
