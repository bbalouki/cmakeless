#include "mathx/mathx.hpp"

namespace mathx {

auto clamp(int value, int low, int high) -> int
{
    if (value < low) {
        return low;
    }
    return value > high ? high : value;
}

}  // namespace mathx
