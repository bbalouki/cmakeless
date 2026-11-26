"""Sanitizer names to per-compiler compile and link flag lines.

Flags are always emitted in compile/link pairs behind syntax-guarded
generator expressions, so the half-applied-sanitizer bug (compiled with
ASan, linked without) is not reproducible through this API. MSVC-syntax
compilers (cl and clang-cl) embed the runtime themselves, so they get a
compile flag only and never a GNU link flag their linker would reject. Two
flavors exist:

- Static lines for target.sanitize, active unconditionally.
- Preset lines guarded by the CMAKELESS_SANITIZE cache variable, so one
  generated CMakeLists serves every preset in CMakePresets.json.
"""

from __future__ import annotations

from collections.abc import Sequence

from cmakeless.emitter.flags import GNU_SYNTAX, MSVC_SYNTAX, flag_line, language_guard
from cmakeless.model.nodes import ProjectModel

# The cache variable presets use to switch sanitizers on; declared in the
# generated CMakeLists whenever any preset requests sanitizers.
SANITIZE_CACHE_VARIABLE = "CMAKELESS_SANITIZE"

# GCC/Clang flags by sanitizer name; applied to compile and link.
_GNU_FLAG_BY_SANITIZER: dict[str, str] = {
    "address": "-fsanitize=address",
    "undefined": "-fsanitize=undefined",
    "thread": "-fsanitize=thread",
    "leak": "-fsanitize=leak",
}

# AddressSanitizer stack traces are unreadable without frame pointers.
_FRAME_POINTER_FLAG = "-fno-omit-frame-pointer"

# The only sanitizer MSVC's cl driver supports; it links the runtime itself,
# so /fsanitize=address is a compile-only flag.
MSVC_SUPPORTED_SANITIZERS: frozenset[str] = frozenset({"address"})


def static_sanitize_lines(
    sanitize: tuple[str, ...], languages: Sequence[str] = ("CXX",)
) -> tuple[list[str], list[str]]:
    """Render a target's own sanitize list as unconditional guarded lines.

    Args:
        sanitize: The sanitizer names from target.sanitize, sorted.
        languages: The languages enabled in the project node.

    Returns:
        (compile option lines, link option lines), each wrapped in
        syntax generator expressions; both empty for no sanitizers.
    """
    if not sanitize:
        return ([], [])
    c_family = language_guard(languages)
    gnu_flags = [_GNU_FLAG_BY_SANITIZER[name] for name in sanitize]
    compile_flags = list(gnu_flags)
    if "address" in sanitize:
        compile_flags.append(_FRAME_POINTER_FLAG)
    compile_lines = [flag_line(compile_flags, GNU_SYNTAX, c_family)]
    if "address" in sanitize:
        compile_lines.append(flag_line(("/fsanitize=address",), MSVC_SYNTAX, c_family))
    link_lines = [flag_line(gnu_flags, GNU_SYNTAX)]
    return (compile_lines, link_lines)


def preset_sanitize_lines(
    union: tuple[str, ...], languages: Sequence[str] = ("CXX",)
) -> tuple[list[str], list[str]]:
    """Render preset-selectable sanitizers as cache-variable-guarded lines.

    Each sanitizer any preset requests gets its own lines, active only when
    the configuring preset lists it in CMAKELESS_SANITIZE.

    Args:
        union: Every sanitizer named by any preset, sorted.
        languages: The languages enabled in the project node.

    Returns:
        (compile option lines, link option lines); both empty when no
        preset requests sanitizers.
    """
    c_family = language_guard(languages)
    compile_lines: list[str] = []
    link_lines: list[str] = []
    for name in union:
        selected = f"$<IN_LIST:{name},${{{SANITIZE_CACHE_VARIABLE}}}>"
        compile_flags = [_GNU_FLAG_BY_SANITIZER[name]]
        if name == "address":
            compile_flags.append(_FRAME_POINTER_FLAG)
        compile_lines.append(flag_line(compile_flags, selected, GNU_SYNTAX, c_family))
        if name in MSVC_SUPPORTED_SANITIZERS:
            compile_lines.append(
                flag_line(("/fsanitize=address",), selected, MSVC_SYNTAX, c_family)
            )
        link_lines.append(flag_line((_GNU_FLAG_BY_SANITIZER[name],), selected, GNU_SYNTAX))
    return (compile_lines, link_lines)


def preset_sanitizer_union(model: ProjectModel) -> tuple[str, ...]:
    """Collect every sanitizer any of the project's presets requests.

    Args:
        model: The frozen project.

    Returns:
        The sanitizer names, deduplicated and sorted.
    """
    return tuple(sorted({name for preset in model.presets for name in preset.sanitize}))
