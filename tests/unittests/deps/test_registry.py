# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The built-in registry knows the folklore for well-known packages."""

from __future__ import annotations

import importlib.metadata

import pytest

import cmakeless.deps.registry as registry_module
from cmakeless.deps.registry import RegistryEntry, known_packages, register, registry_entry


def test_fmt_entry_carries_the_full_folklore() -> None:
    """Fmt entry carries the full folklore."""
    entry = registry_entry("fmt")
    assert entry is not None
    assert entry.cmake_name == "fmt"
    assert entry.targets == ("fmt::fmt",)
    assert entry.url_template is not None
    assert entry.url_template.format(version="10.2.1").endswith("10.2.1.tar.gz")
    assert "10.2.1" in entry.sha256_by_version
    assert entry.vcpkg_name == "fmt"
    assert entry.conan_name == "fmt"


def test_unknown_package_returns_none() -> None:
    """Unknown package returns none."""
    assert registry_entry("not_a_real_package") is None


def test_known_packages_are_sorted_and_include_the_staples() -> None:
    """Known packages are sorted and include the staples."""
    names = known_packages()
    assert names == tuple(sorted(names))
    assert {"fmt", "boost", "catch2", "googletest"} <= set(names)


def test_every_entry_names_all_backends() -> None:
    """Every entry names all backends."""
    for name in known_packages():
        entry = registry_entry(name)
        assert entry is not None
        assert entry.cmake_name, name
        assert entry.vcpkg_name, name
        assert entry.conan_name, name
        assert entry.targets or entry.component_target_template is not None, name


def test_boost_is_marked_not_fetchable_and_component_based() -> None:
    """Boost is marked not fetchable and component based."""
    entry = registry_entry("boost")
    assert entry is not None
    assert entry.url_template is None
    assert entry.component_target_template == "Boost::{component}"


class _FakeEntryPoint:
    """A minimal stand-in for importlib.metadata's EntryPoint."""

    def __init__(self, name: str, produce: object) -> None:
        """Remember the entry point's name and what load() returns."""
        self.name = name
        self._produce = produce

    def load(self) -> object:
        """Return the zero-argument callable this entry point advertises."""
        return self._produce


def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, RegistryEntry]:
    """Give a test its own copy of the registry and a reset plugin-loaded flag.

    Args:
        monkeypatch: Restores both module attributes automatically on
            teardown, so tests never leak state into each other.

    Returns:
        The isolated registry dict, seeded with the real built-in entries.
    """
    isolated = dict(registry_module._REGISTRY)
    monkeypatch.setattr(registry_module, "_REGISTRY", isolated)
    monkeypatch.setattr(registry_module, "_plugins_loaded", False)
    return isolated


def test_register_adds_a_new_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register adds a new package."""
    _isolated_registry(monkeypatch)
    entry = RegistryEntry(cmake_name="Widgets", targets=("widgets::widgets",))
    register("widgets", entry)
    assert registry_entry("widgets") is entry
    assert "widgets" in known_packages()


def test_register_overrides_a_builtin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register overrides a builtin."""
    _isolated_registry(monkeypatch)
    mirror = RegistryEntry(
        cmake_name="fmt", targets=("fmt::fmt",), url_template="https://mirror.internal/fmt.tar.gz"
    )
    register("fmt", mirror)
    assert registry_entry("fmt") is mirror


def test_plugin_entry_points_are_merged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plugin entry points are merged, single entries and batches alike."""
    _isolated_registry(monkeypatch)
    single = RegistryEntry(cmake_name="Widgets", targets=("widgets::widgets",))
    batch = {"gadgets": RegistryEntry(cmake_name="Gadgets", targets=("gadgets::gadgets",))}
    points = (_FakeEntryPoint("widgets", lambda: single), _FakeEntryPoint("acme", lambda: batch))
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda *, group: points)
    assert registry_entry("widgets") is single
    assert registry_entry("gadgets") == batch["gadgets"]


def test_plugin_entry_points_do_not_override_builtins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plugin entry points do not override builtins."""
    isolated = _isolated_registry(monkeypatch)
    builtin_fmt = isolated["fmt"]
    mirror = RegistryEntry(cmake_name="fmt-mirror", targets=("fmt::mirror",))
    points = (_FakeEntryPoint("fmt", lambda: mirror),)
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda *, group: points)
    known_packages()  # forces discovery even though "fmt" is never a miss
    assert registry_entry("fmt") is builtin_fmt


def test_plugin_discovery_runs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plugin discovery runs once per process, not once per lookup."""
    _isolated_registry(monkeypatch)
    calls: list[str] = []

    def fake_entry_points(*, group: str) -> tuple[_FakeEntryPoint, ...]:
        """Record the requested group and report no plugins installed."""
        calls.append(group)
        return ()

    monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)
    registry_entry("not-a-real-package")
    registry_entry("still-not-a-real-package")
    assert len(calls) == 1
