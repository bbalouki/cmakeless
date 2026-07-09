# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Query any CMake variable, before a single line of CMake is emitted.

project.cmake_globals() runs a throwaway CMake configure immediately (never
a hand-written CMake-language parser) and hands back every variable that
configure defined. hasattr(cmake, name) mirrors CMake's if(DEFINED name),
not if(name): WIN32/APPLE/UNIX/ANDROID are only ever *set* by CMake on the
matching platform or toolchain, never defined-and-false elsewhere, so
hasattr() is exactly the right question to ask.

    $ python cmakelessfile.py   # probe, then build for the host
    $ cmakeless build           # the same, through the CLI

Because the probe runs at description time, its result can steer the rest
of the script, the way project.include()/include_module() already let a
reflected include steer target wiring.
"""

from cmakeless import Project

project = Project("cmake_globals_demo", version="1.0.0", cpp_std=20)

app = project.add_executable("cmake_globals_demo", sources=["src/main.cpp"])

cmake = project.cmake_globals()

if hasattr(cmake, "WIN32"):
    app.define("CMAKE_GLOBALS_DEMO_PLATFORM", '"Windows"')
elif hasattr(cmake, "APPLE"):
    app.define("CMAKE_GLOBALS_DEMO_PLATFORM", '"macOS"')
elif hasattr(cmake, "UNIX"):
    app.define("CMAKE_GLOBALS_DEMO_PLATFORM", '"Linux/Unix"')
else:
    app.define("CMAKE_GLOBALS_DEMO_PLATFORM", '"Unknown"')

print(f"[cmakelessfile] compiler: {cmake.CMAKE_CXX_COMPILER_ID}")
print(f"[cmakelessfile] hasattr(cmake, 'ANDROID'): {hasattr(cmake, 'ANDROID')}")

project.build()
