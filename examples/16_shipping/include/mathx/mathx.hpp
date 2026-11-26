#pragma once

#include "mathx_export.h"

namespace mathx {

/// Clamps a value into [low, high]; exported, everything else stays hidden.
MATHX_EXPORT auto clamp(int value, int low, int high) -> int;

}  // namespace mathx
