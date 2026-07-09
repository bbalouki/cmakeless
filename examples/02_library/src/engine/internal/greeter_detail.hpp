/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

#pragma once

// Private to the engine library: shared by every engine .cpp file that
// needs the compiled-in player cap. Consumers of the engine never see this
// header (it lives outside public_headers=), only the target's own sources
// do, via engine.include_dirs("src/engine/internal").
namespace detail
{
constexpr int MAX_PLAYERS{GAME_MAX_PLAYERS};
}
