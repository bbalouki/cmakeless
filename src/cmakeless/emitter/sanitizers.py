# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Sanitizer names to per-compiler compile and link flag lines.

Flags are always emitted in compile/link pairs behind compiler-id generator
expressions, so the half-applied-sanitizer bug (compiled with ASan, linked
without) is not reproducible through this API. Two flavors exist:

- Static lines for target.sanitize, active unconditionally.
- Preset lines guarded by the CMAKELESS_SANITIZE cache variable, so one
  generated CMakeLists serves every preset in CMakePresets.json.
"""

from __future__ import annotations

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

_NOT_MSVC = "$<NOT:$<CXX_COMPILER_ID:MSVC>>"
_MSVC = "$<CXX_COMPILER_ID:MSVC>"


def static_sanitize_lines(sanitize: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Render a target's own sanitize list as unconditional guarded lines.

    Args:
        sanitize: The sanitizer names from target.sanitize, sorted.

    Returns:
        (compile option lines, link option lines), each wrapped in
        compiler-id generator expressions; both empty for no sanitizers.
    """
    if not sanitize:
        return ([], [])
    gnu_flags = [_GNU_FLAG_BY_SANITIZER[name] for name in sanitize]
    compile_flags = list(gnu_flags)
    if "address" in sanitize:
        compile_flags.append(_FRAME_POINTER_FLAG)
    compile_lines = [f"$<{_NOT_MSVC}:{';'.join(compile_flags)}>"]
    if "address" in sanitize:
        compile_lines.append(f"$<{_MSVC}:/fsanitize=address>")
    link_lines = [f"$<{_NOT_MSVC}:{';'.join(gnu_flags)}>"]
    return (compile_lines, link_lines)


def preset_sanitize_lines(union: tuple[str, ...]) -> tuple[list[str], list[str]]:
    """Render preset-selectable sanitizers as cache-variable-guarded lines.

    Each sanitizer any preset requests gets its own lines, active only when
    the configuring preset lists it in CMAKELESS_SANITIZE.

    Args:
        union: Every sanitizer named by any preset, sorted.

    Returns:
        (compile option lines, link option lines); both empty when no
        preset requests sanitizers.
    """
    compile_lines: list[str] = []
    link_lines: list[str] = []
    for name in union:
        selected = f"$<IN_LIST:{name},${{{SANITIZE_CACHE_VARIABLE}}}>"
        compile_flags = _GNU_FLAG_BY_SANITIZER[name]
        if name == "address":
            compile_flags = f"{compile_flags};{_FRAME_POINTER_FLAG}"
        compile_lines.append(f"$<$<AND:{selected},{_NOT_MSVC}>:{compile_flags}>")
        if name in MSVC_SUPPORTED_SANITIZERS:
            compile_lines.append(f"$<$<AND:{selected},{_MSVC}>:/fsanitize=address>")
        link_lines.append(f"$<$<AND:{selected},{_NOT_MSVC}>:{_GNU_FLAG_BY_SANITIZER[name]}>")
    return (compile_lines, link_lines)


def preset_sanitizer_union(model: ProjectModel) -> tuple[str, ...]:
    """Collect every sanitizer any of the project's presets requests.

    Args:
        model: The frozen project.

    Returns:
        The sanitizer names, deduplicated and sorted.
    """
    return tuple(sorted({name for preset in model.presets for name in preset.sanitize}))
