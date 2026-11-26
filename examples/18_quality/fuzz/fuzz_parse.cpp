#include <cstddef>
#include <cstdint>
#include <string_view>

#include "parser.hpp"

// libFuzzer calls this with arbitrary bytes; any crash or sanitizer report is a bug.
extern "C" auto LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) -> int
{
    const std::string_view text(reinterpret_cast<const char*>(data), size);
    static_cast<void>(quality::parse_count(text));
    return 0;
}
