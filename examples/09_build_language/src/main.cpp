/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

#include <cstdlib>
#include <iostream>

#include "version.hpp"

auto main() -> int
{
    std::cout << "build_language_demo " << build_language_demo_version() << '\n';
#ifdef BUILD_LANGUAGE_VERBOSE
    std::cout << "(verbose diagnostics enabled)\n";
#endif
#ifdef BUILD_LANGUAGE_RELEASE_BUILD
    std::cout << "(optimized release build)\n";
#endif
#ifdef BUILD_LANGUAGE_WINDOWS
    std::cout << "(built for Windows)\n";
#endif
    return EXIT_SUCCESS;
}
