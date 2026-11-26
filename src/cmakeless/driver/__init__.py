"""Layer 4: runs cmake as a subprocess and translates failures into exceptions.

Only this layer needs CMake installed; everything above it is pure Python.

This package re-exports every public class and function from its submodules,
so `from cmakeless.driver import ...` reaches the whole layer-4 surface.
"""

from cmakeless.driver.cmake_driver import (
    COMPILE_COMMANDS_NAME,
    LOG_FILE_NAME,
    BuildOptions,
    CMakeDriver,
    TestOptions,
    read_junit,
    resolve_tool,
    run_program,
)
from cmakeless.driver.doctor import DoctorCheck, run_diagnostics
from cmakeless.driver.error_translation import extract_diagnostics
from cmakeless.driver.file_api import (
    CMakeInfo,
    CompilerInfo,
    TargetDetail,
    TargetInfo,
    read_cmake_info,
    read_reply,
    read_target_details,
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
from cmakeless.driver.insight import (
    NINJA_LOG_NAME,
    HeaderCost,
    StepTime,
    chrome_trace,
    header_costs,
    read_ninja_log,
)
from cmakeless.driver.reflection import ModuleReflection, reflect, reflect_work_dir
from cmakeless.driver.sarif import Finding, parse_clang_tidy, to_sarif

__all__ = [
    "COMPILE_COMMANDS_NAME",
    "CXX_MODULES_FAMILIES",
    "LOG_FILE_NAME",
    "NINJA_LOG_NAME",
    "BuildOptions",
    "CMakeDriver",
    "CMakeInfo",
    "CompilerInfo",
    "DoctorCheck",
    "Finding",
    "Generator",
    "GeneratorFamily",
    "HeaderCost",
    "ModuleReflection",
    "StepTime",
    "TargetDetail",
    "TargetInfo",
    "TestOptions",
    "chrome_trace",
    "extract_diagnostics",
    "header_costs",
    "known_generator_names",
    "parse_clang_tidy",
    "probe_globals",
    "read_cmake_info",
    "read_junit",
    "read_ninja_log",
    "read_reply",
    "read_target_details",
    "reflect",
    "reflect_work_dir",
    "resolve_tool",
    "run_diagnostics",
    "run_program",
    "select_generator",
    "supports_cxx_modules",
    "to_sarif",
    "write_query",
]
