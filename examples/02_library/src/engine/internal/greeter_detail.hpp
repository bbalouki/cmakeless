#pragma once

// Private to the engine library: shared by every engine .cpp file that
// needs the compiled-in player cap. Consumers of the engine never see this
// header (it lives outside public_headers=), only the target's own sources
// do, via engine.include_dirs("src/engine/internal").
namespace detail
{
constexpr int MAX_PLAYERS{GAME_MAX_PLAYERS};
}
