# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The Toolchain builder: wrapped files and generated descriptions."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project, Toolchain


@pytest.fixture
def project(project_dir: Path) -> Project:
    """A minimal buildable project."""
    built = Project("demo", cpp_std=20, root=project_dir)
    built.add_executable("demo", sources=["src/main.cpp"])
    return built


def test_from_file_wraps_an_existing_toolchain(project: Project) -> None:
    """From file wraps an existing toolchain."""
    toolchain_file = project.root / "cmake" / "rpi4.toolchain.cmake"
    toolchain_file.parent.mkdir()
    toolchain_file.write_text("set(CMAKE_SYSTEM_NAME Linux)\n", encoding="utf-8")
    project.add_toolchain(Toolchain.from_file("cmake/rpi4.toolchain.cmake"))
    model = project.freeze()
    (toolchain,) = model.toolchains
    assert toolchain.name == "rpi4.toolchain"
    assert toolchain.file == Path("cmake/rpi4.toolchain.cmake")


def test_missing_wrapped_file_is_rejected(project: Project) -> None:
    """Missing wrapped file is rejected."""
    project.add_toolchain(Toolchain.from_file("cmake/nope.cmake"))
    with pytest.raises(ConfigurationError, match="does not exist"):
        project.freeze()


def test_generated_toolchain_freezes_its_fields(project: Project) -> None:
    """Generated toolchain freezes its fields."""
    project.add_toolchain(
        Toolchain(
            "arm64-linux",
            compiler="aarch64-linux-gnu-g++",
            system_name="Linux",
            system_processor="aarch64",
        )
    )
    model = project.freeze()
    (toolchain,) = model.toolchains
    assert toolchain.file is None
    assert toolchain.compiler == "aarch64-linux-gnu-g++"
    assert toolchain.system_name == "Linux"


def test_generated_toolchain_needs_a_compiler(project: Project) -> None:
    """Generated toolchain needs a compiler."""
    project.add_toolchain(Toolchain("empty"))
    with pytest.raises(ConfigurationError, match="neither a file nor a compiler"):
        project.freeze()


def test_duplicate_toolchain_names_are_rejected(project: Project) -> None:
    """Duplicate toolchain names are rejected."""
    project.add_toolchain(Toolchain("cross", compiler="g++"))
    project.add_toolchain(Toolchain("cross", compiler="clang++"))
    with pytest.raises(ConfigurationError, match="Duplicate toolchain name"):
        project.freeze()


def test_arm_none_eabi_sets_the_bare_metal_fields(project: Project) -> None:
    """arm_none_eabi sets the bare metal fields."""
    project.add_toolchain(Toolchain.arm_none_eabi(cpu="cortex-m0plus"))
    (toolchain,) = project.freeze().toolchains
    assert toolchain.name == "arm-none-eabi"
    assert toolchain.compiler == "arm-none-eabi-g++"
    assert toolchain.system_name == "Generic"
    assert toolchain.system_processor == "arm"
    assert ("CMAKE_CXX_FLAGS_INIT", "-mcpu=cortex-m0plus -mthumb") in toolchain.variables
    assert ("CMAKE_TRY_COMPILE_TARGET_TYPE", "STATIC_LIBRARY") in toolchain.variables


def test_ios_sets_sysroot_and_architecture_per_platform(project: Project) -> None:
    """ios sets sysroot and architecture per platform."""
    project.add_toolchain(Toolchain.ios(platform="SIMULATORARM64"))
    (toolchain,) = project.freeze().toolchains
    assert toolchain.system_name == "iOS"
    assert ("CMAKE_OSX_SYSROOT", "iphonesimulator") in toolchain.variables
    assert ("CMAKE_OSX_ARCHITECTURES", "arm64") in toolchain.variables


def test_ios_rejects_an_unknown_platform() -> None:
    """ios rejects an unknown platform."""
    with pytest.raises(ConfigurationError, match="platform"):
        Toolchain.ios(platform="OS32")


def test_android_wraps_the_ndk_toolchain_file(project: Project, tmp_path: Path) -> None:
    """android wraps the ndk toolchain file."""
    ndk_toolchain = tmp_path / "build" / "cmake" / "android.toolchain.cmake"
    ndk_toolchain.parent.mkdir(parents=True)
    ndk_toolchain.write_text("", encoding="utf-8")
    project.add_toolchain(Toolchain.android(ndk=tmp_path, abi="arm64-v8a", platform=24))
    (toolchain,) = project.freeze().toolchains
    assert toolchain.name == "android-arm64-v8a"
    assert toolchain.file == ndk_toolchain
    assert ("ANDROID_ABI", "arm64-v8a") in toolchain.variables
    assert ("ANDROID_PLATFORM", "android-24") in toolchain.variables


def test_android_rejects_an_unknown_abi() -> None:
    """android rejects an unknown abi."""
    with pytest.raises(ConfigurationError, match="abi"):
        Toolchain.android(ndk="/opt/ndk", abi="mips")


def test_emscripten_resolves_the_emsdk_argument(project: Project, tmp_path: Path) -> None:
    """emscripten resolves the emsdk argument."""
    expected = tmp_path / "upstream" / "emscripten" / "cmake" / "Modules" / "Platform"
    expected /= "Emscripten.cmake"
    expected.parent.mkdir(parents=True)
    expected.write_text("", encoding="utf-8")
    project.add_toolchain(Toolchain.emscripten(emsdk=tmp_path))
    (toolchain,) = project.freeze().toolchains
    assert toolchain.file == expected


def test_emscripten_resolves_the_emsdk_environment_variable(
    monkeypatch: pytest.MonkeyPatch, project: Project, tmp_path: Path
) -> None:
    """emscripten resolves the emsdk environment variable."""
    expected = tmp_path / "upstream" / "emscripten" / "cmake" / "Modules" / "Platform"
    expected /= "Emscripten.cmake"
    expected.parent.mkdir(parents=True)
    expected.write_text("", encoding="utf-8")
    monkeypatch.setenv("EMSDK", str(tmp_path))
    project.add_toolchain(Toolchain.emscripten())
    (toolchain,) = project.freeze().toolchains
    assert toolchain.file == expected


def test_emscripten_without_emsdk_or_env_var_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """emscripten without emsdk or env var raises."""
    monkeypatch.delenv("EMSDK", raising=False)
    with pytest.raises(ConfigurationError, match="EMSDK"):
        Toolchain.emscripten()
