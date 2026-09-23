#include <cstdlib>
#include <iostream>

#include "version_banner.hpp"

auto main() -> int
{
    std::cout << version_banner() << "\n";
    return EXIT_SUCCESS;
}
