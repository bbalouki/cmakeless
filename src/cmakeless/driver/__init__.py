# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Layer 4: runs cmake as a subprocess and translates failures into exceptions.

Only this layer needs CMake installed; everything above it is pure Python.
"""

from cmakeless.driver.cmake_driver import CMakeDriver
from cmakeless.driver.file_api import TargetInfo
from cmakeless.driver.generators import Generator, select_generator

__all__ = ["CMakeDriver", "Generator", "TargetInfo", "select_generator"]
