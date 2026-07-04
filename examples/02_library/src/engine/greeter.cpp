/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

#include "greeter.hpp"
#include "greeter_detail.hpp"

#include <format>

auto greeting(int player_count) -> std::string
{
    return std::format("Engine ready for {} of {} players.", player_count, detail::MAX_PLAYERS);
}
