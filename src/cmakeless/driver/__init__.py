# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Layer 4: runs cmake as a subprocess and translates failures into exceptions.

Only this layer needs CMake installed; everything above it is pure Python.
"""

from cmakeless.driver.cmake_driver import CMakeDriver, resolve_tool
from cmakeless.driver.doctor import DoctorCheck, run_diagnostics
from cmakeless.driver.file_api import CMakeInfo, CompilerInfo, TargetInfo
from cmakeless.driver.generators import Generator, select_generator
from cmakeless.driver.reflection import ModuleReflection, reflect

__all__ = [
    "CMakeDriver",
    "CMakeInfo",
    "CompilerInfo",
    "DoctorCheck",
    "Generator",
    "ModuleReflection",
    "TargetInfo",
    "reflect",
    "resolve_tool",
    "run_diagnostics",
    "select_generator",
]
