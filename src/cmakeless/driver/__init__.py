"""Layer 4: runs cmake as a subprocess and translates failures into exceptions.

Only this layer needs CMake installed; everything above it is pure Python.
"""

from cmakeless.driver.cmake_driver import CMakeDriver

__all__ = ["CMakeDriver"]
