"""Per-run build instrumentation: coverage, profile-guided optimization, time traces.

The CLI switches these on for one run, in a build tree of their own, so the
normal build is never touched. Flags are attached per target, never as
directory-level globals.
"""

from __future__ import annotations

from collections.abc import Sequence

from cmakeless.emitter.flags import GNU_SYNTAX, MSVC_SYNTAX, flag_line, language_guard
from cmakeless.model.nodes import ProjectModel

# The cache variable holding the directory PGO profiles are written to and
# read from; shared between the generate and use build trees.
PGO_DIRECTORY_VARIABLE = "CMAKELESS_PGO_DIR"

# The merged profile llvm-profdata writes for Clang's -fprofile-use.
CLANG_PROFDATA_NAME = "cmakeless.profdata"

_CLANG = "$<CXX_COMPILER_ID:Clang,AppleClang,IntelLLVM>"
_GCC = "$<CXX_COMPILER_ID:GNU>"
_PGO_DIR = f"${{{PGO_DIRECTORY_VARIABLE}}}"


def instrumentation_section(model: ProjectModel) -> list[str]:
    """Declare what instrumentation needs once per file.

    Args:
        model: The frozen project node.

    Returns:
        The PGO directory cache variable and an MSVC notice, when relevant.
    """
    active = set(model.instrumentation)
    sections: list[str] = []
    if active & {"pgo-generate", "pgo-use"}:
        sections.append(
            f'set({PGO_DIRECTORY_VARIABLE} "${{CMAKE_BINARY_DIR}}/../pgo-profiles" CACHE PATH\n'
            f'    "Where profile-guided optimization data is written and read")'
        )
    if active & {"coverage", "pgo-generate", "pgo-use"}:
        sections.append(
            "if(MSVC)\n"
            '    message(WARNING "cmakeless coverage and pgo use GCC/Clang instrumentation; '
            'with MSVC run OpenCppCoverage or Visual Studio PGO instead.")\n'
            "endif()"
        )
    return sections


def instrumentation_compile_lines(model: ProjectModel, languages: Sequence[str]) -> list[str]:
    """Collect the compile flags every compiled target gets for this run.

    Args:
        model: The frozen project node.
        languages: The languages enabled in this project node.

    Returns:
        Syntax- and compiler-guarded flag lines; empty without instrumentation.
    """
    c_family = language_guard(languages)
    lines: list[str] = []
    for name in model.instrumentation:
        if name == "coverage":
            lines.append(flag_line(("--coverage",), GNU_SYNTAX, c_family))
        elif name == "time-trace":
            lines.append(flag_line(("-ftime-trace",), GNU_SYNTAX, _CLANG, c_family))
            lines.append(flag_line(("/clang:-ftime-trace",), MSVC_SYNTAX, _CLANG, c_family))
        else:
            lines.extend(_pgo_lines(name, c_family))
    return lines


def instrumentation_link_lines(model: ProjectModel) -> list[str]:
    """Collect the link flags every linked target gets for this run.

    Args:
        model: The frozen project node.

    Returns:
        Syntax- and compiler-guarded flag lines; time traces need none.
    """
    lines: list[str] = []
    for name in model.instrumentation:
        if name == "coverage":
            lines.append(flag_line(("--coverage",), GNU_SYNTAX))
        elif name != "time-trace":
            lines.extend(_pgo_lines(name, None))
    return lines


def _pgo_lines(name: str, c_family: str | None) -> list[str]:
    """Render one PGO stage for GCC and for Clang, which take different paths.

    GCC reads a directory of .gcda files; Clang reads one merged .profdata
    file, which the driver produces with llvm-profdata between the stages.

    Args:
        name: "pgo-generate" or "pgo-use".
        c_family: The language guard, or None for link lines.

    Returns:
        Two compiler-guarded flag lines.
    """
    if name == "pgo-generate":
        flags = (f"-fprofile-generate={_PGO_DIR}",)
        return [flag_line(flags, GNU_SYNTAX, c_family)]
    gcc = (f"-fprofile-use={_PGO_DIR}", "-fprofile-correction", "-Wno-missing-profile")
    clang = (f"-fprofile-use={_PGO_DIR}/{CLANG_PROFDATA_NAME}",)
    return [
        flag_line(gcc, GNU_SYNTAX, _GCC, c_family),
        flag_line(clang, GNU_SYNTAX, _CLANG, c_family),
    ]
