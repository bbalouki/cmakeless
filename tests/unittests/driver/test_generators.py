"""Generator strategy selection."""

from __future__ import annotations

import pytest

from cmakeless.driver.generators import (
    CXX_MODULES_FAMILIES,
    Generator,
    GeneratorFamily,
    known_generator_names,
    select_generator,
    supports_cxx_modules,
)
from cmakeless.errors import ConfigurationError


def patch_ninja(monkeypatch: pytest.MonkeyPatch, *, available: bool) -> None:
    """Control whether ninja appears to be on PATH."""
    path = "C:/tools/ninja.exe" if available else None
    monkeypatch.setattr(
        "cmakeless.driver.generators.shutil.which",
        lambda tool: path if tool == "ninja" else None,
    )


def test_auto_prefers_ninja_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto prefers ninja when available."""
    patch_ninja(monkeypatch, available=True)
    assert select_generator(None).cmake_args == ("-G", "Ninja")


def test_auto_falls_back_to_cmake_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto falls back to cmake default."""
    patch_ninja(monkeypatch, available=False)
    assert select_generator(None).cmake_args == ()


def test_explicit_ninja_without_ninja_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit ninja without ninja is an error."""
    patch_ninja(monkeypatch, available=False)
    with pytest.raises(ConfigurationError, match=r"ninja-build.org"):
        select_generator("ninja")


def test_vs_delegates_to_cmake_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vs delegates to cmake default."""
    patch_ninja(monkeypatch, available=True)
    assert select_generator("vs").cmake_args == ()


def test_raw_generator_names_pass_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raw generator names pass through."""
    patch_ninja(monkeypatch, available=True)
    generator = select_generator("Xcode")
    assert generator.cmake_args == ("-G", "Xcode")


def test_ninja_multi_config_shorthand(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ninja multi config shorthand."""
    patch_ninja(monkeypatch, available=True)
    generator = select_generator("ninja-multi")
    assert generator.cmake_args == ("-G", "Ninja Multi-Config")
    assert generator.family is GeneratorFamily.NINJA_MULTI_CONFIG


def test_ninja_multi_config_without_ninja_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ninja multi config without ninja is an error."""
    patch_ninja(monkeypatch, available=False)
    with pytest.raises(ConfigurationError, match=r"ninja-build.org"):
        select_generator("ninja-multi")


def test_make_shorthand(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make shorthand."""
    patch_ninja(monkeypatch, available=True)
    generator = select_generator("make")
    assert generator.cmake_args == ("-G", "Unix Makefiles")
    assert generator.family is GeneratorFamily.MAKEFILES


def test_xcode_shorthand_has_no_path_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Xcode shorthand has no path check."""
    patch_ninja(monkeypatch, available=False)
    generator = select_generator("xcode")
    assert generator.cmake_args == ("-G", "Xcode")
    assert generator.family is GeneratorFamily.XCODE


def test_vs_shorthand_has_visual_studio_family(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vs shorthand has visual studio family."""
    patch_ninja(monkeypatch, available=True)
    assert select_generator("vs").family is GeneratorFamily.VISUAL_STUDIO


def test_raw_makefiles_name_gets_makefiles_family(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raw makefiles name gets makefiles family."""
    patch_ninja(monkeypatch, available=True)
    generator = select_generator("Unix Makefiles")
    assert generator.cmake_args == ("-G", "Unix Makefiles")
    assert generator.family is GeneratorFamily.MAKEFILES


def test_raw_ninja_multi_config_name_gets_correct_family(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raw ninja multi config name gets correct family, not plain Ninja."""
    patch_ninja(monkeypatch, available=True)
    generator = select_generator("Ninja Multi-Config")
    assert generator.family is GeneratorFamily.NINJA_MULTI_CONFIG


def test_known_generator_names_are_the_documented_shorthands() -> None:
    """Known generator names are the documented shorthands."""
    names = known_generator_names()
    assert "ninja" in names
    assert "ninja-multi" in names
    assert "vs" in names


def test_an_unrecognized_raw_generator_name_has_no_family() -> None:
    """A raw -G name CMakeless cannot classify falls back to OTHER."""
    generator = select_generator("Green Hills MULTI")
    assert generator.family is GeneratorFamily.OTHER


def test_a_raw_generator_name_is_passed_straight_through() -> None:
    """A raw -G name is passed straight through."""
    generator = select_generator("Green Hills MULTI")
    assert generator.cmake_args == ("-G", "Green Hills MULTI")


@pytest.mark.parametrize(
    ("family", "supported"),
    [
        (GeneratorFamily.NINJA, True),
        (GeneratorFamily.NINJA_MULTI_CONFIG, True),
        (GeneratorFamily.VISUAL_STUDIO, True),
        (GeneratorFamily.MAKEFILES, False),
        (GeneratorFamily.XCODE, False),
        (GeneratorFamily.OTHER, False),
    ],
)
def test_only_scanning_generators_support_cxx_modules(
    family: GeneratorFamily, supported: bool
) -> None:
    """Only scanning generators support cxx modules."""
    generator = Generator(name="x", cmake_args=(), family=family)
    assert supports_cxx_modules(generator) is supported
    assert (family in CXX_MODULES_FAMILIES) is supported
