"""Source-file languages, inferred from suffixes the way CMake itself does.

A project only enables the languages its sources need, in one fixed order,
so a C++-only project keeps emitting exactly `LANGUAGES CXX`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

# The order languages appear in project(... LANGUAGES ...); CXX first so a
# C++-only project's output never changes.
LANGUAGE_ORDER: tuple[str, ...] = (
    "CXX",
    "C",
    "ASM",
    "ASM_MASM",
    "CUDA",
    "HIP",
    "ISPC",
    "Fortran",
    "OBJC",
    "OBJCXX",
)

# Compiled-source suffixes by the CMake language that compiles them. The
# case-sensitive entries matter: ".S" is preprocessed assembly and ".F90" is
# preprocessed Fortran, exactly as CMake treats them.
LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".cpp": "CXX",
    ".cc": "CXX",
    ".cxx": "CXX",
    ".c++": "CXX",
    ".cp": "CXX",
    ".cppm": "CXX",
    ".ixx": "CXX",
    ".mpp": "CXX",
    ".c": "C",
    ".s": "ASM",
    ".S": "ASM",
    ".asm": "ASM_MASM",
    ".cu": "CUDA",
    ".hip": "HIP",
    ".ispc": "ISPC",
    ".f": "Fortran",
    ".F": "Fortran",
    ".for": "Fortran",
    ".f77": "Fortran",
    ".f90": "Fortran",
    ".F90": "Fortran",
    ".f95": "Fortran",
    ".f03": "Fortran",
    ".f08": "Fortran",
    ".m": "OBJC",
    ".mm": "OBJCXX",
}

# Suffixes that are legitimately listed as sources without being compiled:
# headers (for IDE project trees), Windows resources, linker inputs, and
# files Qt's AUTOUIC and AUTORCC process.
NON_COMPILED_SUFFIXES: frozenset[str] = frozenset(
    {
        ".h",
        ".hh",
        ".hpp",
        ".hxx",
        ".h++",
        ".inl",
        ".ipp",
        ".tpp",
        ".tcc",
        ".cuh",
        ".inc",
        ".rc",
        ".def",
        ".manifest",
        ".natvis",
        ".ui",
        ".qrc",
        ".ld",
        ".o",
        ".obj",
        ".a",
        ".lib",
        ".plist",
    }
)


def language_of(source: Path) -> str | None:
    """Name the CMake language that compiles one source file.

    Args:
        source: A source path; only its suffix is inspected.

    Returns:
        The CMake language name, or None for a non-compiled or unknown file.
    """
    return LANGUAGE_BY_SUFFIX.get(source.suffix) or LANGUAGE_BY_SUFFIX.get(source.suffix.lower())


def is_known_suffix(source: Path) -> bool:
    """Tell whether a source suffix is one CMakeless knows how to treat.

    Args:
        source: A source path.

    Returns:
        True for compiled sources and for the known non-compiled kinds.
    """
    return language_of(source) is not None or source.suffix.lower() in NON_COMPILED_SUFFIXES


def languages_for(sources: Iterable[Path]) -> tuple[str, ...]:
    """Collect the languages a set of sources needs, CXX always included.

    CXX stays enabled even for a C-only tree because every target carries a
    cxx_std compile feature, which CMake rejects when CXX is not enabled.

    Args:
        sources: Every compiled source in one project node.

    Returns:
        The languages in LANGUAGE_ORDER.
    """
    found = {"CXX"} | {language for source in sources if (language := language_of(source))}
    return tuple(language for language in LANGUAGE_ORDER if language in found)
