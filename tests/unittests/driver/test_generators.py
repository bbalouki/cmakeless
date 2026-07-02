"""Generator strategy selection."""

from __future__ import annotations

import pytest

from cmakeless.driver.generators import select_generator
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
