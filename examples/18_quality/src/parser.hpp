#pragma once

#include <optional>
#include <string_view>

namespace quality {

/// Parses a non-negative decimal integer; returns nothing on any other input.
auto parse_count(std::string_view text) -> std::optional<int>;

}  // namespace quality
