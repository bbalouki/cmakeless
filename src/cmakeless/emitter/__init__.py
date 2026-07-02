"""Layer 3: walks the model and generates idiomatic, modern CMake.

Deterministic by contract: same model in, same bytes out.
"""

from cmakeless.emitter.cmake_emitter import emit_cmakelists

__all__ = ["emit_cmakelists"]
