"""Layer 3: walks the model and generates idiomatic, modern CMake.

Deterministic by contract: same model in, same bytes out.
"""

from cmakeless.emitter.cmake_emitter import emit_cmakelists, emit_tree
from cmakeless.emitter.presets_emitter import emit_presets
from cmakeless.emitter.toolchain_emitter import emit_toolchain

__all__ = ["emit_cmakelists", "emit_presets", "emit_toolchain", "emit_tree"]
