#include "parser.hpp"

#include <limits>

namespace quality {

auto parse_count(std::string_view text) -> std::optional<int>
{
    constexpr int base = 10;
    if (text.empty()) {
        return std::nullopt;
    }
    int value = 0;
    for (const char digit : text) {
        if (digit < '0' || digit > '9') {
            return std::nullopt;
        }
        const int next = digit - '0';
        if (value > (std::numeric_limits<int>::max() - next) / base) {
            return std::nullopt;
        }
        value = value * base + next;
    }
    return value;
}

}  // namespace quality
