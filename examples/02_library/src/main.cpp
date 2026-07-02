#include <cstdlib>
#include <iostream>

#include "greeter.hpp"

auto main() -> int
{
    constexpr int PLAYER_COUNT{2};
    std::cout << greeting(PLAYER_COUNT) << '\n';
    return EXIT_SUCCESS;
}
