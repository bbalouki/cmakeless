#include "greeter.hpp"

#include <format>

namespace
{
constexpr int MAX_PLAYERS{GAME_MAX_PLAYERS};
}

auto greeting(int player_count) -> std::string
{
    return std::format("Engine ready for {} of {} players.", player_count, MAX_PLAYERS);
}
