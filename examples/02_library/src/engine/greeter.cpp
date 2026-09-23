#include "greeter.hpp"
#include "greeter_detail.hpp"

#include <format>

auto greeting(int player_count) -> std::string
{
    return std::format("Engine ready for {} of {} players.", player_count, detail::MAX_PLAYERS);
}
