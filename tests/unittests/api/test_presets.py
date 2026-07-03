"""The Preset builder and its freeze-time validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Preset, Project, Toolchain


@pytest.fixture
def project(project_dir: Path) -> Project:
    """A minimal buildable project."""
    built = Project("demo", cpp_std=20, root=project_dir)
    built.add_executable("demo", sources=["src/main.cpp"])
    return built


def test_presets_freeze_in_declaration_order(project: Project) -> None:
    """Presets freeze in declaration order."""
    project.add_preset(Preset("debug", optimize="none", sanitize=["address"]))
    project.add_preset(Preset("release", optimize="release", lto=True))
    model = project.freeze()
    assert [preset.name for preset in model.presets] == ["debug", "release"]
    assert model.presets[0].sanitize == ("address",)
    assert model.presets[1].lto is True


def test_preset_accepts_a_toolchain_object(project: Project) -> None:
    """Preset accepts a toolchain object."""
    toolchain = project.add_toolchain(Toolchain("arm64-linux", compiler="aarch64-linux-gnu-g++"))
    project.add_preset(Preset("cross", optimize="release", toolchain=toolchain))
    model = project.freeze()
    assert model.presets[0].toolchain == "arm64-linux"


def test_duplicate_preset_names_are_rejected(project: Project) -> None:
    """Duplicate preset names are rejected."""
    project.add_preset(Preset("debug"))
    project.add_preset(Preset("debug"))
    with pytest.raises(ConfigurationError, match="Duplicate preset name"):
        project.freeze()


def test_unknown_optimize_level_is_rejected(project: Project) -> None:
    """Unknown optimize level is rejected."""
    project.add_preset(Preset("fast", optimize="ludicrous"))
    with pytest.raises(ConfigurationError, match="ludicrous"):
        project.freeze()


def test_unknown_preset_sanitizer_is_rejected(project: Project) -> None:
    """Unknown preset sanitizer is rejected."""
    project.add_preset(Preset("debug", sanitize=["memory-hole"]))
    with pytest.raises(ConfigurationError, match="memory-hole"):
        project.freeze()


def test_address_and_thread_cannot_be_combined(project: Project) -> None:
    """Address and thread cannot be combined."""
    project.add_preset(Preset("clash", sanitize=["address", "thread"]))
    with pytest.raises(ConfigurationError, match="mutually exclusive"):
        project.freeze()


def test_dangling_toolchain_reference_is_rejected(project: Project) -> None:
    """Dangling toolchain reference is rejected."""
    project.add_preset(Preset("cross", toolchain="rpi4"))
    with pytest.raises(ConfigurationError, match="rpi4"):
        project.freeze()
