"""Layer 1: what the user touches.

Friendly, forgiving, mutable while the user is describing the build.
Project.build() is the boundary: it freezes everything into the immutable
model, validates, and only then proceeds.

This package re-exports every public class and function from its submodules,
so `from cmakeless.api import ...` reaches the whole layer-1 surface.
"""

from cmakeless.api.dependencies import Dependencies, Dependency
from cmakeless.api.presets import Preset
from cmakeless.api.project import Project
from cmakeless.api.targets import Executable, Library, PythonModule, Test
from cmakeless.api.toolchains import Toolchain
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
    "ConsoleObserver",
    "Dependencies",
    "Dependency",
    "Executable",
    "Library",
    "Observer",
    "Preset",
    "Project",
    "PythonModule",
    "StepFailed",
    "StepFinished",
    "StepStarted",
    "Test",
    "Toolchain",
]
