"""Layer 3: walks the model and generates idiomatic, modern CMake.

Deterministic by contract: same model in, same bytes out.

This package re-exports every public class and function from its submodules,
so `from cmakeless.emitter import ...` reaches the whole layer-3 surface.
"""

from cmakeless.emitter.cmake_emitter import emit_cmakelists, emit_tree
from cmakeless.emitter.presets_emitter import PRESETS_SCHEMA_VERSION, emit_presets
from cmakeless.emitter.sanitizers import (
    MSVC_SUPPORTED_SANITIZERS,
    SANITIZE_CACHE_VARIABLE,
    preset_sanitize_lines,
    preset_sanitizer_union,
    static_sanitize_lines,
)
from cmakeless.emitter.toolchain_emitter import emit_toolchain
from cmakeless.emitter.when_emitter import guarded, render_generator_expression

__all__ = [
    "MSVC_SUPPORTED_SANITIZERS",
    "PRESETS_SCHEMA_VERSION",
    "SANITIZE_CACHE_VARIABLE",
    "emit_cmakelists",
    "emit_presets",
    "emit_toolchain",
    "emit_tree",
    "guarded",
    "preset_sanitize_lines",
    "preset_sanitizer_union",
    "render_generator_expression",
    "static_sanitize_lines",
]
