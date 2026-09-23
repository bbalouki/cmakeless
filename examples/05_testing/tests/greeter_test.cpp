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
