"""The built-in registry knows the folklore for well-known packages."""

from __future__ import annotations

from cmakeless.deps.registry import known_packages, registry_entry


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
