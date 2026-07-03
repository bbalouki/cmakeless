// A tiny CLI over the stats library: pass numbers, get a summary line.
//
//     $ ./stats_cli 3 1 4 1 5 9 2 6
//     n=8 mean=3.875 stddev=2.571 min=1.000 median=3.500 max=9.000
#include <charconv>
#include <cstdlib>
#include <span>
#include <string_view>
#include <vector>

#include <fmt/core.h>

#include "stats/series.hpp"

namespace {

[[nodiscard]] auto parse_samples(std::span<char*> arguments) -> std::vector<double>
{
    std::vector<double> samples;
    samples.reserve(arguments.size());
    for (const std::string_view argument : arguments)
    {
        double value{};
        const auto* end{argument.data() + argument.size()};
        const auto [parsed, error]{std::from_chars(argument.data(), end, value)};
        if (error != std::errc{} || parsed != end)
        {
            fmt::print(stderr, "skipping non-numeric argument: {}\n", argument);
            continue;
        }
        samples.push_back(value);
    }
    return samples;
}

} // namespace

auto main(int argc, char** argv) -> int
{
    const std::span<char*> arguments{argv + 1, static_cast<std::size_t>(argc - 1)};
    const std::vector<double> samples{parse_samples(arguments)};
    if (samples.empty())
    {
        fmt::print(stderr, "usage: stats_cli <number> [number ...]\n");
        return EXIT_FAILURE;
    }
    const stats::Series series{samples};
    fmt::print("{}\n", series.summary());
    return EXIT_SUCCESS;
}
