/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

#include <cstdlib>
#include <iostream>

#include "version_banner.hpp"

auto main() -> int
{
    std::cout << version_banner() << "\n";
    return EXIT_SUCCESS;
}
