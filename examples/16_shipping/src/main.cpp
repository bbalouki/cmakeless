#include <cstdlib>
#include <iostream>

#include "mathx/mathx.hpp"

auto main() -> int
{
    std::cout << "clamp(42, 0, 10) = " << mathx::clamp(42, 0, 10) << '\n';
    return EXIT_SUCCESS;
}
