# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The built-in package registry: the folklore raw CMake makes you memorize.

For each well-known package the registry records the find_package() name,
the exported targets (``fmt::fmt`` is not ``fmt``), the canonical source
archive URL, curated SHA256 pins for the versions we test, and the port
names the vcpkg and Conan backends use. Anything not listed here still works
through the explicit overrides on ``target.depends()``.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from dataclasses import dataclass, field

# The entry-point group installed plugin distributions publish registry
# entries under; see register() and _load_plugin_registrations() below.
PLUGIN_ENTRY_POINT_GROUP = "cmakeless.registry"


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
    # pybind11 exposes the pybind11_add_module() command and the
    # pybind11::headers target once fetched; find_package(pybind11) works too.
    "pybind11": RegistryEntry(
        cmake_name="pybind11",
        targets=("pybind11::headers",),
        url_template="https://github.com/pybind/pybind11/archive/refs/tags/v{version}.tar.gz",
        vcpkg_name="pybind11",
        conan_name="pybind11",
    ),
    # nanobind exposes the nanobind_add_module() command once fetched; its
    # release tarballs bundle the robin_map dependency it needs.
    "nanobind": RegistryEntry(
        cmake_name="nanobind",
        targets=("nanobind::nanobind",),
        url_template="https://github.com/wjakob/nanobind/archive/refs/tags/v{version}.tar.gz",
        vcpkg_name="nanobind",
        conan_name="nanobind",
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
    # Growing the curated list from vcpkg/Conan metadata at scale (ROADMAP.md
    # Phase 5.3): general-purpose, gaming, and finance/engineering/aerospace
    # staples. None of these pin url_template/sha256_by_version, matching
    # zlib/boost above: they resolve through find_package or a package
    # manager backend by default, and an explicit depends(url=..., sha256=...)
    # override opts a project into "auto" mode's FetchContent fallback.
    "abseil": RegistryEntry(
        cmake_name="absl",
        targets=(),
        component_target_template="absl::{component}",
        vcpkg_name="abseil",
        conan_name="abseil",
    ),
    "protobuf": RegistryEntry(
        cmake_name="protobuf",
        targets=("protobuf::libprotobuf",),
        vcpkg_name="protobuf",
        conan_name="protobuf",
    ),
    "grpc": RegistryEntry(
        cmake_name="gRPC", targets=("gRPC::grpc++",), vcpkg_name="grpc", conan_name="grpc"
    ),
    "openssl": RegistryEntry(
        cmake_name="OpenSSL",
        targets=("OpenSSL::SSL", "OpenSSL::Crypto"),
        vcpkg_name="openssl",
        conan_name="openssl",
    ),
    "curl": RegistryEntry(
        cmake_name="CURL", targets=("CURL::libcurl",), vcpkg_name="curl", conan_name="libcurl"
    ),
    "sqlite3": RegistryEntry(
        cmake_name="SQLite3",
        targets=("SQLite::SQLite3",),
        vcpkg_name="sqlite3",
        conan_name="sqlite3",
    ),
    "eigen": RegistryEntry(
        cmake_name="Eigen3",
        targets=("Eigen3::Eigen",),
        vcpkg_name="eigen3",
        conan_name="eigen",
    ),
    "glm": RegistryEntry(
        cmake_name="glm", targets=("glm::glm",), vcpkg_name="glm", conan_name="glm"
    ),
    "tbb": RegistryEntry(
        cmake_name="TBB", targets=("TBB::tbb",), vcpkg_name="tbb", conan_name="onetbb"
    ),
    "benchmark": RegistryEntry(
        cmake_name="benchmark",
        targets=("benchmark::benchmark",),
        vcpkg_name="benchmark",
        conan_name="benchmark",
    ),
    "gflags": RegistryEntry(
        cmake_name="gflags", targets=("gflags::gflags",), vcpkg_name="gflags", conan_name="gflags"
    ),
    "glog": RegistryEntry(
        cmake_name="glog", targets=("glog::glog",), vcpkg_name="glog", conan_name="glog"
    ),
    "yaml-cpp": RegistryEntry(
        cmake_name="yaml-cpp",
        targets=("yaml-cpp::yaml-cpp",),
        vcpkg_name="yaml-cpp",
        conan_name="yaml-cpp",
    ),
    "tinyxml2": RegistryEntry(
        cmake_name="tinyxml2",
        targets=("tinyxml2::tinyxml2",),
        vcpkg_name="tinyxml2",
        conan_name="tinyxml2",
    ),
    "pugixml": RegistryEntry(
        cmake_name="pugixml",
        targets=("pugixml::pugixml",),
        vcpkg_name="pugixml",
        conan_name="pugixml",
    ),
    "cxxopts": RegistryEntry(
        cmake_name="cxxopts",
        targets=("cxxopts::cxxopts",),
        vcpkg_name="cxxopts",
        conan_name="cxxopts",
    ),
    "cli11": RegistryEntry(
        cmake_name="CLI11", targets=("CLI11::CLI11",), vcpkg_name="cli11", conan_name="cli11"
    ),
    "cereal": RegistryEntry(
        cmake_name="cereal", targets=("cereal::cereal",), vcpkg_name="cereal", conan_name="cereal"
    ),
    "range-v3": RegistryEntry(
        cmake_name="range-v3",
        targets=("range-v3::range-v3",),
        vcpkg_name="range-v3",
        conan_name="range-v3",
    ),
    "toml11": RegistryEntry(
        cmake_name="toml11",
        targets=("toml11::toml11",),
        vcpkg_name="toml11",
        conan_name="toml11",
    ),
    "mimalloc": RegistryEntry(
        cmake_name="mimalloc",
        targets=("mimalloc",),
        vcpkg_name="mimalloc",
        conan_name="mimalloc",
    ),
    # Gaming.
    "sdl2": RegistryEntry(
        cmake_name="SDL2", targets=("SDL2::SDL2",), vcpkg_name="sdl2", conan_name="sdl"
    ),
    # glfw's find_package name keeps the "3" its CMake config ships under;
    # the target it exports does not.
    "glfw": RegistryEntry(
        cmake_name="glfw3", targets=("glfw",), vcpkg_name="glfw3", conan_name="glfw"
    ),
    "glew": RegistryEntry(
        cmake_name="GLEW", targets=("GLEW::GLEW",), vcpkg_name="glew", conan_name="glew"
    ),
    "vulkan": RegistryEntry(
        cmake_name="Vulkan",
        targets=("Vulkan::Vulkan",),
        vcpkg_name="vulkan",
        conan_name="vulkan-loader",
    ),
    "imgui": RegistryEntry(
        cmake_name="imgui", targets=("imgui::imgui",), vcpkg_name="imgui", conan_name="imgui"
    ),
    "box2d": RegistryEntry(
        cmake_name="box2d", targets=("box2d::box2d",), vcpkg_name="box2d", conan_name="box2d"
    ),
    "openal-soft": RegistryEntry(
        cmake_name="OpenAL",
        targets=("OpenAL::OpenAL",),
        vcpkg_name="openal-soft",
        conan_name="openal",
    ),
    "freetype": RegistryEntry(
        cmake_name="Freetype",
        targets=("Freetype::Freetype",),
        vcpkg_name="freetype",
        conan_name="freetype",
    ),
    "assimp": RegistryEntry(
        cmake_name="assimp", targets=("assimp::assimp",), vcpkg_name="assimp", conan_name="assimp"
    ),
    "entt": RegistryEntry(
        cmake_name="EnTT", targets=("EnTT::EnTT",), vcpkg_name="entt", conan_name="entt"
    ),
    # Finance, engineering, and aerospace.
    "quantlib": RegistryEntry(
        cmake_name="QuantLib",
        targets=("QuantLib::QuantLib",),
        vcpkg_name="quantlib",
        conan_name="quantlib",
    ),
    "date": RegistryEntry(
        cmake_name="date", targets=("date::date",), vcpkg_name="date", conan_name="date"
    ),
    # OpenCV's exported targets are per-module (opencv_core, opencv_imgproc,
    # ...); this default covers the common case, override targets=[...] for
    # additional modules.
    "opencv": RegistryEntry(
        cmake_name="OpenCV", targets=("opencv_core",), vcpkg_name="opencv4", conan_name="opencv"
    ),
    "ceres": RegistryEntry(
        cmake_name="Ceres",
        targets=("Ceres::ceres",),
        vcpkg_name="ceres",
        conan_name="ceres-solver",
    ),
    "proj": RegistryEntry(
        cmake_name="PROJ", targets=("PROJ::proj",), vcpkg_name="proj", conan_name="proj"
    ),
}


def register(name: str, entry: RegistryEntry) -> None:
    """Register or override one package in the process-wide registry.

    Last write wins: calling this again for the same name replaces the
    previous entry, which is how a cmakelessfile.py repoints a built-in
    package at an internal mirror or teaches CMakeless about a package the
    curated list does not carry.

    Args:
        name: The package name as used in depends() specs.
        entry: The metadata describing how to acquire and link it.
    """
    _REGISTRY[name] = entry


_plugins_loaded = False


def _load_plugin_registrations() -> None:
    """Discover and merge registry entries from installed plugin packages.

    Iterates the "cmakeless.registry" entry-point group once per process;
    each entry point must load to a zero-argument callable returning either
    a single RegistryEntry (keyed by the entry point's own name) or a
    Mapping[str, RegistryEntry] (a batch, keyed by the mapping's keys).

    Plugin-supplied entries never override a built-in or an explicit
    register() call: discovery order across installed distributions is not
    user-controlled the way an explicit register() call is, so explicit
    registration always wins over auto-discovery.
    """
    global _plugins_loaded
    if _plugins_loaded:
        return
    _plugins_loaded = True
    for entry_point in importlib.metadata.entry_points(group=PLUGIN_ENTRY_POINT_GROUP):
        produced = entry_point.load()()
        if isinstance(produced, RegistryEntry):
            _REGISTRY.setdefault(entry_point.name, produced)
        else:
            for name, entry in produced.items():
                _REGISTRY.setdefault(name, entry)


def registry_entry(name: str) -> RegistryEntry | None:
    """Look up one package in the registry, built-in or plugin-supplied.

    Args:
        name: The package name as written in the depends() spec.

    Returns:
        The registry entry, or None for a package we do not know.
    """
    if name not in _REGISTRY:
        _load_plugin_registrations()
    return _REGISTRY.get(name)


def known_packages() -> tuple[str, ...]:
    """List every package the registry knows, built-in and plugin-supplied.

    Returns:
        The registered package names, sorted.
    """
    _load_plugin_registrations()
    return tuple(sorted(_REGISTRY))
