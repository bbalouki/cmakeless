"""Source languages are inferred from suffixes, CXX first and always present."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless.model.languages import is_known_suffix, language_of, languages_for


@pytest.mark.parametrize(
    ("name", "language"),
    [
        ("main.cpp", "CXX"),
        ("geometry.cppm", "CXX"),
        ("hal.c", "C"),
        ("startup.S", "ASM"),
        ("startup.s", "ASM"),
        ("vectors.asm", "ASM_MASM"),
        ("kernel.cu", "CUDA"),
        ("solver.f90", "Fortran"),
        ("solver.F90", "Fortran"),
        ("view.mm", "OBJCXX"),
        ("shade.ispc", "ISPC"),
    ],
)
def test_compiled_suffixes_map_to_their_cmake_language(name: str, language: str) -> None:
    """Every compiled suffix names the CMake language that compiles it."""
    assert language_of(Path(name)) == language


def test_a_cxx_only_tree_enables_exactly_cxx() -> None:
    """A C++-only tree keeps emitting LANGUAGES CXX, byte for byte."""
    assert languages_for([Path("a.cpp"), Path("b.hpp")]) == ("CXX",)


def test_mixed_sources_enable_languages_in_a_fixed_order() -> None:
    """Languages come out in one deterministic order regardless of input order."""
    sources = [Path("k.cu"), Path("startup.S"), Path("hal.c"), Path("main.cpp")]
    assert languages_for(sources) == ("CXX", "C", "ASM", "CUDA")


@pytest.mark.parametrize("name", ["include/a.hpp", "app.rc", "boards/f4.ld", "ui/main.ui"])
def test_headers_and_resources_are_known_but_not_compiled(name: str) -> None:
    """Headers, resources, and linker scripts are accepted without a language."""
    assert is_known_suffix(Path(name))
    assert language_of(Path(name)) is None


def test_a_typo_suffix_is_unknown() -> None:
    """A misspelled suffix is neither compiled nor a known non-compiled kind."""
    assert not is_known_suffix(Path("main.cp_"))
