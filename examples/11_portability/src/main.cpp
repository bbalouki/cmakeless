#include <fmt/core.h>

auto main() -> int
{
    fmt::print("Hello from the portability example (fmt {})!\n", FMT_VERSION / 10000);
    return 0;
}
