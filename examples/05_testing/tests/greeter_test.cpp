/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

#include <catch2/catch_test_macros.hpp>

#include "greeter.hpp"

TEST_CASE("greeting addresses the given name")
{
    REQUIRE(greeting("world") == "Hello, world!");
}

TEST_CASE("greeting handles an empty name")
{
    REQUIRE(greeting("") == "Hello, !");
}
