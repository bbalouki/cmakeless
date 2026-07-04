/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

#include <fmt/core.h>

auto main() -> int
{
    fmt::print("Hello from the portability example (fmt {})!\n", FMT_VERSION / 10000);
    return 0;
}
