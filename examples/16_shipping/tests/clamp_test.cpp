#include <cstdlib>

#include "mathx/mathx.hpp"

auto main() -> int
{
    const bool ok = mathx::clamp(-5, 0, 10) == 0 && mathx::clamp(5, 0, 10) == 5
                    && mathx::clamp(50, 0, 10) == 10;
    return ok ? EXIT_SUCCESS : EXIT_FAILURE;
}
