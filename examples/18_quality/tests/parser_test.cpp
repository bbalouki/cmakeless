#include <cstdlib>

#include "parser.hpp"

auto main() -> int
{
    const bool ok = quality::parse_count("42") == 42 && !quality::parse_count("4x")
                    && !quality::parse_count("") && !quality::parse_count("99999999999");
    return ok ? EXIT_SUCCESS : EXIT_FAILURE;
}
