# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# A tiny, reusable CMake helper, included and reflected via project.include()
# rather than run directly: CMakeless discovers print_build_summary() and
# CMAKE_INTEROP_HELPER_VERSION by asking real CMake to run this file, never
# by parsing its text.

set(CMAKE_INTEROP_HELPER_VERSION "1.0")

function(print_build_summary target_name)
    message(STATUS "cmake_interop_demo: building '${target_name}' with helper v${CMAKE_INTEROP_HELPER_VERSION}")
endfunction()
