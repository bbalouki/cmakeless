#include <cstdlib>
#include <iostream>

#include "version.hpp"

auto main() -> int
{
    std::cout << "build_language_demo " << build_language_demo_version() << '\n';
#ifdef BUILD_LANGUAGE_VERBOSE
    std::cout << "(verbose diagnostics enabled)\n";
#endif
#ifdef BUILD_LANGUAGE_RELEASE_BUILD
    std::cout << "(optimized release build)\n";
#endif
    return EXIT_SUCCESS;
}
