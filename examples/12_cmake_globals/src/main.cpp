/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

#include <cstdlib>
#include <iostream>

auto main() -> int
{
    std::cout << "Built for platform: " << CMAKE_GLOBALS_DEMO_PLATFORM << "\n";
    return EXIT_SUCCESS;
}
