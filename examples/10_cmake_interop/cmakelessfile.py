# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""CMake reflection and introspection: include(), include_module(), cmake_info().

Shows the full interop-unlock surface: a small hand-written .cmake helper
reflected via project.include() (its function and variable discovered by
running real CMake, never a hand-written parser), a real built-in CMake
module reflected the same way via project.include_module(), and
project.cmake_info() reading the resolved generator, compiler, and system
back from CMake's File API after configure.

    $ python cmakelessfile.py   # build, then print what was discovered/resolved
    $ cmakeless build           # the same build through the CLI

Reflection needs CMake on PATH the moment project.include()/include_module()
is called, the one exception to "generating CMakeLists.txt never needs
CMake": there is no other honest way to know what a .cmake file defines
without running CMake on it.
"""

from cmakeless import Project

project = Project("cmake_interop_demo", version="1.0.0", cpp_std=20)

summary = project.include("cmake/print_build_summary.cmake")
print(f"[cmakelessfile] discovered functions: {summary.functions}")
print(f"[cmakelessfile] helper version: {summary.variable('CMAKE_INTEROP_HELPER_VERSION')}")
summary.call("print_build_summary", "cmake_interop_demo")

# A real built-in CMake module, reflected the same way as the local helper
# above: include_module() never needs a bundled list of "known" modules,
# because it asks CMake directly. check_cxx_compiler_flag() is a real
# compiler check, so calling it needs the working compiler this project
# already requires to build src/main.cpp.
compiler_checks = project.include_module("CheckCXXCompilerFlag")
compiler_checks.call("check_cxx_compiler_flag", "-Wall", "CMAKE_INTEROP_HAS_WALL")

project.add_executable("cmake_interop_demo", sources=["src/main.cpp"])

project.build()

info = project.cmake_info()
compilers = ", ".join(f"{c.language}={c.compiler_id} {c.compiler_version}" for c in info.compilers)
print(f"[cmakelessfile] generator: {info.generator} (multi-config: {info.multi_config})")
print(f"[cmakelessfile] compilers: {compilers}")
print(f"[cmakelessfile] system: {info.system_name} {info.system_processor}")
