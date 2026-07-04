# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Layer 1: what the user touches.

Friendly, forgiving, mutable while the user is describing the build.
Project.build() is the boundary: it freezes everything into the immutable
model, validates, and only then proceeds.

This package re-exports every public class and function from its submodules,
so `from cmakeless.api import ...` reaches the whole layer-1 surface.
"""

from cmakeless.api.commands import Command, CustomTarget
from cmakeless.api.dependencies import Dependencies, Dependency
from cmakeless.api.options import Option
from cmakeless.api.presets import Preset
from cmakeless.api.project import Project
from cmakeless.api.targets import Executable, Library, PythonModule, Test
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
    "BuildEvent",
    "Command",
    "ConsoleObserver",
    "CustomTarget",
    "Dependencies",
    "Dependency",
    "Executable",
    "Library",
    "Observer",
    "Option",
    "Preset",
    "Project",
    "PythonModule",
    "StepFailed",
    "StepFinished",
    "StepStarted",
    "Test",
    "Toolchain",
    "When",
]
