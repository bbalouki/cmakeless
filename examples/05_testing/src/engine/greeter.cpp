#include "greeter.hpp"

auto greeting(const std::string& name) -> std::string
{
    return "Hello, " + name + "!";
}
