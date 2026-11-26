"""Per-compiler flag tables, keyed by command-line syntax and linker family.

Flag *syntax* follows the compiler frontend, not the compiler id: clang-cl
reports CXX_COMPILER_ID=Clang yet speaks cl's command line, so keying on the
id alone hands it GNU flags (and its -Wall means -Weverything). Linker flags
follow the platform's linker instead, since the frontend does not decide
which linker runs, and they go through CMake's LINKER: prefix so the right
pass-through spelling (-Wl, or -Xlinker) is chosen per compiler.
"""

from __future__ import annotations

from collections.abc import Sequence

from cmakeless.model.properties import CpuFamily, CpuModel, FlagSetModel, ProfileModel

# Variables the syntax preamble defines; every flag line below refers to
# them instead of repeating the full generator expression.
MSVC_SYNTAX_VARIABLE = "CMAKELESS_MSVC_SYNTAX"
MSVC_LINKER_VARIABLE = "CMAKELESS_MSVC_LINKER"
APPLE_LINKER_VARIABLE = "CMAKELESS_APPLE_LINKER"
X86_VARIABLE = "CMAKELESS_X86"

MSVC_SYNTAX = f"${{{MSVC_SYNTAX_VARIABLE}}}"
GNU_SYNTAX = f"$<NOT:{MSVC_SYNTAX}>"
MSVC_LINKER = f"${{{MSVC_LINKER_VARIABLE}}}"
APPLE_LINKER = f"${{{APPLE_LINKER_VARIABLE}}}"
GNU_LINKER = f"$<NOT:$<OR:{MSVC_LINKER},{APPLE_LINKER}>>"
OPTIMIZED_CONFIG = "$<NOT:$<CONFIG:Debug>>"
LINUX = "$<PLATFORM_ID:Linux>"
X86 = f"$<BOOL:${{{X86_VARIABLE}}}>"

_STRICT_MSVC: tuple[str, ...] = ("/W4",)
_STRICT_MSVC_CXX: tuple[str, ...] = ("/permissive-",)
_STRICT_GNU: tuple[str, ...] = (
    "-Wall",
    "-Wextra",
    "-Wconversion",
    "-Wsign-conversion",
    "-pedantic",
)
# The cpp-best-practices additions: each flags a real, recurring bug class.
_MAX_MSVC: tuple[str, ...] = (
    "/w14242",
    "/w14254",
    "/w14263",
    "/w14265",
    "/w14287",
    "/we4289",
    "/w14296",
    "/w14311",
    "/w14545",
    "/w14546",
    "/w14547",
    "/w14549",
    "/w14555",
    "/w14619",
    "/w14640",
    "/w14826",
    "/w14905",
    "/w14906",
    "/w14928",
)
_MAX_GNU: tuple[str, ...] = (
    "-Wshadow",
    "-Wcast-align",
    "-Wunused",
    "-Wnull-dereference",
    "-Wdouble-promotion",
    "-Wformat=2",
    "-Wimplicit-fallthrough",
)
_MAX_GNU_CXX: tuple[str, ...] = ("-Wnon-virtual-dtor", "-Wold-style-cast", "-Woverloaded-virtual")

# MSVC exposes x86-64 levels only from AVX2 upward; lower levels need no flag.
_MSVC_ARCH_BY_LEVEL: dict[str, str] = {"v3": "/arch:AVX2", "v4": "/arch:AVX512"}


def syntax_preamble(*, x86: bool) -> str:
    """Define the syntax and linker-family variables flag lines refer to.

    Args:
        x86: True to also detect whether the target CPU is x86, for
            profile flags only valid there.

    Returns:
        The preamble section text.
    """
    lines = [
        "# Flag syntax follows the compiler frontend (clang-cl speaks cl's command",
        "# line); linker flags follow the platform's linker.",
        f'set({MSVC_SYNTAX_VARIABLE} "$<OR:$<CXX_COMPILER_ID:MSVC>,'
        f'$<STREQUAL:${{CMAKE_CXX_COMPILER_FRONTEND_VARIANT}},MSVC>>")',
        f'set({MSVC_LINKER_VARIABLE} "$<AND:$<PLATFORM_ID:Windows>,$<NOT:$<BOOL:${{MINGW}}>>>")',
        f'set({APPLE_LINKER_VARIABLE} "$<PLATFORM_ID:Darwin,iOS,tvOS,watchOS,visionOS>")',
    ]
    if x86:
        lines.extend(
            (
                "# MSVC reports the target architecture separately from the host processor.",
                "if(MSVC)",
                '    set(_cmakeless_arch "${CMAKE_CXX_COMPILER_ARCHITECTURE_ID}")',
                "else()",
                '    set(_cmakeless_arch "${CMAKE_SYSTEM_PROCESSOR}")',
                "endif()",
                'if(_cmakeless_arch MATCHES "^([xX]64|[xX]86|x86_64|AMD64|amd64|i[3-6]86)$")',
                f"    set({X86_VARIABLE} ON)",
                "else()",
                f"    set({X86_VARIABLE} OFF)",
                "endif()",
            )
        )
    return "\n".join(lines)


def flag_line(flags: Sequence[str], *conditions: str | None) -> str:
    """Render flags as one list item, wrapped in every non-None condition.

    Args:
        flags: The flags, in order.
        *conditions: Boolean generator expressions; None entries are skipped.

    Returns:
        "a;b" bare, "$<c:a;b>" for one condition, "$<$<AND:c1,c2>:a;b>" for
        several.
    """
    active = [condition for condition in conditions if condition is not None]
    joined = ";".join(flags)
    if not active:
        return joined
    if len(active) == 1:
        return f"$<{active[0]}:{joined}>"
    return f"$<$<AND:{','.join(active)}>:{joined}>"


def language_guard(languages: Sequence[str], *, cxx_only: bool = False) -> str | None:
    """Restrict C-family flags so CUDA, Fortran, and assembler never see them.

    Args:
        languages: The languages enabled in this project node.
        cxx_only: True for flags only C++ accepts.

    Returns:
        None for a C++-only project (nothing else could receive the flags),
        else a $<COMPILE_LANGUAGE:...> condition.
    """
    if tuple(languages) == ("CXX",):
        return None
    return "$<COMPILE_LANGUAGE:CXX>" if cxx_only else "$<COMPILE_LANGUAGE:C,CXX>"


def warning_lines(preset: str, languages: Sequence[str]) -> list[str]:
    """Translate a warning preset into syntax-guarded flag lines.

    Args:
        preset: "max", "strict", "default", or "none".
        languages: The languages enabled in this project node.

    Returns:
        The flag lines; empty for "default".
    """
    c_family = language_guard(languages)
    if preset == "none":
        return [
            flag_line(("/W0",), MSVC_SYNTAX, c_family),
            flag_line(("-w",), GNU_SYNTAX, c_family),
        ]
    if preset not in ("strict", "max"):
        return []
    msvc = _STRICT_MSVC + (_MAX_MSVC if preset == "max" else ())
    gnu = _STRICT_GNU + (_MAX_GNU if preset == "max" else ())
    gnu_cxx = _MAX_GNU_CXX if preset == "max" else ()
    cxx = language_guard(languages, cxx_only=True)
    if cxx is None:
        return [
            flag_line((*msvc, *_STRICT_MSVC_CXX), MSVC_SYNTAX),
            flag_line((*gnu, *gnu_cxx), GNU_SYNTAX),
        ]
    lines = [
        flag_line(msvc, MSVC_SYNTAX, c_family),
        flag_line(_STRICT_MSVC_CXX, MSVC_SYNTAX, cxx),
        flag_line(gnu, GNU_SYNTAX, c_family),
    ]
    if gnu_cxx:
        lines.append(flag_line(gnu_cxx, GNU_SYNTAX, cxx))
    return lines


def cpu_lines(cpu: CpuModel, languages: Sequence[str]) -> tuple[list[str], list[str]]:
    """Translate a CPU target into compile and link flag lines.

    Args:
        cpu: The validated CPU target.
        languages: The languages enabled in this project node.

    Returns:
        (compile lines, link lines); ARM flags go to both, because the GNU
        driver picks the matching runtime libraries from them at link time.
    """
    c_family = language_guard(languages)
    if cpu.family is CpuFamily.NATIVE:
        return ([flag_line(("-march=native",), GNU_SYNTAX, c_family)], [])
    if cpu.family is CpuFamily.X86_64:
        assert cpu.level is not None, "Cpu.x86_64() always sets a level"
        compile_lines = [flag_line((f"-march=x86-64-{cpu.level}",), GNU_SYNTAX, c_family)]
        if cpu.level in _MSVC_ARCH_BY_LEVEL:
            compile_lines.append(
                flag_line((_MSVC_ARCH_BY_LEVEL[cpu.level],), MSVC_SYNTAX, c_family)
            )
        return (compile_lines, [])
    arm = [f"-mcpu={cpu.core}"]
    if cpu.fpu is not None:
        arm.append(f"-mfpu={cpu.fpu}")
    if cpu.float_abi is not None:
        arm.append(f"-mfloat-abi={cpu.float_abi}")
    return ([flag_line(arm, GNU_SYNTAX, c_family)], [flag_line(arm, GNU_SYNTAX)])


def profile_compile_lines(profile: ProfileModel, languages: Sequence[str]) -> list[str]:
    """Render every compile flag a profile contributes.

    Args:
        profile: The profile to render.
        languages: The languages enabled in this project node.

    Returns:
        Syntax-, platform-, and configuration-guarded compile flag lines.
    """
    c_family = language_guard(languages)
    lines: list[str] = []
    for flag_set, scope in _scoped_flag_sets(profile):
        release = OPTIMIZED_CONFIG if flag_set.release_only else None
        if flag_set.msvc_compile:
            lines.append(flag_line(flag_set.msvc_compile, MSVC_SYNTAX, scope, release, c_family))
        if flag_set.gnu_compile:
            lines.append(flag_line(flag_set.gnu_compile, GNU_SYNTAX, scope, release, c_family))
    return lines


def profile_link_lines(profile: ProfileModel) -> list[str]:
    """Render every linker flag a profile contributes, through CMake's LINKER: prefix.

    Args:
        profile: The profile to render.

    Returns:
        Linker-family-, platform-, and configuration-guarded link lines.
    """
    lines: list[str] = []
    for flag_set, scope in _scoped_flag_sets(profile):
        release = OPTIMIZED_CONFIG if flag_set.release_only else None
        for flags, linker in (
            (flag_set.msvc_link, MSVC_LINKER),
            (flag_set.gnu_link, GNU_LINKER),
            (flag_set.apple_link, APPLE_LINKER),
        ):
            if flags:
                linker_flags = [f"LINKER:{flag}" for flag in flags]
                lines.append(flag_line(linker_flags, linker, scope, release))
    return lines


def profile_define_lines(profile: ProfileModel) -> list[str]:
    """Render every preprocessor definition a profile contributes.

    Args:
        profile: The profile to render.

    Returns:
        Configuration- and platform-guarded definition tokens.
    """
    lines: list[str] = []
    for flag_set, scope in _scoped_flag_sets(profile):
        release = OPTIMIZED_CONFIG if flag_set.release_only else None
        lines.extend(flag_line((define,), scope, release) for define in flag_set.defines)
    return lines


def map_file_lines(target_name: str) -> list[str]:
    """Ask each linker family for a map file next to the linked binary.

    Args:
        target_name: The target whose map file to write.

    Returns:
        One LINKER: line per linker family.
    """
    path = f"$<TARGET_FILE_DIR:{target_name}>/{target_name}.map"
    return [
        flag_line((f"LINKER:/MAP:{path}",), MSVC_LINKER),
        flag_line((f"LINKER:-Map={path}",), GNU_LINKER),
        flag_line((f"LINKER:-map,{path}",), APPLE_LINKER),
    ]


def linker_script_line(script_path: str) -> str:
    """Pass a linker script to ELF linkers, the only family that reads one.

    Args:
        script_path: The script path as CMake should see it.

    Returns:
        The guarded LINKER: line.
    """
    return flag_line((f"LINKER:-T,{script_path}",), GNU_LINKER)


def needs_x86_detection(profile: ProfileModel | None) -> bool:
    """Tell whether a profile carries flags valid only on x86.

    Args:
        profile: The profile to inspect, or None.

    Returns:
        True when the x86 detection block must be emitted.
    """
    return profile is not None and bool(profile.x86_only)


def _scoped_flag_sets(profile: ProfileModel) -> list[tuple[FlagSetModel, str | None]]:
    """Pair each of a profile's flag sets with its platform condition.

    Args:
        profile: The profile to flatten.

    Returns:
        (flag set, condition or None) pairs in a fixed order.
    """
    return [
        *((flag_set, None) for flag_set in profile.flag_sets),
        *((flag_set, LINUX) for flag_set in profile.linux_only),
        *((flag_set, X86) for flag_set in profile.x86_only),
    ]
