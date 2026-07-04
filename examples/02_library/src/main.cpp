/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

#include <cstdlib>
#include <iostream>

#include "greeter.hpp"

auto main() -> int
{
    constexpr int PLAYER_COUNT{2};
    std::cout << greeting(PLAYER_COUNT) << '\n';
    return EXIT_SUCCESS;
}
