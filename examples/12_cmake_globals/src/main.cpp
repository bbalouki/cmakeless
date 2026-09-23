#include <cstdlib>
#include <iostream>

auto main() -> int
{
    std::cout << "Built for platform: " << CMAKE_GLOBALS_DEMO_PLATFORM << "\n";
    return EXIT_SUCCESS;
}
