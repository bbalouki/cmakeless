#include <fmt/core.h>

auto main() -> int
{
    fmt::print("Hello from {} {}!\n", "fmt", FMT_VERSION / 10000);
    return 0;
}
