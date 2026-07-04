# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Metadata resolution: find_package names and imported targets."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless.deps.find_package import FindPackageAdapter, fill_metadata
from cmakeless.deps.lockfile import LockData
from cmakeless.deps.provider import ResolutionContext
from cmakeless.errors import DependencyError
from cmakeless.model.nodes import DependencyModel


def make_context() -> ResolutionContext:
    """An empty resolution context; metadata never needs the lock."""
    return ResolutionContext(root_dir=Path(), lock=LockData(packages={}))


def test_registry_fills_cmake_name_and_targets() -> None:
    """Registry fills cmake name and targets."""
    completed = fill_metadata(DependencyModel(name="googletest", version="1.14.0"))
    assert completed.cmake_name == "GTest"
    assert completed.link_targets == ("GTest::gtest", "GTest::gtest_main")


def test_user_overrides_beat_the_registry() -> None:
    """User overrides beat the registry."""
    completed = fill_metadata(
        DependencyModel(name="fmt", version="10.2.1", cmake_name="MyFmt", link_targets=("my::fmt",))
    )
    assert completed.cmake_name == "MyFmt"
    assert completed.link_targets == ("my::fmt",)


def test_components_expand_through_the_registry_template() -> None:
    """Components expand through the registry template."""
    completed = fill_metadata(
        DependencyModel(name="boost", version="1.84.0", components=("asio", "beast"))
    )
    assert completed.cmake_name == "Boost"
    assert completed.link_targets == ("Boost::asio", "Boost::beast")


def test_components_on_a_componentless_package_are_rejected() -> None:
    """Components on a componentless package are rejected."""
    with pytest.raises(DependencyError, match="does not take components"):
        fill_metadata(DependencyModel(name="fmt", version="10.2.1", components=("core",)))


def test_unknown_package_lists_the_registry_and_the_escape_hatch() -> None:
    """Unknown package lists the registry and the escape hatch."""
    with pytest.raises(DependencyError) as excinfo:
        fill_metadata(DependencyModel(name="obscurelib", version="1.0"))
    message = str(excinfo.value)
    assert "obscurelib" in message
    assert "fmt" in message
    assert "targets=" in message


def test_unknown_package_with_explicit_targets_defaults_the_cmake_name() -> None:
    """Unknown package with explicit targets defaults the cmake name."""
    completed = fill_metadata(
        DependencyModel(name="obscurelib", version="1.0", link_targets=("obscure::lib",))
    )
    assert completed.cmake_name == "obscurelib"
    assert completed.link_targets == ("obscure::lib",)


def test_adapter_resolve_is_pure_metadata() -> None:
    """Adapter resolve is pure metadata."""
    adapter = FindPackageAdapter()
    completed = adapter.resolve(DependencyModel(name="fmt", version="10.2.1"), make_context())
    assert completed.cmake_name == "fmt"
    assert completed.link_targets == ("fmt::fmt",)
    assert completed.url is None
    assert completed.sha256 is None
