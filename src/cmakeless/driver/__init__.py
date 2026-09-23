"""Layer 4: runs cmake as a subprocess and translates failures into exceptions.

Only this layer needs CMake installed; everything above it is pure Python.

This package re-exports every public class and function from its submodules,
so `from cmakeless.driver import ...` reaches the whole layer-4 surface.
"""

from cmakeless.driver.cmake_driver import (
    COMPILE_COMMANDS_NAME,
    LOG_FILE_NAME,
    CMakeDriver,
    resolve_tool,
)
from cmakeless.driver.doctor import DoctorCheck, run_diagnostics
from cmakeless.driver.error_translation import extract_diagnostics
from cmakeless.driver.file_api import (
    CMakeInfo,
    CompilerInfo,
    TargetInfo,
    read_cmake_info,
    read_reply,
    write_query,
)
from cmakeless.driver.generators import (
    CXX_MODULES_FAMILIES,
    Generator,
    GeneratorFamily,
    known_generator_names,
    select_generator,
    supports_cxx_modules,
)
from cmakeless.driver.globals import probe_globals
from cmakeless.driver.reflection import ModuleReflection, reflect, reflect_work_dir

__all__ = [
    "COMPILE_COMMANDS_NAME",
    "CXX_MODULES_FAMILIES",
    "LOG_FILE_NAME",
    "CMakeDriver",
    "CMakeInfo",
    "CompilerInfo",
    "DoctorCheck",
    "Generator",
    "GeneratorFamily",
    "ModuleReflection",
    "TargetInfo",
    "extract_diagnostics",
    "known_generator_names",
    "probe_globals",
    "read_cmake_info",
    "read_reply",
    "reflect",
    "reflect_work_dir",
    "resolve_tool",
    "run_diagnostics",
    "select_generator",
    "supports_cxx_modules",
    "write_query",
]
