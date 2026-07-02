"""Layer 1: what the user touches.

Friendly, forgiving, mutable while the user is describing the build.
Project.build() is the boundary: it freezes everything into the immutable
model, validates, and only then proceeds.
"""

from cmakeless.api.project import Project
from cmakeless.api.targets import Executable

__all__ = ["Executable", "Project"]
