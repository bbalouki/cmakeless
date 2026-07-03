"""The built-in package registry: the folklore raw CMake makes you memorize.

For each well-known package the registry records the find_package() name,
the exported targets (``fmt::fmt`` is not ``fmt``), the canonical source
archive URL, curated SHA256 pins for the versions we test, and the port
names the vcpkg and Conan backends use. Anything not listed here still works
through the explicit overrides on ``target.depends()``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    """Everything the adapters need to know about one well-known package.

    Attributes:
        cmake_name: The name find_package() knows the package by.
        targets: The imported targets consumers link against.
        component_target_template: Format string turning a component name
            into an imported target (for example ``Boost::{component}``),
            or None when the package has no components.
        url_template: Format string turning a version into a source archive
            URL, or None when source builds are impractical (boost) and a
            package manager backend should be used instead.
        sha256_by_version: Curated archive pins for the versions we test;
            other versions are hashed on first resolution and locked.
        vcpkg_name: The vcpkg port name.
        conan_name: The Conan Center reference name.
    """

    cmake_name: str
    targets: tuple[str, ...]
    component_target_template: str | None = None
    url_template: str | None = None
    sha256_by_version: Mapping[str, str] = field(default_factory=dict)
    vcpkg_name: str = ""
    conan_name: str = ""


_REGISTRY: dict[str, RegistryEntry] = {
    "fmt": RegistryEntry(
        cmake_name="fmt",
        targets=("fmt::fmt",),
        url_template="https://github.com/fmtlib/fmt/archive/refs/tags/{version}.tar.gz",
        sha256_by_version={
            "10.2.1": "1250e4cc58bf06ee631567523f48848dc4596133e163f02615c97f78bab6c811",
        },
        vcpkg_name="fmt",
        conan_name="fmt",
    ),
    "spdlog": RegistryEntry(
        cmake_name="spdlog",
        targets=("spdlog::spdlog",),
        url_template="https://github.com/gabime/spdlog/archive/refs/tags/v{version}.tar.gz",
        vcpkg_name="spdlog",
        conan_name="spdlog",
    ),
    "catch2": RegistryEntry(
        cmake_name="Catch2",
        targets=("Catch2::Catch2WithMain",),
        url_template="https://github.com/catchorg/Catch2/archive/refs/tags/v{version}.tar.gz",
        sha256_by_version={
            "3.5.4": "b7754b711242c167d8f60b890695347f90a1ebc95949a045385114165d606dbb",
        },
        vcpkg_name="catch2",
        conan_name="catch2",
    ),
    "doctest": RegistryEntry(
        cmake_name="doctest",
        targets=("doctest::doctest",),
        url_template="https://github.com/doctest/doctest/archive/refs/tags/v{version}.tar.gz",
        sha256_by_version={
            "2.4.11": "632ed2c05a7f53fa961381497bf8069093f0d6628c5f26286161fbd32a560186",
        },
        vcpkg_name="doctest",
        conan_name="doctest",
    ),
    "googletest": RegistryEntry(
        cmake_name="GTest",
        targets=("GTest::gtest", "GTest::gtest_main"),
        url_template="https://github.com/google/googletest/archive/refs/tags/v{version}.tar.gz",
        sha256_by_version={
            "1.14.0": "8ad598c73ad796e0d8280b082cebd82a630d73e73cd3c70057938a6501bba5d7",
        },
        vcpkg_name="gtest",
        conan_name="gtest",
    ),
    "nlohmann_json": RegistryEntry(
        cmake_name="nlohmann_json",
        targets=("nlohmann_json::nlohmann_json",),
        url_template="https://github.com/nlohmann/json/archive/refs/tags/v{version}.tar.gz",
        vcpkg_name="nlohmann-json",
        conan_name="nlohmann_json",
    ),
    # zlib's own CMake build does not export the ZLIB::ZLIB target that
    # find_package provides, so a source fetch would link a different name.
    "zlib": RegistryEntry(
        cmake_name="ZLIB",
        targets=("ZLIB::ZLIB",),
        vcpkg_name="zlib",
        conan_name="zlib",
    ),
    # A source build of boost is impractical; use vcpkg or Conan for it.
    "boost": RegistryEntry(
        cmake_name="Boost",
        targets=(),
        component_target_template="Boost::{component}",
        vcpkg_name="boost",
        conan_name="boost",
    ),
}


def registry_entry(name: str) -> RegistryEntry | None:
    """Look up one package in the built-in registry.

    Args:
        name: The package name as written in the depends() spec.

    Returns:
        The registry entry, or None for a package we do not know.
    """
    return _REGISTRY.get(name)


def known_packages() -> tuple[str, ...]:
    """List every package the built-in registry knows, for error messages.

    Returns:
        The registered package names, sorted.
    """
    return tuple(sorted(_REGISTRY))
