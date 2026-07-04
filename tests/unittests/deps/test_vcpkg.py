# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The vcpkg adapter: manifest generation, root detection, toolchain wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmakeless.deps.lockfile import LockData
from cmakeless.deps.provider import ResolutionContext
from cmakeless.deps.vcpkg import VcpkgAdapter, vcpkg_root
from cmakeless.errors import DependencyError, ToolchainError
from cmakeless.model.nodes import DependencyModel, ProjectModel


def make_model(*dependencies: DependencyModel, name: str = "demo") -> ProjectModel:
    """A frozen project around the given dependencies."""
    return ProjectModel(
        name=name,
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/does/not/matter"),
        source_script="cmakelessfile.py",
        package_manager="vcpkg",
        dependencies=dependencies,
    )


def hide_vcpkg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every vcpkg discovery mechanism come up empty."""
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    monkeypatch.delenv("VCPKG_INSTALLATION_ROOT", raising=False)
    monkeypatch.setattr("cmakeless.deps.vcpkg.shutil.which", lambda _: None)


def test_manifest_with_baseline_pins_versions() -> None:
    """Manifest with baseline pins versions."""
    adapter = VcpkgAdapter()
    model = make_model(
        DependencyModel(name="googletest", version="1.14.0"),
        DependencyModel(name="fmt", version="10.2.1"),
    )
    files = adapter.manifest_files(model, LockData(packages={}, vcpkg_baseline="abc123"))
    manifest = json.loads(files[Path("vcpkg.json")])
    assert manifest["builtin-baseline"] == "abc123"
    assert manifest["dependencies"] == [
        {"name": "fmt", "version>=": "10.2.1"},
        {"name": "gtest", "version>=": "1.14.0"},
    ]


def test_manifest_without_baseline_lists_plain_ports() -> None:
    """Manifest without baseline lists plain ports."""
    adapter = VcpkgAdapter()
    model = make_model(DependencyModel(name="fmt", version="10.2.1"))
    manifest = json.loads(adapter.manifest_files(model, LockData(packages={}))[Path("vcpkg.json")])
    assert "builtin-baseline" not in manifest
    assert manifest["dependencies"] == ["fmt"]


def test_manifest_name_is_sanitized_for_vcpkg() -> None:
    """Manifest name is sanitized for vcpkg."""
    adapter = VcpkgAdapter()
    model = make_model(DependencyModel(name="fmt", version="10.2.1"), name="My_Game")
    manifest = json.loads(adapter.manifest_files(model, LockData(packages={}))[Path("vcpkg.json")])
    assert manifest["name"] == "my-game"


def test_root_prefers_the_vcpkg_root_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Root prefers the vcpkg root variable."""
    monkeypatch.setenv("VCPKG_ROOT", str(tmp_path))
    assert vcpkg_root() == tmp_path


def test_root_falls_back_to_the_github_runner_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Root falls back to the github runner variable."""
    monkeypatch.delenv("VCPKG_ROOT", raising=False)
    monkeypatch.setenv("VCPKG_INSTALLATION_ROOT", str(tmp_path))
    assert vcpkg_root() == tmp_path


def test_missing_vcpkg_raises_toolchain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing vcpkg raises toolchain error."""
    hide_vcpkg(monkeypatch)
    with pytest.raises(ToolchainError, match="VCPKG_ROOT"):
        vcpkg_root()


def test_toolchain_args_point_at_the_vcpkg_toolchain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Toolchain args point at the vcpkg toolchain."""
    monkeypatch.setenv("VCPKG_ROOT", str(tmp_path))
    (argument,) = VcpkgAdapter().toolchain_args(tmp_path / "build", build_type="Release")
    assert argument.startswith("-DCMAKE_TOOLCHAIN_FILE=")
    assert argument.endswith(str(Path("scripts") / "buildsystems" / "vcpkg.cmake"))


def test_lock_baseline_reuses_the_locked_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lock baseline reuses the locked value."""
    hide_vcpkg(monkeypatch)
    context = ResolutionContext(
        root_dir=Path(), lock=LockData(packages={}, vcpkg_baseline="locked123")
    )
    assert VcpkgAdapter().lock_baseline(context) == "locked123"


def test_lock_baseline_tolerates_a_missing_installation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock baseline tolerates a missing installation."""
    hide_vcpkg(monkeypatch)
    context = ResolutionContext(root_dir=Path(), lock=LockData(packages={}))
    assert VcpkgAdapter().lock_baseline(context) is None


def test_offline_without_install_raises(tmp_path: Path) -> None:
    """Offline without install raises."""
    with pytest.raises(DependencyError, match="already installed"):
        VcpkgAdapter().pre_configure(
            root_dir=tmp_path, build_dir=tmp_path / "build", build_type="Release", offline=True
        )


def test_offline_with_install_present_succeeds(tmp_path: Path) -> None:
    """Offline with install present succeeds."""
    installed = tmp_path / "build" / "vcpkg_installed" / "x64-linux"
    installed.mkdir(parents=True)
    (installed / "lib").mkdir()
    VcpkgAdapter().pre_configure(
        root_dir=tmp_path, build_dir=tmp_path / "build", build_type="Release", offline=True
    )


def test_online_needs_no_install_directory(tmp_path: Path) -> None:
    """Online needs no install directory."""
    VcpkgAdapter().pre_configure(
        root_dir=tmp_path, build_dir=tmp_path / "build", build_type="Release", offline=False
    )


def test_resolve_fills_metadata_only() -> None:
    """Resolve fills metadata only."""
    adapter = VcpkgAdapter()
    context = ResolutionContext(root_dir=Path(), lock=LockData(packages={}))
    completed = adapter.resolve(DependencyModel(name="fmt", version="10.2.1"), context)
    assert completed.cmake_name == "fmt"
    assert completed.link_targets == ("fmt::fmt",)
    assert completed.url is None
